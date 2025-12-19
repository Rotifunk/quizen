from quizen.reporting import build_meta_sheet_rows
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

    rows = build_meta_sheet_rows(parts, questions)

    # header + 2 parts + spacer + question header + 2 questions = 7 rows
    assert len(rows) == 7
    assert rows[1] == ["PART.01", "Intro", "2", "L1, L2"]
    assert rows[-1] == ["2", "PART.02 Deep", "3", "2", "2"]
