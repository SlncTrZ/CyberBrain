# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from typing import Any

import httpx


class OllamaMicroReasoningBackend:
    """Ollama-backed implementation of the provider-side micro reasoning contract."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
        num_predict: int = 700,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("Ollama base_url must use http or https")
        if not model.strip():
            raise ValueError("Ollama model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if num_predict < 64:
            raise ValueError("num_predict must be >= 64")
        self._base_url = base_url.rstrip("/")
        self._model = model.strip()
        self._timeout = timeout_seconds
        self._num_predict = num_predict
        self._client = client

    def reason_task(self, request: dict[str, Any]) -> dict[str, Any]:
        evidence = request.get("evidence") or []
        allowed_ids = [str(item.get("id")) for item in evidence if item.get("id")]
        if not allowed_ids:
            return {"task_id": request["task_id"], "claims": []}

        schema = self._schema(task_id=str(request["task_id"]), allowed_ids=allowed_ids)
        prompt = self._prompt(request)
        try:
            request_kwargs = {
                "json": {
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "format": schema,
                    "options": {
                        "temperature": 0,
                        "num_predict": self._num_predict,
                    },
                },
                "timeout": self._timeout,
            }
            if self._client is None:
                response = httpx.post(
                    f"{self._base_url}/api/generate",
                    **request_kwargs,
                )
            else:
                response = self._client.post(
                    f"{self._base_url}/api/generate",
                    **request_kwargs,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("Ollama micro reasoner request failed") from exc

        raw = payload.get("response") or payload.get("thinking") or ""
        if not isinstance(raw, str) or not raw.strip():
            raise RuntimeError("Ollama micro reasoner returned no usable output")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama micro reasoner returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Ollama micro reasoner JSON must be an object")
        return result

    @staticmethod
    def _prompt(request: dict[str, Any]) -> str:
        task_id = str(request["task_id"])
        topic = str(request.get("topic") or "")
        kind = str(request.get("kind") or "")
        instruction = str(request.get("instruction") or "")
        evidence = request.get("evidence") or []
        return (
            "/no_think\n"
            "You are a strict historical evidence consolidator. "
            "Use only supplied evidence. Preserve negation exactly. Never invent. "
            "Do not give advice, plans, or future recommendations. "
            "Every claim must cite only evidence IDs supplied below. "
            "Preserve literal command names, flags, config keys, model names, service names, "
            "paths, ports, and identifiers exactly when they materially support the claim. "
            "Do not paraphrase a literal such as 'validate --strict' into a generic phrase. "
            "If the task cannot be supported, return an empty claims array. "
            f"Echo task_id exactly as {task_id!r}. "
            "Return concise factual claims.\n\n"
            f"TOPIC: {topic}\n"
            f"TASK KIND: {kind}\n"
            f"INSTRUCTION: {instruction}\n"
            "EVIDENCE:\n"
            + json.dumps(evidence, ensure_ascii=False, indent=2)
        )

    @staticmethod
    def _schema(*, task_id: str, allowed_ids: list[str]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "enum": [task_id]},
                "claims": {
                    "type": "array",
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim": {"type": "string", "maxLength": 320},
                            "evidence_ids": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 4,
                                "items": {"type": "string", "enum": allowed_ids},
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["claim", "evidence_ids", "confidence"],
                    },
                },
            },
            "required": ["task_id", "claims"],
        }
