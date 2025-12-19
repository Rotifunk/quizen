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


def test_home_template_and_filters(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))
    html = client.get("/")
    assert "Drive 상위 폴더 ID" in html.text
    assert "문항 수" in html.text

    payload = {
        "lectures": [{"order": "001", "id": "L1", "title": "Intro"}],
        "total_questions": 3,
        "difficulty": 3,
        "include_mcq": True,
        "include_ox": True,
    }
    run = client.post("/runs", json=payload).json()["run_id"]

    filtered = client.get(f"/runs/{run}/questions", params={"min_score": 79}).json()
    assert filtered["count"] == 3

    style_only = client.get(f"/runs/{run}/questions", params={"style_only": True}).json()
    assert style_only["count"] <= filtered["count"]


def test_question_patch_validates(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))
    payload = {
        "lectures": [{"order": "001", "id": "L1", "title": "Intro"}],
        "total_questions": 1,
        "difficulty": 3,
        "include_mcq": True,
        "include_ox": False,
    }
    run_resp = client.post("/runs", json=payload)
    run_id = run_resp.json()["run_id"]

    invalid = client.patch(
        f"/runs/{run_id}/questions/0",
        json={"answer_code": 5},
    )
    assert invalid.status_code == 400

    valid = client.patch(
        f"/runs/{run_id}/questions/0",
        json={"answer_code": 2, "options": ["A", "B", "C", "D"]},
    )
    assert valid.status_code == 200
    assert valid.json()["question"]["answer_code"] == 2
