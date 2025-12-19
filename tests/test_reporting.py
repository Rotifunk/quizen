from quizen.reporting import build_meta_report, build_meta_sheet_rows
from quizen.models import Part, Question


def test_build_meta_sheet_rows_produces_part_and_question_sections():
    parts = [
        Part(part_code="PART.01", part_title="Intro", part_name="PART.01 Intro", lecture_ids=["L1", "L2"]),
        Part(part_code="PART.02", part_title="Deep", part_name="PART.02 Deep", lecture_ids=["L3"]),
    ]
    questions = [
        Question(
            difficulty_code=3,
            question_type_code=1,
            question_text="Q1",
            explanation_text="E1",
            answer_code=1,
            options=["A", "B", "C", "D"],
            part_name="PART.01 Intro",
        ),
        Question(
            difficulty_code=2,
            question_type_code=3,
            question_text="Q2",
            explanation_text="E2",
            answer_code=2,
            options=[],
            part_name="PART.02 Deep",
        ),
    ]

    questions[0].validity_score = 82
    questions[1].validity_score = 71
    questions[1].style_violation_flags.append("below_threshold")

    rows = build_meta_sheet_rows(
        parts,
        questions,
        events=[{"event": "run_started"}],
        warnings=["Filename missing order"],
        call_results=[{"service": "llm", "operation": "question_generation", "status": "success"}],
    )

    assert rows[1] == ["PART.01", "Intro", "2", "L1, L2"]
    assert ["pipeline_event", "payload"] in rows
    assert ["warning"] in rows
    assert ["service", "operation", "status", "error_code", "message"] in rows

    # Ensure score distribution rows are appended
    assert ["PART.01 Intro", "1", "82", "82", "82", "0"] in rows
    assert ["PART.02 Deep", "1", "71", "71", "71", "1"] in rows


def test_build_meta_report_collects_failed_calls():
    parts = [Part(part_code="PART.01", part_title="Intro", part_name="PART.01 Intro", lecture_ids=["L1"])]
    questions = [
        Question(
            difficulty_code=3,
            question_type_code=1,
            question_text="Q1",
            explanation_text="E1",
            answer_code=1,
            options=["A", "B", "C", "D"],
            part_name="PART.01 Intro",
            validity_score=90,
        )
    ]

    report = build_meta_report(
        parts,
        questions,
        events=[{"event": "run_started"}],
        warnings=["warn"],
        call_results=[{"service": "llm", "operation": "summary", "status": "error", "error_code": "Timeout"}],
    )

    assert report["warnings"] == ["warn"]
    assert report["events"][0]["event"] == "run_started"
    assert report["failed_calls"] == [{"service": "llm", "operation": "summary", "status": "error", "error_code": "Timeout"}]
