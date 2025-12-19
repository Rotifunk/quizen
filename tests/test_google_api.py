import json
from pathlib import Path
from unittest.mock import patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from quizen.google_api import (
    DriveApiError,
    DriveClient,
    SheetHeaderMissingError,
    SheetNotFoundError,
    SheetsClient,
    WriteResult,
    load_credentials,
)
from quizen.models import ExportRow


def test_load_credentials_prefers_service_account(tmp_path: Path):
    creds_path = tmp_path / "service.json"
    creds_path.write_text(json.dumps({"type": "service_account"}))

    with patch("quizen.google_api.service_account.Credentials.from_service_account_file") as mock_service:
        mock_service.return_value = object()
        result = load_credentials(creds_path)

    mock_service.assert_called_once()
    assert result is mock_service.return_value


def test_load_credentials_uses_token_for_oauth(tmp_path: Path):
    creds_path = tmp_path / "oauth.json"
    creds_path.write_text(json.dumps({"web": {"client_id": "abc"}}))
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")

    with patch("quizen.google_api.user_credentials.Credentials.from_authorized_user_file") as mock_user:
        mock_user.return_value = object()
        result = load_credentials(creds_path, token_path=token_path)

    mock_user.assert_called_once()
    assert result is mock_user.return_value


class _FakeGetResponse:
    def __init__(self, sheet_names):
        self.sheet_names = sheet_names

    def execute(self):
        return {"sheets": [{"properties": {"title": name}} for name in self.sheet_names]}


class _FakeValues:
    def __init__(self, *, header_present=True, updated_rows=None, raise_on_execute: list[HttpError] | None = None):
        self.updated_with = None
        self.header_present = header_present
        self.updated_rows = updated_rows
        self._mode = None
        self.raise_on_execute = raise_on_execute or []
        self.get_calls = []

    def get(self, spreadsheetId, range):
        self._mode = "get"
        self.get_calls.append({"spreadsheetId": spreadsheetId, "range": range})
        return self

    def update(self, spreadsheetId, range, valueInputOption, body):
        self._mode = "update"
        self.updated_with = {
            "spreadsheetId": spreadsheetId,
            "range": range,
            "valueInputOption": valueInputOption,
            "body": body,
        }
        return self

    def execute(self):
        if self.raise_on_execute and self._mode == "update":
            exc = self.raise_on_execute.pop(0)
            raise exc
        if self._mode == "get":
            return {"values": [["h"]] if self.header_present else []}
        if self._mode == "update":
            updated_rows = self.updated_rows
            if updated_rows is None:
                updated_rows = len(self.updated_with["body"]["values"])
            return {"updatedRange": self.updated_with["range"], "updatedRows": updated_rows}
        raise AssertionError("Unknown mode for _FakeValues")


class _FakeSpreadsheets:
    def __init__(self, *, sheet_names=None, header_present=True, updated_rows=None, raise_on_execute=None):
        self.sheet_names = sheet_names or ["Sheet1"]
        self._values = _FakeValues(
            header_present=header_present, updated_rows=updated_rows, raise_on_execute=raise_on_execute
        )
        self.get_calls = []

    def values(self):
        return self._values

    def get(self, spreadsheetId, fields):
        self.get_calls.append({"spreadsheetId": spreadsheetId, "fields": fields})
        return _FakeGetResponse(self.sheet_names)


class _FakeSheetsService:
    def __init__(self, *, sheet_names=None, header_present=True, updated_rows=None, raise_on_execute=None):
        self._spreadsheets = _FakeSpreadsheets(
            sheet_names=sheet_names,
            header_present=header_present,
            updated_rows=updated_rows,
            raise_on_execute=raise_on_execute,
        )

    def spreadsheets(self):
        return self._spreadsheets


def test_write_export_rows_builds_sheet_cells():
    sheet_service = _FakeSheetsService(sheet_names=["Export"])
    client = SheetsClient(service=sheet_service)

    rows = [
        ExportRow(
            difficulty_code=3,
            question_type_code=1,
            question_text="Q1",
            explanation_text="E1",
            answer_code=2,
            options=["A", "B", "C", "D"],
        ),
        ExportRow(
            difficulty_code=2,
            question_type_code=3,
            question_text="Q2",
            explanation_text="E2",
            answer_code=1,
            options=[],
        ),
    ]

    result = client.write_export_rows("sheet123", rows, start_row=3, sheet_name="Export")

    assert isinstance(result, WriteResult)
    assert result.updated_range == "Export!A3:I4"
    assert result.success_count == 2
    assert result.failure_count == 0
    expected_body = {
        "values": [
            ["3", "1", "Q1", "E1", "2", "A", "B", "C", "D"],
            ["2", "3", "Q2", "E2", "1", "", "", "", ""],
        ]
    }
    assert sheet_service.spreadsheets().values().updated_with["body"] == expected_body


