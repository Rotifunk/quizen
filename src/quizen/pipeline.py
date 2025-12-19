"""Pipeline orchestration skeleton for quizen."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .distribution import rebalance_questions
from .models import ExportRow, Part, PartSummary, Question


@dataclass
class PipelineEvents:
    """Simple in-memory event log collector."""

    events: List[Dict] = field(default_factory=list)

    def push(self, name: str, **payload):
        self.events.append({"event": name, **payload})


@dataclass
class PipelineContext:
    """Shared context for a run."""

    parts: List[Part] = field(default_factory=list)
    summaries: List[PartSummary] = field(default_factory=list)
    questions: List[Question] = field(default_factory=list)
    export_rows: List[ExportRow] = field(default_factory=list)
    events: PipelineEvents = field(default_factory=PipelineEvents)


class PipelineRunner:
    """Coordinates PART classification → summary → question generation → export rows."""

    def __init__(
        self,
        classify_parts: Callable[[], List[Part]],
        summarize_parts: Callable[[List[Part]], List[PartSummary]],
        generate_questions: Callable[[List[PartSummary]], List[Question]],
        map_export_rows: Callable[[List[Question]], List[ExportRow]],
    ):
        self.classify_parts = classify_parts
        self.summarize_parts = summarize_parts
        self.generate_questions = generate_questions
        self.map_export_rows = map_export_rows

    def run(self) -> PipelineContext:
        ctx = PipelineContext()
        ctx.events.push("run_started")

        ctx.parts = self.classify_parts()
        ctx.events.push("part_classification_completed", part_count=len(ctx.parts))

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
