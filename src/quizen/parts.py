"""PART classification helpers and fallback logic.

The functions in this module follow PRD v0.5 requirements:
- Enforce the naming rule `PART.01 {파트 주제}` with zero-padded codes.
- Ensure every lecture is assigned exactly once.
- Provide a deterministic fallback split when the LLM response is
  unavailable or invalid.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .llm import LLMClient
from .models import Lecture, Part


PARTS_SCHEMA: Dict = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part_code": {"type": "string"},
                    "part_title": {"type": "string"},
                    "part_name": {"type": "string"},
                    "lecture_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["part_code", "part_title", "part_name", "lecture_ids"],
            },
        }
    },
    "required": ["parts"],
}


def build_classification_prompt(lectures: List[Lecture]) -> str:
    """Construct a compact instruction for Gemini JSON mode."""

    rows = [
        f"- {lec.order or '???'} | {lec.id} | {lec.title}"
        for lec in lectures
    ]
    lecture_list = "\n".join(rows)
    return (
        "강의명을 PART 단위로 묶어 주세요. 출력은 JSON, 스키마 parts[]. "
        "명명 규칙: PART.01 {파트 주제}. 모든 강의는 정확히 1개 PART에 포함.\n"
        f"강의 목록:\n{lecture_list}"
    )


def _normalize_part_payload(payload: Dict) -> Part:
    return Part(
        part_code=payload["part_code"],
        part_title=payload["part_title"],
        part_name=payload["part_name"],
        lecture_ids=payload.get("lecture_ids", []),
    )


def _validate_parts(parts: List[Part], lectures: List[Lecture]) -> List[str]:
    errors: List[str] = []
    lecture_ids = {lec.id for lec in lectures}
    assigned_counts: Dict[str, int] = {lec_id: 0 for lec_id in lecture_ids}

    for part in parts:
        if not part.part_code.startswith("PART."):
            errors.append(f"Invalid part_code: {part.part_code}")
        if not part.part_name.startswith(part.part_code):
            errors.append(f"part_name must prefix part_code: {part.part_name}")
        for lec_id in part.lecture_ids:
            if lec_id not in assigned_counts:
                errors.append(f"Unknown lecture_id in parts: {lec_id}")
            else:
                assigned_counts[lec_id] += 1

    missing = [lec_id for lec_id, count in assigned_counts.items() if count == 0]
    duplicates = [lec_id for lec_id, count in assigned_counts.items() if count > 1]
    if missing:
        errors.append(f"Unassigned lectures: {', '.join(sorted(missing))}")
    if duplicates:
        errors.append(f"Lecture assigned to multiple parts: {', '.join(sorted(duplicates))}")
    return errors


def fallback_split_parts(lectures: List[Lecture]) -> List[Part]:
    """Deterministically split lectures into PART buckets.

    The heuristic follows PRD guidance (4~10 parts recommended) while allowing
    smaller courses to keep fewer parts.
    """

    if not lectures:
        return []

    if len(lectures) < 4:
        part_count = len(lectures)
    else:
        part_count = min(10, max(4, (len(lectures) + 19) // 20))

    bucket_size = max(1, len(lectures) // part_count)
    parts: List[Part] = []
    for idx in range(part_count):
        start = idx * bucket_size
        end = (idx + 1) * bucket_size if idx < part_count - 1 else len(lectures)
        bucket = lectures[start:end]
        if not bucket:
            continue
        code = f"PART.{idx + 1:02d}"
        title = f"코스 파트 {idx + 1}"
        parts.append(
            Part(
                part_code=code,
                part_title=title,
                part_name=f"{code} {title}",
                lecture_ids=[lec.id for lec in bucket],
            )
        )
    return parts


@dataclass
class PartClassificationResult:
    parts: List[Part]
    fallback_used: bool
    warnings: List[str]


class PartClassifier:
    """LLM-first PART classifier with schema validation and fallback."""

    def __init__(self, llm_client: Optional[LLMClient] = None, max_retries: int = 1):
        self.llm_client = llm_client
        self.max_retries = max_retries

    def classify(self, lectures: List[Lecture]) -> PartClassificationResult:
        warnings: List[str] = []
        if not lectures:
            return PartClassificationResult(parts=[], fallback_used=False, warnings=[])

        prompt = build_classification_prompt(lectures)
        attempts = 0
        if self.llm_client:
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    raw = self.llm_client.generate_json(prompt, PARTS_SCHEMA)
                    parts_payload = raw.get("parts") or []
                    parts = [_normalize_part_payload(p) for p in parts_payload]
                    errors = _validate_parts(parts, lectures)
                    if errors:
                        warnings.extend(errors)
                        raise ValueError("; ".join(errors))
                    return PartClassificationResult(
                        parts=parts, fallback_used=False, warnings=warnings
                    )
                except Exception as exc:  # noqa: BLE001 - surface all for fallback
                    warnings.append(f"LLM classification failed (attempt {attempts}): {exc}")

        parts = fallback_split_parts(lectures)
        warnings.append("Fallback PART split applied")
        return PartClassificationResult(parts=parts, fallback_used=True, warnings=warnings)
