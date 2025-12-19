"""Validity scoring stubs for questions."""
from __future__ import annotations

from typing import List

from .models import Question


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
        question.validity_score = base
        question.style_violation_flags = []
    return questions
