"""Minimal FastAPI application exposing the pipeline runner."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .models import Lecture
from .pipeline import build_default_runner
from .questions import QuestionGenerationOptions
from .storage import JsonStorage


class LecturePayload(BaseModel):
    order: str
    id: str
    title: str


class RunRequest(BaseModel):
    lectures: list[LecturePayload]
    total_questions: int = Field(10, ge=1)
    difficulty: int = Field(3, ge=1, le=5)
    include_mcq: bool = True
    include_ox: bool = True

    def to_models(self) -> tuple[list[Lecture], QuestionGenerationOptions]:
        lectures = [Lecture(**lecture.model_dump()) for lecture in self.lectures]
        options = QuestionGenerationOptions(
            total_questions=self.total_questions,
            difficulty=self.difficulty,
            include_mcq=self.include_mcq,
            include_ox=self.include_ox,
        )
        return lectures, options


def create_app(storage_dir: str | Path = "./runs", llm_client=None) -> FastAPI:
    storage = JsonStorage(Path(storage_dir))
    app = FastAPI(title="quizen", version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/runs")
    def run_pipeline(req: RunRequest):
        lectures, options = req.to_models()
        run_id = uuid.uuid4().hex
        runner = build_default_runner(lectures, llm_client=llm_client, question_options=options)
        ctx = runner.run()
        storage.save(run_id, ctx.to_dict())
        return {"run_id": run_id, "events": ctx.events.events, "question_count": len(ctx.questions)}

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        try:
            payload = storage.load(run_id)
        except FileNotFoundError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=404, detail=str(exc))
        return payload

    return app
