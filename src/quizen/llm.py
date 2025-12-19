"""LLM client scaffolding for Gemini 3 Flash interactions."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx


class LLMClient:
    """Minimal HTTP client wrapper for Gemini endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str | Sequence[str] = "models/gemini-3-flash-preview",
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = client or httpx.Client(timeout=30)
        self._owns_client = client is None

    def generate_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        *,
        models: Iterable[str] | None = None,
        max_retries: int = 2,
        backoff_factor: float = 1.0,
    ) -> Dict[str, Any]:
        """Send a generation request with retries and model fallback."""

        logger = logging.getLogger(__name__)

        model_candidates = list(models) if models is not None else self._normalize_models()
        if not model_candidates:
            raise ValueError("At least one model must be provided for generation")

        last_exc: Exception | None = None
        for model_name in model_candidates:
            attempt = 0
            while attempt <= max_retries:
                attempt += 1
                try:
                    return self._generate_for_model(prompt, schema, model_name)
                except httpx.TimeoutException as exc:
                    last_exc = exc
                    logger.warning(
                        "LLM request timed out for model %s (attempt %s/%s)",
                        model_name,
                        attempt,
                        max_retries + 1,
                    )
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    status = exc.response.status_code if exc.response else "unknown"
                    logger.warning(
                        "LLM request failed with status %s for model %s (attempt %s/%s)",
                        status,
                        model_name,
                        attempt,
                        max_retries + 1,
                    )
                except httpx.HTTPError as exc:
                    last_exc = exc
                    logger.warning(
                        "LLM request error for model %s (attempt %s/%s): %s",
                        model_name,
                        attempt,
                        max_retries + 1,
                        exc,
                    )
                except ValueError:
                    raise
                except Exception as exc:  # noqa: BLE001 - propagate unexpected
                    last_exc = exc
                    logger.error("LLM request failed for model %s: %s", model_name, exc)
                    break

                if attempt <= max_retries:
                    sleep_for = backoff_factor * (2 ** (attempt - 1))
                    if sleep_for > 0:
                        time.sleep(sleep_for)

            logger.info(
                "Falling back to next model after %s attempts for model %s",
                max_retries + 1,
                model_name,
            )

        if last_exc:
            raise last_exc
        raise RuntimeError("LLM generation failed without raising an explicit error")

    def _normalize_models(self) -> List[str]:
        if isinstance(self.model, str):
            return [self.model]
        return list(self.model)

    def _generate_for_model(self, prompt: str, schema: Dict[str, Any], model: str) -> Dict[str, Any]:
        url = f"{self.base_url}/v1beta/models/{model}:generateContent"
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
        return self._extract_args(data, prompt, schema)

    def _extract_args(self, data: Dict[str, Any], prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError(
                "LLM response did not include any candidates; ensure the prompt and response schema match."
            )
        parts = candidates[0].get("content", {}).get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError(
                "LLM response missing content parts; confirm the prompt requests JSON output matching the schema."
            )
        function_call = parts[0].get("functionCall")
        if not isinstance(function_call, dict):
            raise ValueError(
                "LLM response missing content.parts[0].functionCall.args; check the prompt/schema alignment."
            )
        args = function_call.get("args")
        if not isinstance(args, dict):
            raise ValueError(
                "LLM response missing functionCall.args object; verify the response schema matches the prompt."
            )
        return args

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
