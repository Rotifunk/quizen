"""LLM client scaffolding for Gemini 3 Flash interactions."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx


class LLMClient:
    """Minimal HTTP client wrapper for Gemini endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "models/gemini-3-flash-preview",
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = client or httpx.Client(timeout=30)
        self._owns_client = client is None

    def generate_json(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Send a generation request; caller should handle retries/fallbacks."""
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        headers = {"X-Goog-Api-Key": self.api_key}
        response = self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("LLM returned no candidates")
        # Gemini JSON mode returns content.parts[0].functionCall.args style payload
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError("LLM response missing content")
        return parts[0].get("functionCall", {}).get("args", {})

    def close(self):
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def build_default_llm_client(
    *, base_url: str = "https://generativelanguage.googleapis.com", model: str = "models/gemini-1.5-flash"
) -> LLMClient:
    """Create an LLM client using the GOOGLE_API_KEY env variable for tests and local runs."""

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY is required to build the default LLM client")
    return LLMClient(base_url=base_url, api_key=api_key, model=model)
