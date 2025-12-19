"""Validity scoring utilities for questions."""
from __future__ import annotations

from typing import List, Sequence

from .models import Question

THRESHOLD_FLAG = "below_threshold"

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

def _build_rubric_prompt(questions: Sequence[Question]) -> str:
    entries = []
    for idx, q in enumerate(questions, start=1):
        options = " | ".join(q.options) if q.options else "(OX)"
        entries.append(
            f"[{idx}] {q.part_name}\n문항: {q.question_text}\n해설: {q.explanation_text}\n선지/정답: {options} / {q.answer_code}"
        )
    rubric = (
        "당신은 교육용 문항을 평가하는 심사위원입니다.\n"
        "각 문항을 0~100 사이 점수로 평가하고, 문제 유형이나 표현상의 이슈 태그, 개선 문장을 제시하세요.\n"
        "응답은 JSON으로 반환하세요."
    )
    return f"{rubric}\n\n" + "\n\n".join(entries)


def _assign_scores_from_payload(
    questions: List[Question], payload: dict, threshold: float
) -> List[Question]:
    scores = list(payload.get("scores", []))
    for idx, question in enumerate(questions):
        result = scores[idx] if idx < len(scores) else {}
        score = float(result.get("total_score", 0.0))
        flags = list(result.get("issue_tags", []))
        improvement = result.get("improvement")
        if improvement:
            flags.append(f"improvement: {improvement}")
        if score < threshold:
            flags.append(THRESHOLD_FLAG)
        question.validity_score = score
        question.style_violation_flags = flags
    return questions


def score_questions(
    questions: List[Question], llm_client=None, threshold: float = 75.0
) -> List[Question]:
    """Assign validity scores via LLM rubric when available.

    Falls back to deterministic heuristic scores when the LLM is unavailable or
    raises an error. When an LLM score falls below ``threshold``, a
    ``below_threshold`` flag is added to ``style_violation_flags`` to aid
    downstream filtering.
    """

    if llm_client:
        schema = {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "total_score": {"type": "number"},
                            "issue_tags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "improvement": {"type": "string"},
                        },
                        "required": ["total_score"],
                    },
                }
            },
            "required": ["scores"],
        }

        try:
            prompt = _build_rubric_prompt(questions)
            payload = llm_client.generate_json(prompt, schema)
            return _assign_scores_from_payload(questions, payload, threshold)
        except Exception:
            # Fall through to deterministic scoring
            pass

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
