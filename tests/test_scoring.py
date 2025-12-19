import sys
import types

# Stub Google client libraries to avoid heavy dependencies during tests
google_stub = types.ModuleType("google")
sys.modules.setdefault("google", google_stub)
sys.modules.setdefault("google.oauth2", types.ModuleType("google.oauth2"))
credentials_module = types.ModuleType("google.oauth2.credentials")
credentials_module.Credentials = type("Credentials", (), {})
sys.modules.setdefault("google.oauth2.credentials", credentials_module)
service_account_module = types.ModuleType("google.oauth2.service_account")
service_account_module.Credentials = type(
    "ServiceAccountCredentials",
    (),
    {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())},
)
sys.modules.setdefault("google.oauth2.service_account", service_account_module)
flow_module = types.ModuleType("google_auth_oauthlib.flow")
flow_module.InstalledAppFlow = type(
    "InstalledAppFlow",
    (),
    {"from_client_secrets_file": staticmethod(lambda *a, **k: type("_Flow", (), {"run_local_server": lambda self, port=0: object()})())},
)
sys.modules.setdefault("google_auth_oauthlib", types.ModuleType("google_auth_oauthlib"))
sys.modules.setdefault("google_auth_oauthlib.flow", flow_module)
discovery_module = types.ModuleType("googleapiclient.discovery")
discovery_module.build = lambda *args, **kwargs: None
sys.modules.setdefault("googleapiclient", types.ModuleType("googleapiclient"))
sys.modules.setdefault("googleapiclient.discovery", discovery_module)
http_module = types.ModuleType("googleapiclient.http")
http_module.MediaIoBaseDownload = type(
    "MediaIoBaseDownload", (), {"next_chunk": lambda self: (None, True)}
)
sys.modules.setdefault("googleapiclient.http", http_module)
fastapi_module = types.ModuleType("fastapi")
fastapi_module.FastAPI = type("FastAPI", (), {"__init__": lambda self, *a, **k: None})
fastapi_module.HTTPException = type("HTTPException", (Exception,), {})
sys.modules.setdefault("fastapi", fastapi_module)

from quizen.models import Question
from quizen.scoring import THRESHOLD_FLAG, score_questions


class _FakeLLMClient:
    def __init__(self, payload=None, exc: Exception | None = None):
        self.payload = payload or {}
        self.exc = exc
        self.calls = []

    def generate_json(self, prompt, schema):
        self.calls.append({"prompt": prompt, "schema": schema})
        if self.exc:
            raise self.exc
        return self.payload


def _question(q_type: int = 1) -> Question:
    return Question(
        difficulty_code=2,
        question_type_code=q_type,
        question_text="무엇이 핵심인가요?",
        explanation_text="간단한 설명",
        answer_code=1,
        options=["A", "B", "C", "D"] if q_type == 1 else [],
        part_name="PART.01 제목",
        validity_score=None,
        style_violation_flags=[],
    )


def test_score_questions_llm_success_parses_fields():
    payload = {
        "scores": [
            {
                "total_score": 92,
                "issue_tags": ["lengthy"],
                "improvement": "문장을 더 간결하게 하세요.",
            }
        ]
    }
    llm = _FakeLLMClient(payload=payload)

    questions = score_questions([_question()], llm_client=llm, threshold=80.0)

    assert questions[0].validity_score == 92.0
    assert "lengthy" in questions[0].style_violation_flags
    assert any(flag.startswith("improvement:") for flag in questions[0].style_violation_flags)
    assert THRESHOLD_FLAG not in questions[0].style_violation_flags
    assert llm.calls, "LLM should be invoked"


def test_score_questions_falls_back_on_llm_error():
    llm = _FakeLLMClient(exc=RuntimeError("boom"))

    questions = score_questions([_question()], llm_client=llm)

    assert questions[0].validity_score == 85.0
    assert questions[0].style_violation_flags == []


def test_score_questions_flags_threshold_breaches():
    payload = {"scores": [{"total_score": 60, "issue_tags": ["off_topic"]}]}
    llm = _FakeLLMClient(payload=payload)

    questions = score_questions([_question()], llm_client=llm, threshold=70.0)

    assert THRESHOLD_FLAG in questions[0].style_violation_flags
    assert "off_topic" in questions[0].style_violation_flags
