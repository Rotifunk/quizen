"""Validity scoring stubs for questions."""
from __future__ import annotations

from typing import List

from .models import Question


def _detect_style_flags(question: Question) -> list[str]:
    flags: list[str] = []
    polite_endings = ("습니다", "합니다", "하십시오", "합니까", "입니까")
    if question.question_type_code == 1 and not question.question_text.endswith("시오."):
        flags.append("mcq_prompt_style")
    if question.question_type_code == 3 and not question.question_text.endswith("다."):
        flags.append("ox_tone")
    if question.explanation_text and not question.explanation_text.rstrip().endswith(polite_endings):
        flags.append("explanation_tone")
    return flags


def score_questions(questions: List[Question]) -> List[Question]:
    """Assign a simple validity score placeholder.

    The function avoids LLM calls while preserving the schema expected by
    downstream consumers. A lightweight heuristic gives slightly lower scores
    to OX형 문항 to encourage follow-up review.
    """

    for question in questions:
        base = 85.0
        if question.question_type_code == 3:
            base = 80.0
        style_flags = _detect_style_flags(question)
        if style_flags:
            base -= 5
        question.validity_score = base
        question.style_violation_flags = style_flags
    return questions
