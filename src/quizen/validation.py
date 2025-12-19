"""Validation helpers for questions and export rows."""
from __future__ import annotations

from typing import List, Tuple

from .models import ExportRow, Question


class ValidationError(Exception):
    """Raised when export validation fails."""


MCQ_ANSWER_RANGE = {1, 2, 3, 4}
OX_ANSWER_RANGE = {1, 2}


def validate_question(question: Question) -> None:
    """Validate a single question against PRD constraints."""
    if question.question_type_code == 1:
        if len(question.options) != 4:
            raise ValidationError("MCQ must have exactly four options")
        if question.answer_code not in MCQ_ANSWER_RANGE:
            raise ValidationError("MCQ answer must be between 1 and 4")
    if question.question_type_code == 3:
        if question.answer_code not in OX_ANSWER_RANGE:
            raise ValidationError("OX answer must be 1 or 2")
        if question.options not in ([], None):
            raise ValidationError("OX options should be empty")


def validate_export_rows(rows: List[ExportRow]) -> Tuple[bool, List[str]]:
    """Validate rows before writing into Google Sheets template."""
    errors: List[str] = []
    for idx, row in enumerate(rows, start=3):  # spreadsheet rows start at 3
        if row.difficulty_code not in {1, 2, 3, 4, 5}:
            errors.append(f"Row {idx}: difficulty must be 1-5")
        if row.question_type_code not in {1, 3}:
            errors.append(f"Row {idx}: question_type must be 1 or 3")
        if row.question_type_code == 1:
            if len(row.options) != 4:
                errors.append(f"Row {idx}: MCQ must have 4 options")
            if row.answer_code not in MCQ_ANSWER_RANGE:
                errors.append(f"Row {idx}: MCQ answer must be 1-4")
        if row.question_type_code == 3:
            if row.answer_code not in OX_ANSWER_RANGE:
                errors.append(f"Row {idx}: OX answer must be 1 or 2")
    return (len(errors) == 0), errors
