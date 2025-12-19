"""Question generation helpers aligned with PRD constraints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .distribution import minimum_distribution
from .models import PartSummary, Question
from .llm import LLMClient


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


def _fallback_question(part_name: str, idx: int, q_type: int, difficulty: int) -> Question:
    if q_type == 1:
        choices = _build_mcq_options(part_name, idx)
        answer_code = 1
    else:
        choices = []
        answer_code = 1

    return Question(
        difficulty_code=difficulty,
        question_type_code=q_type,
        question_text=f"{part_name}의 핵심 내용을 이해했나요? (Q{idx})",
        explanation_text=f"{part_name} 요약을 기반으로 한 확인 질문입니다.",
        answer_code=answer_code,
        options=choices,
        part_name=part_name,
        validity_score=None,
        style_violation_flags=[],
    )


def _normalize_llm_question(
    raw: dict,
    *,
    part_name: str,
    default_difficulty: int,
    position: int,
) -> Question:
    q_type_raw = raw.get("question_type") or raw.get("question_type_code")
    q_type = 1 if str(q_type_raw) in {"1", "mcq", "MCQ"} else 3

    difficulty = int(raw.get("difficulty_code") or default_difficulty)
    answer_code = int(raw.get("answer_code") or 1)
    explanation = raw.get("explanation_text") or raw.get("explanation")
    question_text = raw.get("question_text") or raw.get("question")
    options = raw.get("options") or []

    if q_type == 1 and len(options) != 4:
        options = _build_mcq_options(part_name, position)

    if q_type == 3:
        options = []

    try:
        return Question(
            difficulty_code=difficulty,
            question_type_code=q_type,
            question_text=question_text or f"{part_name} 질문 {position}",
            explanation_text=explanation or f"{part_name} 핵심 확인", 
            answer_code=answer_code,
            options=options,
            part_name=part_name,
            validity_score=None,
            style_violation_flags=[],
        )
    except Exception:
        return _fallback_question(part_name, position, q_type, difficulty)


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
            questions.append(_fallback_question(part_name, counter, q_type, options.difficulty))
            counter += 1

    return questions


def generate_llm_questions(
    summaries: Sequence[PartSummary], options: QuestionGenerationOptions, llm_client: LLMClient
) -> List[Question]:
    """Generate questions via LLM with schema validation and deterministic fallback."""

    options.validate()
    if not summaries:
        return []

    part_names = [summary.part_name for summary in summaries]
    distribution = minimum_distribution(options.total_questions, list(summaries))

    questions: List[Question] = []
    counter = 1
    for summary in summaries:
        planned = distribution.get(summary.part_name, 0)
        if planned <= 0:
            continue

        prompt = (
            "당신은 교육용 문항을 작성하는 전문가입니다.\n"
            "다음 PART 요약을 참고하여 학습자 이해도를 점검할 선다형/ OX형 문항을 만들어 주세요.\n"
            f"PART 이름: {summary.part_name}\n"
            f"요약: {summary.content}\n"
            f"난이도 코드: {options.difficulty}\n"
            f"필요 문항 수: {planned}\n"
            "규칙:\n"
            "- question_type_code는 1(선다형) 또는 3(OX)만 사용합니다.\n"
            "- 선다형은 options 4개와 answer_code 1~4, OX는 options를 비워 두고 answer_code 1(O)/2(X)로 지정합니다.\n"
            "- question_text와 explanation_text는 한국어로 간결하게 작성합니다."
        )
        schema = {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_text": {"type": "string"},
                            "explanation_text": {"type": "string"},
                            "question_type_code": {"type": "integer"},
                            "difficulty_code": {"type": "integer"},
                            "answer_code": {"type": "integer"},
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "question_text",
                            "explanation_text",
                            "question_type_code",
                            "answer_code",
                        ],
                    },
                    "minItems": planned,
                }
            },
            "required": ["questions"],
        }

        try:
            result = llm_client.generate_json(prompt, schema)
            payload_questions = list(result.get("questions", []))
        except Exception:
            payload_questions = []

        if not payload_questions:
            for _ in range(planned):
                q_type = _pick_question_type(counter, options.include_mcq, options.include_ox)
                questions.append(_fallback_question(summary.part_name, counter, q_type, options.difficulty))
                counter += 1
            continue

        for raw_q in payload_questions[:planned]:
            q_type = raw_q.get("question_type_code") or raw_q.get("question_type")
            if q_type == 3 and not options.include_ox:
                q_type = 1
            if q_type == 1 and not options.include_mcq:
                q_type = 3

            normalized_raw = dict(raw_q)
            normalized_raw["question_type_code"] = q_type

            question = _normalize_llm_question(
                normalized_raw,
                part_name=summary.part_name,
                default_difficulty=options.difficulty,
                position=counter,
            )
            questions.append(question)
            counter += 1

    return questions


def generate_questions(
    summaries: Sequence[PartSummary], options: QuestionGenerationOptions, llm_client: LLMClient | None = None
) -> List[Question]:
    """Primary entry point for question generation with optional LLM support."""

    if llm_client:
        return generate_llm_questions(summaries, options, llm_client)
    return generate_stub_questions(summaries, options)
