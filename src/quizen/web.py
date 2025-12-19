"""FastAPI application exposing pipeline APIs and HTML review views."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from .models import Lecture, Question
from .pipeline import build_default_runner
from .questions import QuestionGenerationOptions
from .storage import JsonStorage
from .validation import ValidationError, validate_question


class LecturePayload(BaseModel):
    order: str
    id: str
    title: str


class DriveSheetSettings(BaseModel):
    drive_folder_id: Optional[str] = Field(None, description="Drive 폴더 ID")
    template_sheet_id: Optional[str] = Field(None, description="템플릿 Sheet ID")
    copy_name: Optional[str] = Field(None, description="복제본 이름")
    destination_folder_id: Optional[str] = Field(None, description="복제 대상 폴더")


class RunRequest(BaseModel):
    lectures: list[LecturePayload]
    total_questions: int = Field(10, ge=1)
    difficulty: int = Field(3, ge=1, le=5)
    include_mcq: bool = True
    include_ox: bool = True
    drive: DriveSheetSettings | None = None

    def to_models(self) -> tuple[list[Lecture], QuestionGenerationOptions]:
        lectures = [Lecture(**lecture.model_dump()) for lecture in self.lectures]
        options = QuestionGenerationOptions(
            total_questions=self.total_questions,
            difficulty=self.difficulty,
            include_mcq=self.include_mcq,
            include_ox=self.include_ox,
        )
        return lectures, options


class QuestionEditPayload(BaseModel):
    question_text: Optional[str] = None
    explanation_text: Optional[str] = None
    options: Optional[List[str]] = None
    answer_code: Optional[int] = Field(None, ge=1)
    difficulty_code: Optional[int] = Field(None, ge=1, le=5)

    @field_validator("options")
    @classmethod
    def normalize_options(cls, value):
        if value is None:
            return value
        return [opt for opt in value if opt is not None]


def _templates() -> Jinja2Templates:
    root = Path(__file__).parent / "templates"
    return Jinja2Templates(directory=str(root))


def _load_run_or_404(storage: JsonStorage, run_id: str) -> Dict[str, Any]:
    try:
        return storage.load(run_id)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc))


def _filter_questions(
    questions: Iterable[Dict[str, Any]],
    *,
    part_name: str | None = None,
    question_type: int | None = None,
    min_score: float | None = None,
    style_only: bool = False,
    search: str | None = None,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for q in questions:
        if part_name and q.get("part_name") != part_name:
            continue
        if question_type and q.get("question_type_code") != question_type:
            continue
        if min_score is not None:
            score = q.get("validity_score")
            if score is None or score < min_score:
                continue
        if style_only and not q.get("style_violation_flags"):
            continue
        if search:
            blob = f"{q.get('question_text','')} {q.get('explanation_text','')}".lower()
            if search.lower() not in blob:
                continue
        filtered.append(q)
    return filtered


def _sort_questions(questions: List[Dict[str, Any]], sort_by: str | None, order: str | None) -> List[Dict[str, Any]]:
    if not sort_by:
        return questions
    reverse = order == "desc"
    key_map = {
        "part": "part_name",
        "difficulty": "difficulty_code",
        "validity": "validity_score",
    }
    key = key_map.get(sort_by, sort_by)
    return sorted(questions, key=lambda q: q.get(key) or 0, reverse=reverse)


def _apply_question_edit(question: Dict[str, Any], payload: QuestionEditPayload) -> Question:
    edited = dict(question)
    if payload.question_text is not None:
        edited["question_text"] = payload.question_text
    if payload.explanation_text is not None:
        edited["explanation_text"] = payload.explanation_text
    if payload.options is not None:
        edited["options"] = payload.options
    if payload.answer_code is not None:
        edited["answer_code"] = payload.answer_code
    if payload.difficulty_code is not None:
        edited["difficulty_code"] = payload.difficulty_code

    model = Question(**edited)
    validate_question(model)
    return model


def create_app(storage_dir: str | Path = "./runs", llm_client=None) -> FastAPI:
    storage = JsonStorage(Path(storage_dir))
    app = FastAPI(title="quizen", version="0.1.0")
    templates = _templates()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "defaults": {
                    "total_questions": 10,
                    "difficulty": 3,
                    "include_mcq": True,
                    "include_ox": True,
                },
            },
        )

    @app.post("/runs")
    def run_pipeline(req: RunRequest):
        lectures, options = req.to_models()
        run_id = uuid.uuid4().hex
        runner = build_default_runner(lectures, llm_client=llm_client, question_options=options)
        try:
            ctx = runner.run()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        payload = ctx.to_dict()
        payload["request"] = req.model_dump()
        storage.save(run_id, payload)
        return {"run_id": run_id, "events": ctx.events.events, "question_count": len(ctx.questions)}

    @app.post("/runs/form", response_class=HTMLResponse)
    async def run_pipeline_from_form(
        request: Request,
        drive_folder_id: str = Form(""),
        template_sheet_id: str = Form(""),
        copy_name: str = Form(""),
        destination_folder_id: str = Form(""),
        lectures_json: str = Form(""),
        total_questions: int = Form(10),
        difficulty: int = Form(3),
        include_mcq: Optional[str] = Form(None),
        include_ox: Optional[str] = Form(None),
    ):
        try:
            lecture_payloads = json.loads(lectures_json or "[]")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid lectures JSON: {exc}")

        req = RunRequest(
            lectures=lecture_payloads,
            total_questions=total_questions,
            difficulty=difficulty,
            include_mcq=bool(include_mcq),
            include_ox=bool(include_ox),
            drive=DriveSheetSettings(
                drive_folder_id=drive_folder_id or None,
                template_sheet_id=template_sheet_id or None,
                copy_name=copy_name or None,
                destination_folder_id=destination_folder_id or None,
            ),
        )
        lectures, options = req.to_models()
        run_id = uuid.uuid4().hex
        runner = build_default_runner(lectures, llm_client=llm_client, question_options=options)
        try:
            ctx = runner.run()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        payload = ctx.to_dict()
        payload["request"] = req.model_dump()
        storage.save(run_id, payload)

        return templates.TemplateResponse(
            request,
            "run_result.html",
            {
                "run_id": run_id,
                "question_count": len(ctx.questions),
                "events": ctx.events.events,
            },
        )

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        return _load_run_or_404(storage, run_id)

    @app.get("/runs/{run_id}/questions")
    def search_questions(
        run_id: str,
        part: str | None = Query(None),
        question_type: int | None = Query(None),
        min_score: float | None = Query(None),
        style_only: bool = Query(False),
        search: str | None = Query(None),
        sort_by: str | None = Query(None, description="part|difficulty|validity"),
        order: str | None = Query("asc"),
    ):
        run = _load_run_or_404(storage, run_id)
        questions = run.get("questions", [])
        filtered = _filter_questions(
            questions,
            part_name=part,
            question_type=question_type,
            min_score=min_score,
            style_only=style_only,
            search=search,
        )
        sorted_q = _sort_questions(filtered, sort_by, order)
        return {"run_id": run_id, "count": len(sorted_q), "questions": sorted_q}

    @app.patch("/runs/{run_id}/questions/{index}")
    def edit_question(run_id: str, index: int, payload: QuestionEditPayload):
        run = _load_run_or_404(storage, run_id)
        questions: List[Dict[str, Any]] = list(run.get("questions", []))
        try:
            original = questions[index]
        except IndexError:
            raise HTTPException(status_code=404, detail="Question not found")

        try:
            updated = _apply_question_edit(original, payload)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=400, detail=str(exc))

        questions[index] = updated.model_dump()
        run["questions"] = questions
        storage.save(run_id, run)
        return {"run_id": run_id, "index": index, "question": questions[index]}

    @app.get("/runs/{run_id}/review", response_class=HTMLResponse)
    def review_run(
        request: Request,
        run_id: str,
        part: str | None = Query(None),
        question_type: int | None = Query(None),
        min_score: float | None = Query(None),
        style_only: bool = Query(False),
        search: str | None = Query(None),
    ):
        run = _load_run_or_404(storage, run_id)
        questions = run.get("questions", [])
        filtered = _filter_questions(
            questions,
            part_name=part,
            question_type=question_type,
            min_score=min_score,
            style_only=style_only,
            search=search,
        )
        part_names = sorted({q.get("part_name") for q in questions if q.get("part_name")})
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "run_id": run_id,
                "questions": filtered,
                "parts": part_names,
                "filters": {
                    "part": part,
                    "question_type": question_type,
                    "min_score": min_score,
                    "style_only": style_only,
                    "search": search,
                },
            },
        )

    @app.get("/runs/{run_id}/report", response_class=HTMLResponse)
    def run_report(request: Request, run_id: str):
        run = _load_run_or_404(storage, run_id)
        questions = run.get("questions", [])
        events = run.get("events", [])
        scores = [q.get("validity_score") for q in questions if q.get("validity_score") is not None]
        avg_score = mean(scores) if scores else None
        low_scores = [q for q in questions if q.get("validity_score") is not None and q["validity_score"] < 70]
        style_flags = [q for q in questions if q.get("style_violation_flags")]
        parts = sorted({q.get("part_name") for q in questions if q.get("part_name")})

        return templates.TemplateResponse(
            request,
            "report.html",
            {
                "run_id": run_id,
                "events": events,
                "avg_score": avg_score,
                "low_scores": low_scores,
                "style_flags": style_flags,
                "parts": parts,
            },
        )

    return app
