"""Integration-style coverage for run_drive_to_sheet with env guard."""
from __future__ import annotations

import json
import os
import types
from pathlib import Path
from uuid import uuid4

import pytest

from quizen.runner import run_drive_to_sheet


class MockDrive:
    def __init__(self):
        self.credentials = object()
        self.list_calls: list[str] = []
        self.copy_calls: list[tuple[str, str, str]] = []

    def list_srt_files(self, folder_id: str):
        self.list_calls.append(folder_id)
        return [
            types.SimpleNamespace(id="file-1", name="001 intro.srt", mime_type="text/plain"),
            types.SimpleNamespace(id="file-2", name="002 wrap_up.srt", mime_type="text/plain"),
        ]

    def copy_file(self, file_id: str, destination_folder_id: str, new_name: str):
        self.copy_calls.append((file_id, destination_folder_id, new_name))
        return types.SimpleNamespace(id="new-sheet", name=new_name, mime_type="application/vnd.google-apps.spreadsheet")


class MockSheets:
    def __init__(self):
        self.writes = []
        self.meta_writes = []

    def write_export_rows(self, spreadsheet_id, rows, sheet_name="Sheet1"):
        # force evaluation of generator
        self.writes.append((spreadsheet_id, list(rows), sheet_name))
        return {"written": len(self.writes[-1][1])}

    def append_meta_sheet(self, spreadsheet_id, sheet_name, rows):
        self.meta_writes.append((spreadsheet_id, sheet_name, rows))
        return {"written": len(rows)}


@pytest.mark.integration
@pytest.mark.skipif(
    not (
        os.getenv("QUIZEN_GOOGLE_CREDENTIALS_PATH")
        and os.getenv("QUIZEN_SRT_FOLDER_ID")
        and os.getenv("QUIZEN_TEMPLATE_SHEET_ID")
    ),
    reason=(
        "Set QUIZEN_GOOGLE_CREDENTIALS_PATH, QUIZEN_SRT_FOLDER_ID, and QUIZEN_TEMPLATE_SHEET_ID "
        "to run against real Drive/Sheets; otherwise mocked clients are exercised in a separate test"
    ),
)
def test_run_drive_to_sheet_with_real_google(tmp_path):
    creds_path = Path(os.environ["QUIZEN_GOOGLE_CREDENTIALS_PATH"])
    token_path = tmp_path / "token.json"
    result = run_drive_to_sheet(
        credentials_path=creds_path,
        srt_folder_id=os.environ["QUIZEN_SRT_FOLDER_ID"],
        template_sheet_id=os.environ["QUIZEN_TEMPLATE_SHEET_ID"],
        copy_name=f"quizen-ci-{uuid4().hex[:8]}",
        destination_folder_id=os.getenv("QUIZEN_DESTINATION_FOLDER_ID") or os.environ["QUIZEN_SRT_FOLDER_ID"],
        token_path=token_path,
        allow_browser_flow=False,
    )

    assert result["sheet_id"]
    assert result["question_count"] > 0
    assert token_path.exists()


def test_run_drive_to_sheet_with_mock_clients(monkeypatch):
    mock_drive = MockDrive()
    mock_sheets = MockSheets()
    meta_rows = [["meta", "row"]]

    monkeypatch.setattr("quizen.runner.build_meta_sheet_rows", lambda *args, **kwargs: meta_rows)

    result = run_drive_to_sheet(
        credentials_path=None,
        srt_folder_id="folder-mock",
        template_sheet_id="template-mock",
        copy_name="Copy",
        destination_folder_id="dest-mock",
        drive_client=mock_drive,
        sheets_client=mock_sheets,
    )

    assert result["sheet_id"] == "new-sheet"
    assert result["question_count"] == len(mock_sheets.writes[0][1])
    assert mock_drive.copy_calls[0] == ("template-mock", "dest-mock", "Copy")
    assert mock_sheets.meta_writes[0] == ("new-sheet", "quizen_meta", meta_rows)
    # ensure warnings are serializable
    json.dumps(result["warnings"])
