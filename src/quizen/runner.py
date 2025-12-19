"""High-level helpers to pull SRTs from Drive and push results to Sheets."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .google_api import DriveClient, SheetsClient, load_credentials, prepare_export
from .models import Lecture
from .parsing import parse_filename
from .pipeline import CallResultCollector, PipelineContext, build_default_runner
from .questions import QuestionGenerationOptions
from .reporting import build_meta_report, build_meta_sheet_rows


def build_lectures_from_drive(drive: DriveClient, folder_id: str) -> Tuple[List[Lecture], List[str]]:
    """List SRT files in a Drive folder and parse them into Lecture models."""

    files = drive.list_srt_files(folder_id)
    lectures: List[Lecture] = []
    warnings: List[str] = []

    for file in files:
        lecture, lecture_warnings = parse_filename(Path(file.name))
        lecture.file_path = file.name
        lectures.append(lecture)
        warnings.extend(lecture_warnings)

    lectures.sort(key=lambda lec: (lec.order or "999", lec.title))
    return lectures, warnings


def run_drive_to_sheet(
    *,
    credentials_path: Path | None,
    srt_folder_id: str,
    template_sheet_id: str,
    copy_name: str,
    destination_folder_id: Optional[str] = None,
    token_path: Optional[Path] = None,
    allow_browser_flow: bool = False,
    llm_client=None,
    question_options: Optional[QuestionGenerationOptions] = None,
    drive_client: Optional[DriveClient] = None,
    sheets_client: Optional[SheetsClient] = None,
    sheet_name: str = "Sheet1",
    write_meta_sheet: bool = True,
    meta_sheet_name: str = "quizen_meta",
) -> Dict:
    """End-to-end helper: Drive SRT ingest → pipeline → Sheets export."""

    if (drive_client is None or sheets_client is None) and credentials_path is None:
        raise ValueError("credentials_path is required when clients are not provided")

    destination_folder = destination_folder_id or srt_folder_id
    creds = None
    if drive_client is None or sheets_client is None:
        creds = load_credentials(credentials_path, token_path=token_path, allow_browser_flow=allow_browser_flow)

    drive = drive_client or DriveClient(credentials=creds)
    sheets = sheets_client or SheetsClient(credentials=creds)
    if creds is None:
        creds = getattr(drive, "credentials", None)

    call_logger = CallResultCollector()

    try:
        lectures, warnings = build_lectures_from_drive(drive, srt_folder_id)
        call_logger.log("drive", "list_srt_files", status="success")
    except Exception as exc:  # pragma: no cover - propagated
        call_logger.log(
            "drive", "list_srt_files", status="error", error_code=exc.__class__.__name__, message=str(exc)
        )
        raise

    runner = build_default_runner(
        lectures,
        llm_client=llm_client,
        question_options=question_options,
        call_logger=call_logger,
    )
    ctx: PipelineContext = runner.run()

    # Copy template sheet into Drive and write results
    try:
        new_sheet_id = prepare_export(
            credentials_path=credentials_path if credentials_path else Path(""),
            template_sheet_id=template_sheet_id,
            destination_folder_id=destination_folder,
            copy_name=copy_name,
            token_path=token_path,
            allow_browser_flow=allow_browser_flow,
            credentials=creds,
            drive_client=drive,
        )
        call_logger.log("drive", "copy_template", status="success")
    except Exception as exc:  # pragma: no cover - propagated
        call_logger.log(
            "drive",
            "copy_template",
            status="error",
            error_code=exc.__class__.__name__,
            message=str(exc),
        )
        raise

    try:
        sheets.write_export_rows(new_sheet_id, ctx.export_rows, sheet_name=sheet_name)
        call_logger.log("sheets", "write_export_rows", status="success")
    except Exception as exc:  # pragma: no cover - propagated
        call_logger.log(
            "sheets",
            "write_export_rows",
            status="error",
            error_code=exc.__class__.__name__,
            message=str(exc),
        )
        raise

    if write_meta_sheet:
        meta_rows = build_meta_sheet_rows(
            ctx.parts,
            ctx.questions,
            events=ctx.events.events,
            warnings=warnings + ctx.warnings,
            call_results=ctx.call_results.results,
        )
        sheets.append_meta_sheet(new_sheet_id, sheet_name=meta_sheet_name, rows=meta_rows)
        call_logger.log("sheets", "append_meta_sheet", status="success")

    meta_report = build_meta_report(
        ctx.parts,
        ctx.questions,
        events=ctx.events.events,
        warnings=warnings + ctx.warnings,
        call_results=ctx.call_results.results,
    )

    return {
        "sheet_id": new_sheet_id,
        "question_count": len(ctx.export_rows),
        "warnings": warnings + ctx.warnings,
        "events": ctx.events.events,
        "call_results": ctx.call_results.results,
        "call_failures": ctx.call_results.failures,
        "meta_report": meta_report,
    }

