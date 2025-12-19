"""Question generation helpers aligned with PRD constraints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .distribution import minimum_distribution
from .models import PartSummary, Question


@dataclass
class QuestionGenerationOptions:
    difficulty: int = 3
    total_questions: int = 10
    include_mcq: bool = True
    include_ox: bool = True

    def validate(self) -> None:
        if self.difficulty not in {1, 2, 3, 4, 5}:
            raise ValueError("difficulty must be 1~5")
        if self.total_questions <= 0:
            raise ValueError("total_questions must be positive")
        if not (self.include_mcq or self.include_ox):
            raise ValueError("At least one question type must be enabled")


def _pick_question_type(part_index: int, allow_mcq: bool, allow_ox: bool) -> int:
    if allow_mcq and allow_ox:
        return 1 if part_index % 2 == 0 else 3
    if allow_mcq:
        return 1
    return 3


def _build_mcq_options(part_name: str, idx: int) -> List[str]:
    return [
        f"{part_name} 핵심 개념 {idx} 요약",  # plausible distractor
        f"{part_name} 사례 {idx}",
        f"{part_name} 정의 {idx}",
        f"{part_name} 오해 {idx}",
    ]


def generate_stub_questions(
    summaries: Sequence[PartSummary], options: QuestionGenerationOptions
) -> List[Question]:
    """Produce PRD-compliant placeholder questions.

    The function does not call LLMs; it guarantees schema validity and basic
    PART coverage so downstream export validation succeeds during local runs.
    """

    options.validate()
    if not summaries:
        return []

    part_names = [summary.part_name for summary in summaries]
    distribution = minimum_distribution(options.total_questions, list(summaries))

    questions: List[Question] = []
    counter = 1
    for part_idx, part_name in enumerate(part_names):
        planned = distribution.get(part_name, 0)
        for _ in range(planned):
            q_type = _pick_question_type(part_idx, options.include_mcq, options.include_ox)
            if q_type == 1:
                choices = _build_mcq_options(part_name, counter)
                answer_code = 1  # deterministic single answer
            else:
                choices = []
                answer_code = 1

            questions.append(
                Question(
                    difficulty_code=options.difficulty,
                    question_type_code=q_type,
                    question_text=f"{part_name}의 핵심 내용을 이해했나요? (Q{counter})",
                    explanation_text=f"{part_name} 요약을 기반으로 한 확인 질문입니다.",
                    answer_code=answer_code,
                    options=choices,
                    part_name=part_name,
                    validity_score=None,
                    style_violation_flags=[],
                )
            )
            counter += 1

    return questions
