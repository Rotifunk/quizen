import os

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
