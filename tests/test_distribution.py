from quizen.distribution import minimum_distribution, rebalance_questions
from quizen.models import Part, Question


def make_part(idx: int) -> Part:
    code = f"PART.{idx:02d}"
    return Part(part_code=code, part_title=f"Title {idx}", part_name=f"{code} Title {idx}")


def make_question(part_name: str, idx: int) -> Question:
    return Question(
        difficulty_code=3,
        question_type_code=1,
        question_text=f"Q{idx}",
        explanation_text="",
        answer_code=1,
        options=["a", "b", "c", "d"],
        part_name=part_name,
    )


def test_minimum_distribution_round_robin():
    parts = [make_part(1), make_part(2)]
    allocation = minimum_distribution(5, parts)
    assert allocation == {parts[0].part_name: 3, parts[1].part_name: 2}


def test_rebalance_questions_moves_overflow_to_short_parts():
    parts = [make_part(1), make_part(2)]
    questions = [make_question(parts[0].part_name, idx) for idx in range(4)]

    balanced = rebalance_questions(questions, parts)

    counts = {p.part_name: 0 for p in parts}
    for q in balanced:
        counts[q.part_name] += 1

    assert counts == {parts[0].part_name: 2, parts[1].part_name: 2}
    assert len(balanced) == len(questions)

