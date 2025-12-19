"""PART summary generation helpers."""
from __future__ import annotations

from typing import List, Sequence

from .llm import LLMClient
from .models import Part, PartSummary


def _default_summary_text(part: Part, lecture_titles: Sequence[str]) -> str:
    joined = "; ".join(lecture_titles)
    return f"{part.part_name} 강의 요약: {joined}"


def summarize_parts(
    parts: Sequence[Part],
    llm_client: LLMClient | None = None,
) -> List[PartSummary]:
    """Create PART summaries using LLM or deterministic fallback."""

    summaries: List[PartSummary] = []
    for part in parts:
        if llm_client:
            prompt = (
                f"다음 강의들의 핵심 개념을 5문장 이내로 요약해 주세요.\n"
                f"PART: {part.part_name}\n"
                f"강의 ID: {', '.join(part.lecture_ids)}"
            )
            try:
                result = llm_client.generate_json(
                    prompt,
                    schema={
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    },
                )
                content = result.get("summary") or _default_summary_text(part, part.lecture_ids)
            except Exception:
                content = _default_summary_text(part, part.lecture_ids)
        else:
            content = _default_summary_text(part, part.lecture_ids)

        summaries.append(
            PartSummary(
                part_name=part.part_name,
                content=content,
                token_estimate=len(content.split()),
            )
        )
    return summaries
