import types
from pathlib import Path

import pytest

from quizen.models import Lecture
from quizen.runner import build_lectures_from_drive, run_drive_to_sheet


class FakeDrive:
    def __init__(self, creds=None):
        self.list_calls = []
        self.copy_calls = []
        self.credentials = creds

    def list_srt_files(self, folder_id: str):
        self.list_calls.append(folder_id)
        return [
            types.SimpleNamespace(id="1", name="001 lecA Title.srt", mime_type="text/plain"),
            types.SimpleNamespace(id="2", name="002 badname.srt", mime_type="text/plain"),
        ]

    def copy_file(self, file_id: str, destination_folder_id: str, new_name: str):
        self.copy_calls.append((file_id, destination_folder_id, new_name))
        return types.SimpleNamespace(id="new-sheet", name=new_name, mime_type="application/vnd.google-apps.spreadsheet")


class FakeSheets:
    def __init__(self):
        self.writes = []

    def write_export_rows(self, spreadsheet_id, rows, sheet_name="Sheet1"):
        self.writes.append((spreadsheet_id, list(rows), sheet_name))
        return {"written": len(rows)}


class StubCredentials:
    pass


class StubTokenLoader:
    def __init__(self, creds):
        self.creds = creds

    def __call__(self, *_args, **_kwargs):
        return self.creds


def test_build_lectures_from_drive_parses_and_sorts(monkeypatch):
    drive = FakeDrive()
    lectures, warnings = build_lectures_from_drive(drive, "folder-1")

    assert [lec.id for lec in lectures] == ["lecA", "002 badname"]
    assert lectures[0].order == "001"
    assert warnings  # malformed second filename should emit warning


def test_run_drive_to_sheet_uses_clients_and_returns_result(monkeypatch):
    fake_creds = StubCredentials()
    fake_drive = FakeDrive(fake_creds)
    fake_sheets = FakeSheets()

    # Patch load_credentials to avoid file I/O
    monkeypatch.setattr("quizen.runner.load_credentials", StubTokenLoader(fake_creds))

    result = run_drive_to_sheet(
        credentials_path=Path("/tmp/creds.json"),
        srt_folder_id="folder-xyz",
        template_sheet_id="template-123",
        copy_name="Copy",
        destination_folder_id="dest-789",
        drive_client=fake_drive,
        sheets_client=fake_sheets,
    )

    assert result["sheet_id"] == "new-sheet"
    assert result["question_count"] > 0
    assert fake_drive.copy_calls[0][1] == "dest-789"
    assert fake_sheets.writes[0][0] == "new-sheet"
    assert fake_sheets.writes[0][2] == "Sheet1"
