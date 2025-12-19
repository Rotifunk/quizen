"""Reporting utilities for meta sheet and persistence."""
from __future__ import annotations

import json
from statistics import mean
from pathlib import Path
from typing import Dict, List, Sequence

from .models import Part, Question
from .storage import JsonStorage


def _part_score_distribution(parts: Sequence[Part], questions: Sequence[Question]) -> List[Dict]:
    """Aggregate validity score ranges per PART."""

    distribution: List[Dict] = []
    for part in parts:
        part_questions = [q for q in questions if q.part_name == part.part_name]
        scores = [q.validity_score for q in part_questions if q.validity_score is not None]
        below_threshold = sum("below_threshold" in (q.style_violation_flags or []) for q in part_questions)

        distribution.append(
            {
                "part_name": part.part_name,
                "question_count": len(part_questions),
                "average_score": round(mean(scores), 2) if scores else None,
                "min_score": min(scores) if scores else None,
                "max_score": max(scores) if scores else None,
                "below_threshold": below_threshold,
            }
        )
    return distribution


def build_meta_sheet_rows(
    parts: List[Part],
    questions: List[Question],
    *,
    events: Sequence[Dict] | None = None,
    warnings: Sequence[str] | None = None,
    call_results: Sequence[Dict] | None = None,
) -> List[List[str]]:
    """Create rows for an optional `quizen_meta` tab with richer diagnostics."""

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

    rows.append([])
    rows.append(["pipeline_event", "payload"])
    for event in events or []:
        rows.append([event.get("event", ""), json.dumps(event, ensure_ascii=False)])

    rows.append([])
    rows.append(["part_name", "question_count", "average_score", "min_score", "max_score", "below_threshold"])
    for stat in _part_score_distribution(parts, questions):
        rows.append(
            [
                stat["part_name"],
                str(stat["question_count"]),
                "" if stat["average_score"] is None else str(stat["average_score"]),
                "" if stat["min_score"] is None else str(stat["min_score"]),
                "" if stat["max_score"] is None else str(stat["max_score"]),
                str(stat["below_threshold"]),
            ]
        )

    rows.append([])
    rows.append(["warning"])
    for warning in warnings or []:
        rows.append([warning])

    rows.append([])
    rows.append(["service", "operation", "status", "error_code", "message"])
    for result in call_results or []:
        rows.append(
            [
                result.get("service", ""),
                result.get("operation", ""),
                result.get("status", ""),
                result.get("error_code", ""),
                result.get("message", ""),
            ]
        )
    return rows


def persist_run(storage: JsonStorage, run_id: str, payload: Dict) -> Path:
    """Persist a pipeline run using the provided storage backend."""

    return storage.save(run_id, payload)


def build_meta_report(
    parts: List[Part],
    questions: List[Question],
    *,
    events: Sequence[Dict] | None = None,
    warnings: Sequence[str] | None = None,
    call_results: Sequence[Dict] | None = None,
) -> Dict:
    """Structured payload for file logging and API responses."""

    distribution = _part_score_distribution(parts, questions)
    return {
        "events": list(events or []),
        "warnings": list(warnings or []),
        "part_score_distribution": distribution,
        "call_results": list(call_results or []),
        "failed_calls": [result for result in call_results or [] if result.get("status") == "error"],
    }
