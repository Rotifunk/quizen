"""Core data models aligned with PRD v0.5."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Lecture(BaseModel):
    """Lecture metadata parsed from filename."""

    order: str = Field(..., description="Lecture order, zero-padded")
    id: str = Field(..., description="Lecture ID")
    title: str = Field(..., description="Lecture title")
    part_code: Optional[str] = Field(None, description="Assigned part code from classification")
    file_path: Optional[str] = Field(None, description="Full path to SRT file")


class Part(BaseModel):
    """LLM-produced PART grouping."""

    part_code: str = Field(..., description="Formatted as PART.01")
    part_title: str = Field(..., description="Topic title without code")
    part_name: str = Field(..., description="Concatenated code and title")
    lecture_ids: List[str] = Field(default_factory=list)

    @field_validator("part_code")
    def validate_part_code(cls, value: str) -> str:
        if not value.startswith("PART."):
            raise ValueError("part_code must start with 'PART.'")
        suffix = value.split("PART.")[-1]
        if len(suffix) != 2 or not suffix.isdigit():
            raise ValueError("part_code must be zero-padded two digits, e.g., PART.01")
        return value

    @field_validator("part_name")
    def validate_part_name(cls, value: str) -> str:
        if not value.startswith("PART."):
            raise ValueError("part_name must begin with PART code")
        return value


class Question(BaseModel):
    """Internal question schema (PRD §9.2)."""

    difficulty_code: int = Field(..., ge=1, le=5)
    question_type_code: int = Field(..., description="1=MCQ, 3=OX")
    question_text: str
    explanation_text: str
    answer_code: int = Field(..., description="1-4 for MCQ, 1/2 for OX")
    options: List[str] = Field(default_factory=list)
    part_name: str
    validity_score: Optional[float] = Field(None, ge=0, le=100)
    style_violation_flags: List[str] = Field(default_factory=list)

    @field_validator("question_type_code")
    def validate_question_type(cls, value: int) -> int:
        if value not in (1, 3):
            raise ValueError("question_type_code must be 1 (MCQ) or 3 (OX)")
        return value

    @field_validator("answer_code")
    def validate_answer(cls, value: int, info):
        question_type = info.data.get("question_type_code")
        if question_type == 1 and value not in (1, 2, 3, 4):
            raise ValueError("MCQ answers must be 1-4")
        if question_type == 3 and value not in (1, 2):
            raise ValueError("OX answers must be 1 or 2")
        return value

    @field_validator("options")
    def validate_options(cls, value: List[str], info):
        question_type = info.data.get("question_type_code")
        if question_type == 1 and len(value) != 4:
            raise ValueError("MCQ questions require four options")
        if question_type == 3 and value not in ([], None):
            # Allow explicit blanks to remain empty for OX
            raise ValueError("OX questions should have empty options")
        return value


class PartSummary(BaseModel):
    """LLM-generated summary per PART."""

    part_name: str
    content: str
    token_estimate: Optional[int] = None


class ValidityScore(BaseModel):
    """Rubric evaluation per question."""

    total_score: float = Field(..., ge=0, le=100)
    issue_tags: List[str] = Field(default_factory=list)
    improvement: Optional[str] = None


class ExportRow(BaseModel):
    """Row to be written to Google Sheets template."""

    difficulty_code: int
    question_type_code: int
    question_text: str
    explanation_text: str
    answer_code: int
    options: List[str] = Field(default_factory=list)

    @property
    def sheet_cells(self) -> List[str]:
        """Return A-I cell values with padding for options."""
        padded_options = self.options + ["", "", "", ""]
        return [
            str(self.difficulty_code),
            str(self.question_type_code),
            self.question_text,
            self.explanation_text,
            str(self.answer_code),
            *padded_options[:4],
        ]
