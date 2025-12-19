from quizen.questions import (
    QuestionGenerationOptions,
    generate_llm_questions,
    generate_questions,
)
from quizen.models import PartSummary


class _FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_json(self, prompt, schema):
        self.calls.append((prompt, schema))
        return self.payload


def test_generate_llm_questions_maps_payload():
    summaries = [PartSummary(part_name="PART.01 A", content="요약")]
    options = QuestionGenerationOptions(total_questions=2, difficulty=4)
    payload = {
        "questions": [
            {
                "question_text": "질문1",
                "explanation_text": "해설1",
                "question_type_code": 1,
                "difficulty_code": 5,
                "answer_code": 2,
                "options": ["A", "B", "C", "D"],
            },
            {
                "question_text": "질문2",
                "explanation_text": "해설2",
                "question_type_code": 3,
                "answer_code": 1,
                "options": [],
            },
        ]
    }
    client = _FakeLLM(payload)

    questions = generate_llm_questions(summaries, options, client)

    assert len(questions) == 2
    assert questions[0].question_text == "질문1"
    assert questions[0].options == ["A", "B", "C", "D"]
    assert questions[1].question_type_code == 3
    assert questions[1].options == []
    assert "PART.01 A" in client.calls[0][0]


def test_generate_llm_questions_fallback_on_error():
    class _ErrorLLM:
        def generate_json(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    summaries = [PartSummary(part_name="PART.01 A", content="요약")]
    options = QuestionGenerationOptions(total_questions=1, difficulty=2)

    questions = generate_llm_questions(summaries, options, _ErrorLLM())

    assert len(questions) == 1
    assert "PART.01 A" in questions[0].question_text
    assert questions[0].difficulty_code == 2


def test_generate_questions_switches_to_llm_when_available():
    payload = {
        "questions": [
            {
                "question_text": "LLM",
                "explanation_text": "E",
                "question_type_code": 1,
                "answer_code": 1,
                "options": ["a", "b", "c", "d"],
            }
        ]
    }
    client = _FakeLLM(payload)
    summaries = [PartSummary(part_name="PART.01 A", content="요약")]
    options = QuestionGenerationOptions(total_questions=1, difficulty=3)

    questions = generate_questions(summaries, options, llm_client=client)

    assert len(questions) == 1
    assert questions[0].question_text == "LLM"
