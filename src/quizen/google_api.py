"""Google Drive/Sheets integration helpers."""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from .models import ExportRow


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


class DriveClient:
    """Drive API wrapper for listing and copying files."""

    def __init__(self, credentials=None, service=None):
        self.service = service or build("drive", "v3", credentials=credentials)

    def list_srt_files(self, folder_id: str) -> List[DriveFile]:
        query = f"'{folder_id}' in parents and trashed = false"
        fields = "nextPageToken, files(id, name, mimeType)"
        files: List[DriveFile] = []
        page_token: Optional[str] = None
        while True:
            resp = (
                self.service.files()
                .list(q=query, pageSize=100, pageToken=page_token, fields=fields)
                .execute()
            )
            for item in resp.get("files", []):
                if item.get("name", "").lower().endswith(".srt"):
                    files.append(DriveFile(id=item["id"], name=item["name"], mime_type=item.get("mimeType", "")))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
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

    def write_export_rows(
        self,
        spreadsheet_id: str,
        rows: Iterable[ExportRow],
        start_row: int = 3,
        sheet_name: str = "Sheet1",
    ) -> Dict:
        values: List[List[str | int]] = []
        for row in rows:
            values.append(row.sheet_cells)

        end_row = start_row + len(values) - 1 if values else start_row
        target_range = f"{sheet_name}!A{start_row}:I{end_row}"
        body = {"values": values}
        return (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                body=body,
            )
            .execute()
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

