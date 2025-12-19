"""Pipeline orchestration skeleton for quizen."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .distribution import rebalance_questions
from .models import ExportRow, Lecture, Part, PartSummary, Question
from .parts import PartClassifier, PartClassificationResult
from .questions import QuestionGenerationOptions, generate_questions
from .scoring import score_questions
from .summaries import summarize_parts
from .validation import ValidationError, validate_export_rows, validate_question


@dataclass
class PipelineEvents:
    """Simple in-memory event log collector with optional sinks."""

    events: List[Dict] = field(default_factory=list)
    sinks: List[Callable[[Dict], None]] = field(default_factory=list)

    def push(self, name: str, **payload):
        event_payload = {"event": name, **payload}
        self.events.append(event_payload)
        for sink in self.sinks:
            sink(event_payload)


@dataclass
class PipelineContext:
    """Shared context for a run."""

    parts: List[Part] = field(default_factory=list)
    summaries: List[PartSummary] = field(default_factory=list)
    questions: List[Question] = field(default_factory=list)
    export_rows: List[ExportRow] = field(default_factory=list)
    events: PipelineEvents = field(default_factory=PipelineEvents)

    def to_dict(self) -> Dict:
        return {
            "parts": [p.model_dump() for p in self.parts],
            "summaries": [s.model_dump() for s in self.summaries],
            "questions": [q.model_dump() for q in self.questions],
            "export_rows": [r.model_dump() for r in self.export_rows],
            "events": list(self.events.events),
        }


class PipelineRunner:
    """Coordinates PART classification → summary → question generation → export rows."""

    def __init__(
        self,
        classify_parts: Callable[[], List[Part]],
        summarize_parts: Callable[[List[Part]], List[PartSummary]],
        generate_questions: Callable[[List[PartSummary]], List[Question]],
        map_export_rows: Callable[[List[Question]], List[ExportRow]],
        event_sinks: Optional[List[Callable[[Dict], None]]] = None,
    ):
        self.classify_parts = classify_parts
        self.summarize_parts = summarize_parts
        self.generate_questions = generate_questions
        self.map_export_rows = map_export_rows
        self.event_sinks = event_sinks or []

    def run(self) -> PipelineContext:
        ctx = PipelineContext(events=PipelineEvents(sinks=self.event_sinks))
        ctx.events.push("run_started")

        parts_result = self.classify_parts()
        ctx.parts, part_meta = _unwrap_parts(parts_result)
        ctx.events.push(
            "part_classification_completed",
            part_count=len(ctx.parts),
            fallback_used=part_meta.get("fallback_used"),
            warnings=part_meta.get("warnings"),
        )

        ctx.summaries = self.summarize_parts(ctx.parts)
        ctx.events.push("part_summary_completed", token_estimates=[s.token_estimate for s in ctx.summaries])

        questions = self.generate_questions(ctx.summaries)
        ctx.questions = rebalance_questions(questions, ctx.parts)
        ctx.events.push("question_generation_completed", question_count=len(ctx.questions))

        ctx.export_rows = self.map_export_rows(ctx.questions)
        ctx.events.push("export_ready", row_count=len(ctx.export_rows))
        return ctx


def default_export_mapper(questions: List[Question]) -> List[ExportRow]:
    """Convert validated questions to ExportRow payloads."""
    rows: List[ExportRow] = []
    for q in questions:
        validate_question(q)
        options = q.options if q.question_type_code == 1 else []
        rows.append(
            ExportRow(
                difficulty_code=q.difficulty_code,
                question_type_code=q.question_type_code,
                question_text=q.question_text,
                explanation_text=q.explanation_text,
                answer_code=q.answer_code,
                options=options,
            )
        )
    return rows


def _unwrap_parts(result) -> Tuple[List[Part], Dict]:
    if isinstance(result, PartClassificationResult):
        return result.parts, {"fallback_used": result.fallback_used, "warnings": result.warnings}
    if isinstance(result, tuple) and len(result) == 2:
        parts, meta = result
        return parts, meta or {}
    return result, {}


def build_default_runner(
    lectures: List[Lecture],
    llm_client=None,
    question_options: Optional[QuestionGenerationOptions] = None,
) -> PipelineRunner:
    """Wire up the pipeline with deterministic fallbacks for local runs."""

    classifier = PartClassifier(llm_client=llm_client)
    q_options = question_options or QuestionGenerationOptions()

    def _classify():
        return classifier.classify(lectures)

    def _summaries(parts: List[Part]):
        return summarize_parts(parts, llm_client=llm_client)

    def _generate(summaries: List[PartSummary]):
        questions = generate_questions(summaries, q_options, llm_client=llm_client)
        return score_questions(questions, llm_client=llm_client)

    def _export(questions: List[Question]):
        rows = default_export_mapper(questions)
        ok, errors = validate_export_rows(rows)
        if not ok:
            raise ValidationError("; ".join(errors))
        return rows

    return PipelineRunner(
        classify_parts=_classify,
        summarize_parts=_summaries,
        generate_questions=_generate,
        map_export_rows=_export,
    )