def test_write_export_rows_validates_sheet_and_header():
    sheet_service = _FakeSheetsService(sheet_names=["Other"])
    client = SheetsClient(service=sheet_service)

    with pytest.raises(SheetNotFoundError):
        client.write_export_rows("sheet123", [], start_row=3, sheet_name="Missing")

    sheet_service = _FakeSheetsService(sheet_names=["Export"], header_present=False)
    client = SheetsClient(service=sheet_service)
    with pytest.raises(SheetHeaderMissingError):
        client.write_export_rows("sheet123", [], start_row=3, sheet_name="Export")


def test_write_export_rows_retries_and_reports_partial_success():
    http_error = HttpError(Response({"status": 429}), b"throttle")
    sheet_service = _FakeSheetsService(
        sheet_names=["Export"],
        updated_rows=1,
        raise_on_execute=[http_error],
    )
    client = SheetsClient(service=sheet_service)

    rows = [
        ExportRow(
            difficulty_code=3,
            question_type_code=1,
            question_text="Q1",
            explanation_text="E1",
            answer_code=2,
            options=["A", "B", "C", "D"],
        ),
        ExportRow(
            difficulty_code=2,
            question_type_code=3,
            question_text="Q2",
            explanation_text="E2",
            answer_code=1,
            options=[],
        ),
    ]

    result = client.write_export_rows("sheet123", rows, start_row=3, sheet_name="Export")
    assert result.success_count == 1
    assert result.failure_count == 1


class _FakeFiles:
    def __init__(self, payloads, *, next_tokens=None, raise_on_execute: list[HttpError] | None = None):
        self.payloads = payloads if isinstance(payloads, list) else [payloads]
        self.next_tokens = next_tokens or [None] * len(self.payloads)
        self.requests = []
        self.raise_on_execute = raise_on_execute or []
        self.index = 0

    def list(self, **kwargs):
        self.requests.append(kwargs)
        return self

    def copy(self, **kwargs):
        self.requests.append({"copy": kwargs})
        return self

    def execute(self):
        if self.raise_on_execute:
            exc = self.raise_on_execute.pop(0)
            raise exc
        if self.requests and "copy" in self.requests[-1]:
            return {"id": "copy123", "name": "copied", "mimeType": "application/vnd.google-apps.spreadsheet"}
        payload = self.payloads[self.index]
        next_token = self.next_tokens[self.index] if self.index < len(self.next_tokens) else None
        self.index = min(self.index + 1, len(self.payloads) - 1)
        return {"files": payload, "nextPageToken": next_token}


class _FakeDriveService:
    def __init__(self, payloads, *, next_tokens=None, raise_on_execute=None):
        self._files = _FakeFiles(payloads, next_tokens=next_tokens, raise_on_execute=raise_on_execute)

    def files(self):
        return self._files


def test_list_srt_and_copy_file_filters_and_copies():
    files_payload = [
        {"id": "1", "name": "lecture.srt", "mimeType": "text/plain"},
        {"id": "2", "name": "skip.txt", "mimeType": "text/plain"},
    ]
    service = _FakeDriveService([files_payload])
    client = DriveClient(service=service)

    files = client.list_srt_files("folder123")
    assert len(files) == 1
    assert files[0].id == "1"

    copy = client.copy_file("source", "dest", "new-name")
    assert copy.id == "copy123"


def test_list_srt_files_warns_on_empty_pagination(caplog):
    caplog.set_level("WARNING")
    payloads = [[], []]
    next_tokens = ["token", None]
    service = _FakeDriveService(payloads, next_tokens=next_tokens)
    client = DriveClient(service=service)

    files = client.list_srt_files("folder123")
    assert files == []
    assert any("continuation token without files" in record.message for record in caplog.records)


def test_list_srt_files_raises_drive_error_on_http_failure():
    http_error = HttpError(Response({"status": 500}), b"error")
    service = _FakeDriveService([], raise_on_execute=[http_error])
    client = DriveClient(service=service)

    with pytest.raises(DriveApiError):
        client.list_srt_files("folder123")

