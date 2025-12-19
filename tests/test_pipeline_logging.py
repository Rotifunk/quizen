from quizen.models import Lecture
from quizen.pipeline import build_default_runner


def test_pipeline_events_sink_receives_events():
    lectures = [Lecture(order="001", id="L1", title="Intro")]
    captured = []

    def sink(event):
        captured.append(event["event"])

    runner = build_default_runner(lectures, llm_client=None)
    runner.event_sinks = [sink]

    ctx = runner.run()

    assert "run_started" in captured
    assert captured[-1] == "export_ready"
    assert len(ctx.events.events) == len(captured)
