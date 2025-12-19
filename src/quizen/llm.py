"""LLM client scaffolding for Gemini 3 Flash interactions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class LLMClient:
    """Minimal HTTP client wrapper for Gemini endpoints."""

    def __init__(self, base_url: str, api_key: str, model: str = "models/gemini-3-flash-preview"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = httpx.Client(timeout=30)

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
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
