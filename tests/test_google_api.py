import json
from pathlib import Path
from unittest.mock import patch

from quizen.google_api import DriveClient, SheetsClient, load_credentials
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


class _FakeValues:
    def __init__(self):
        self.updated_with = None

    def update(self, spreadsheetId, range, valueInputOption, body):
        self.updated_with = {
            "spreadsheetId": spreadsheetId,
            "range": range,
            "valueInputOption": valueInputOption,
            "body": body,
        }
        return self

    def execute(self):
        return {"updatedRange": self.updated_with["range"]}


class _FakeSpreadsheets:
    def __init__(self):
        self._values = _FakeValues()

    def values(self):
        return self._values


class _FakeSheetsService:
    def __init__(self):
        self._spreadsheets = _FakeSpreadsheets()

    def spreadsheets(self):
        return self._spreadsheets


def test_write_export_rows_builds_sheet_cells():
    sheet_service = _FakeSheetsService()
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

    response = client.write_export_rows("sheet123", rows, start_row=3, sheet_name="Export")

    assert response["updatedRange"] == "Export!A3:I4"
    expected_body = {
        "values": [
            ["3", "1", "Q1", "E1", "2", "A", "B", "C", "D"],
            ["2", "3", "Q2", "E2", "1", "", "", "", ""],
        ]
    }
    assert sheet_service.spreadsheets().values().updated_with["body"] == expected_body


class _FakeFiles:
    def __init__(self, payloads):
        self.payloads = payloads
        self.requests = []

    def list(self, **kwargs):
        self.requests.append(kwargs)
        return self

    def copy(self, **kwargs):
        self.requests.append({"copy": kwargs})
        return self

    def execute(self):
        if self.requests and "copy" in self.requests[-1]:
            return {"id": "copy123", "name": "copied", "mimeType": "application/vnd.google-apps.spreadsheet"}
        return {"files": self.payloads}


class _FakeDriveService:
    def __init__(self, payloads):
        self._files = _FakeFiles(payloads)

    def files(self):
        return self._files


def test_list_srt_and_copy_file_filters_and_copies():
    files_payload = [
        {"id": "1", "name": "lecture.srt", "mimeType": "text/plain"},
        {"id": "2", "name": "skip.txt", "mimeType": "text/plain"},
    ]
    service = _FakeDriveService(files_payload)
    client = DriveClient(service=service)

    files = client.list_srt_files("folder123")
    assert len(files) == 1
    assert files[0].id == "1"

    copy = client.copy_file("source", "dest", "new-name")
    assert copy.id == "copy123"

