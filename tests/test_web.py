from fastapi.testclient import TestClient

from quizen.web import create_app


def test_create_app_runs_pipeline_and_persists(tmp_path):
    app = create_app(storage_dir=tmp_path)
    client = TestClient(app)

    payload = {
        "lectures": [{"order": "001", "id": "L1", "title": "Intro"}],
        "total_questions": 2,
        "difficulty": 3,
        "include_mcq": True,
        "include_ox": False,
    }
    response = client.post("/runs", json=payload)
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert response.json()["question_count"] == 2

    detail = client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["questions"]
    assert body["events"][0]["event"] == "run_started"


def test_health_endpoint():
    client = TestClient(create_app(storage_dir="/tmp"))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
