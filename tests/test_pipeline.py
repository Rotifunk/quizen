from quizen import build_default_runner
from quizen.models import Lecture
from quizen.parts import PartClassifier
from quizen.questions import QuestionGenerationOptions



def test_part_classifier_fallback_assigns_all_lectures():
    lectures = [Lecture(order=f"{i:03d}", id=f"L{i}", title=f"Lecture {i}") for i in range(1, 6)]
    classifier = PartClassifier(llm_client=None)

    result = classifier.classify(lectures)

    assert result.fallback_used is True
    assert len(result.parts) == 4  # heuristic min parts for 5 lectures
    assigned = sorted([lid for part in result.parts for lid in part.lecture_ids])
    assert assigned == sorted([lec.id for lec in lectures])
    assert any("Fallback PART split" in w for w in result.warnings)



def test_pipeline_runner_builds_export_rows():
    lectures = [Lecture(order="001", id="L1", title="Alpha"), Lecture(order="002", id="L2", title="Beta")]
    runner = build_default_runner(lectures, question_options=QuestionGenerationOptions(total_questions=4))

    ctx = runner.run()

    assert len(ctx.export_rows) == 4
    assert all(len(row.sheet_cells) == 9 for row in ctx.export_rows)
    assert ctx.events.events[0]["event"] == "run_started"
    assert ctx.events.events[-1]["event"] == "export_ready"

