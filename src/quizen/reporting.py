"""Reporting utilities for meta sheet and persistence."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .models import Part, Question
from .storage import JsonStorage


def build_meta_sheet_rows(parts: List[Part], questions: List[Question]) -> List[List[str]]:
    """Create rows for an optional `quizen_meta` tab.

    The layout groups PART information first, followed by question-to-PART
    mapping to help reviewers or dashboards.
    """

    rows: List[List[str]] = [["part_code", "part_title", "lecture_count", "lecture_ids"]]
    for part in parts:
        lecture_ids = ", ".join(part.lecture_ids)
        rows.append([part.part_code, part.part_title, str(len(part.lecture_ids)), lecture_ids])

    rows.append([])
    rows.append(["#", "part_name", "question_type_code", "difficulty_code", "answer_code"])
    for idx, question in enumerate(questions, start=1):
        rows.append(
            [
                str(idx),
                question.part_name,
                str(question.question_type_code),
                str(question.difficulty_code),
                str(question.answer_code),
            ]
        )
    return rows


def persist_run(storage: JsonStorage, run_id: str, payload: Dict) -> Path:
    """Persist a pipeline run using the provided storage backend."""

    return storage.save(run_id, payload)
