import os

import httpx
import pytest

from quizen.llm import LLMClient, build_default_llm_client


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.closed = False

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []
        self.closed = False

    def post(self, url, json=None, headers=None):
        self.requests.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(self.payload)

    def close(self):
        self.closed = True


def test_generate_json_uses_supplied_client_and_api_key_header():
    payload = {
        "candidates": [
            {"content": {"parts": [{"functionCall": {"args": {"result": "ok"}}}]}}
        ]
    }
    fake_client = _FakeClient(payload)
    llm = LLMClient(
        base_url="https://example.com",
        api_key="secret-key",
        model="models/unit-test",
        client=fake_client,
    )

    result = llm.generate_json("prompt", {"type": "object"})

    assert result == {"result": "ok"}
    assert fake_client.requests[0]["headers"]["X-Goog-Api-Key"] == "secret-key"
    assert fake_client.requests[0]["url"].endswith(":generateContent")


def test_generate_json_retries_with_backoff(monkeypatch, caplog):
    payload = {
        "candidates": [
            {"content": {"parts": [{"functionCall": {"args": {"result": "eventual"}}}]}}
        ]
    }

    class _RetryClient:
        def __init__(self):
            self.calls = 0

        def post(self, url, json=None, headers=None):
            self.calls += 1
            if self.calls < 3:
                raise httpx.TimeoutException("timeout")
            return _FakeResponse(payload)

    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda secs: sleep_calls.append(secs))
    caplog.set_level("WARNING")

    llm = LLMClient(
        base_url="https://example.com",
        api_key="secret-key",
        model="models/unit-test",
        client=_RetryClient(),
    )

    result = llm.generate_json("prompt", {"type": "object"}, max_retries=2, backoff_factor=0.5)

    assert result == {"result": "eventual"}
    assert sleep_calls == [0.5, 1.0]
    assert any("timed out" in msg for msg in caplog.messages)


def test_generate_json_falls_back_to_next_model(caplog):
    payload = {
        "candidates": [
            {"content": {"parts": [{"functionCall": {"args": {"result": "next"}}}]}}
        ]
    }

    class _FallbackClient:
        def __init__(self):
            self.calls = []

        def post(self, url, json=None, headers=None):
            self.calls.append(url)
            if "primary" in url:
                response = httpx.Response(503, request=httpx.Request("POST", url))
                raise httpx.HTTPStatusError("service unavailable", request=response.request, response=response)
            return _FakeResponse(payload)

    caplog.set_level("INFO")
    client = _FallbackClient()
    llm = LLMClient(
        base_url="https://example.com",
        api_key="secret-key",
        model="models/primary",
        client=client,
    )

    result = llm.generate_json(
        "prompt", {"type": "object"}, models=["models/primary", "models/secondary"], max_retries=0
    )

    assert result == {"result": "next"}
    assert any("Falling back" in msg for msg in caplog.messages)
    assert any("secondary" in call for call in client.calls)


def test_generate_json_validates_missing_function_call_args():
    payload = {"candidates": [{"content": {"parts": [{"text": "just text"}]}}]}
    fake_client = _FakeClient(payload)
    llm = LLMClient(
        base_url="https://example.com",
        api_key="secret-key",
        model="models/unit-test",
        client=fake_client,
    )

    with pytest.raises(ValueError) as excinfo:
        llm.generate_json("prompt", {"type": "object"})

    assert "functionCall.args" in str(excinfo.value)


def test_build_default_llm_client_reads_google_api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "env-key")

    client = build_default_llm_client(base_url="https://example.com", model="models/test")

    assert client.api_key == "env-key"
    assert client.base_url == "https://example.com"
    assert client.model == "models/test"


def test_build_default_llm_client_errors_without_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(EnvironmentError):
        build_default_llm_client()
