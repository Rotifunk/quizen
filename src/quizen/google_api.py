"""Google Drive/Sheets integration helpers."""
from __future__ import annotations

import io
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from .models import ExportRow


logger = logging.getLogger(__name__)


DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_SCOPES = DRIVE_SCOPES + SHEETS_SCOPES


def load_credentials(
    credentials_path: Path,
    scopes: Sequence[str] | None = None,
    token_path: Optional[Path] = None,
    allow_browser_flow: bool = False,
):
    """Load Google credentials from a service account or OAuth client secret.

    - 서비스 계정 키(`type == service_account`)이면 바로 로드
    - OAuth 클라이언트(JSON 내 `web`/`installed`)는 저장된 token JSON을 우선 사용
    - token이 없고 `allow_browser_flow=True`이면 로컬 서버 플로우로 token 생성 후 저장
    """

    scopes = list(scopes or DEFAULT_SCOPES)
    raw = json.loads(credentials_path.read_text())
    if raw.get("type") == "service_account":
        return service_account.Credentials.from_service_account_file(str(credentials_path), scopes=scopes)

    if token_path and token_path.exists():
        return user_credentials.Credentials.from_authorized_user_file(str(token_path), scopes=scopes)

    if allow_browser_flow:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes=scopes)
        creds = flow.run_local_server(port=0)
        if token_path:
            token_path.write_text(creds.to_json())
        return creds

    raise ValueError(
        "OAuth 클라이언트 credentials는 token이 필요합니다. token_path를 제공하거나 allow_browser_flow=True로 설정하세요."
    )


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str


class DriveApiError(Exception):
    """Raised when Drive API calls fail."""


class SheetNotFoundError(Exception):
    """Raised when a target sheet tab is missing."""


class SheetHeaderMissingError(Exception):
    """Raised when the expected header row is empty."""


@dataclass
class WriteResult:
    """Metadata about a Sheets write operation."""

    updated_range: Optional[str]
    success_count: int
    failure_count: int
    raw_response: Dict


class DriveClient:
    """Drive API wrapper for listing and copying files."""

    def __init__(self, credentials=None, service=None):
        self.service = service or build("drive", "v3", credentials=credentials)

    def list_srt_files(self, folder_id: str) -> List[DriveFile]:
        query = f"'{folder_id}' in parents and trashed = false"
        fields = "nextPageToken, files(id, name, mimeType)"
        files: List[DriveFile] = []
        page_token: Optional[str] = None
        page_count = 0
        try:
            while True:
                resp = (
                    self.service.files()
                    .list(q=query, pageSize=100, pageToken=page_token, fields=fields)
                    .execute()
                )
                page_count += 1
                page_files = resp.get("files", [])
                if resp.get("nextPageToken") and not page_files:
                    logger.warning("Drive pagination returned a continuation token without files for folder %s", folder_id)
                if page_count > 5 and resp.get("nextPageToken"):
                    logger.warning(
                        "Drive listing for folder %s already spanned %d pages; continuing to fetch remaining pages.",
                        folder_id,
                        page_count,
                    )
                for item in page_files:
                    if item.get("name", "").lower().endswith(".srt"):
                        files.append(DriveFile(id=item["id"], name=item["name"], mime_type=item.get("mimeType", "")))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:  # pragma: no cover - defensive
            raise DriveApiError(f"Drive listing failed for folder {folder_id}") from exc
        return files

    def copy_file(self, file_id: str, destination_folder_id: str, new_name: str) -> DriveFile:
        body = {"name": new_name, "parents": [destination_folder_id]}
        result = self.service.files().copy(fileId=file_id, body=body, fields="id, name, mimeType").execute()
        return DriveFile(id=result["id"], name=result["name"], mime_type=result.get("mimeType", ""))

    def download_file(self, file_id: str) -> str:
        request = self.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        return fh.read().decode("utf-8")


class SheetsClient:
    """Sheets API wrapper to push ExportRow payloads."""

    def __init__(self, credentials=None, service=None):
        self.service = service or build("sheets", "v4", credentials=credentials)

    @staticmethod
    def _execute_with_retry(request, retries: int = 3, base_delay: float = 1.0):
        attempt = 0
        while True:
            try:
                return request.execute()
            except HttpError as exc:
                status = getattr(getattr(exc, "resp", None), "status", None)
                if status in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Sheets API returned %s; retrying in %.1fs (attempt %d/%d)",
                        status,
                        delay,
                        attempt + 1,
                        retries,
                    )
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise

    def write_export_rows(
        self,
        spreadsheet_id: str,
        rows: Iterable[ExportRow],
        start_row: int = 3,
        sheet_name: str = "Sheet1",
    ) -> WriteResult:
        values: List[List[str | int]] = []
        for row in rows:
            values.append(row.sheet_cells)

        sheet_metadata = (
            self.service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets.properties.title")
            .execute()
        )
        sheet_titles = {sheet["properties"]["title"] for sheet in sheet_metadata.get("sheets", [])}
        if sheet_name not in sheet_titles:
            raise SheetNotFoundError(f"Sheet '{sheet_name}' does not exist in spreadsheet {spreadsheet_id}")

        header_row_index = max(1, start_row - 1)
        header_range = f"{sheet_name}!A{header_row_index}:I{header_row_index}"
        header_resp = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=header_range)
            .execute()
        )
        if not header_resp.get("values"):
            raise SheetHeaderMissingError(
                f"Expected header row at {header_range} but no values were returned"
            )

        if not values:
            return WriteResult(updated_range=None, success_count=0, failure_count=0, raw_response={})

        end_row = start_row + len(values) - 1
        target_range = f"{sheet_name}!A{start_row}:I{end_row}"
        body = {"values": values}
        response = self._execute_with_retry(
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                body=body,
            )
        )

        updated_rows = int(response.get("updatedRows", len(values))) if values else 0
        success_count = min(updated_rows, len(values))
        failure_count = max(0, len(values) - success_count)
        return WriteResult(
            updated_range=response.get("updatedRange"),
            success_count=success_count,
            failure_count=failure_count,
            raw_response=response,
        )

    def append_meta_sheet(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        rows: List[List[str]],
    ) -> Dict:
        body = {"values": rows}
        return (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1:Z{len(rows)}",
                valueInputOption="USER_ENTERED",
                body=body,
            )
            .execute()
        )


def prepare_export(
    credentials_path: Path,
    template_sheet_id: str,
    destination_folder_id: str,
    copy_name: str,
    token_path: Optional[Path] = None,
    allow_browser_flow: bool = False,
    credentials=None,
    drive_client: DriveClient | None = None,
):
    """Copy the template sheet into the target Drive folder and return the new sheet ID."""

    if credentials is None and not credentials_path:
        raise ValueError("credentials_path is required when credentials are not supplied")

    creds = credentials or load_credentials(credentials_path, token_path=token_path, allow_browser_flow=allow_browser_flow)
    drive = drive_client or DriveClient(credentials=creds)
    copy = drive.copy_file(template_sheet_id, destination_folder_id, copy_name)
    return copy.id

