# SPDX-License-Identifier: MPL-2.0
"""Fallback-only Dream micro-reasoner: 9router Gemini, OpenCode free, then Ollama."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from cyberbrain.reasoner_provider.backends.ollama import OllamaMicroReasoningBackend
from cyberbrain.reasoner_provider.contracts import (
    ReasonTaskRequest,
    ReasonTaskResult,
    validate_task_result,
)
from cyberbrain.reasoner_provider.http import create_reasoner_app
from cyberbrain.reasoner_provider.server import configure_micro_backend


class NineRouterModelPool:
    """Discover and route Dream tasks across preferred 9router model tiers."""

    GEMINI_PRIORITY = (
        "gemini-pro",
        "gemini-flash",
    )

    def __init__(
        self,
        *,
        base_url: str,
        data_dir: str,
        timeout_seconds: float,
        max_tokens: int,
        catalog_ttl_seconds: float = 900.0,
        failure_cooldown_seconds: float = 600.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._data_dir = Path(data_dir)
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        self._catalog_ttl = catalog_ttl_seconds
        self._failure_cooldown = failure_cooldown_seconds
        self._cached_models: list[dict[str, Any]] = []
        self._catalog_loaded_at = 0.0
        self._failed_until: dict[str, float] = {}

    def _api_key(self) -> str:
        db_path = self._data_dir / "db" / "data.sqlite"
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = connection.execute(
                """
                SELECT key
                FROM apiKeys
                WHERE isActive = 1
                ORDER BY createdAt DESC
                LIMIT 1
                """
            ).fetchone()
        finally:
            connection.close()
        if row is None or not str(row[0]).strip():
            raise RuntimeError("9router has no active API key")
        return str(row[0]).strip()

    def _cli_token(self) -> str:
        machine_id = (self._data_dir / "machine-id").read_text(encoding="utf-8").strip()
        secret = (self._data_dir / "auth" / "cli-secret").read_text(encoding="utf-8").strip()
        if not machine_id or not secret:
            raise RuntimeError("9router CLI authentication material is unavailable")
        return hashlib.sha256(
            f"{machine_id}9r-cli-auth{secret}".encode()
        ).hexdigest()[:16]

    def _catalog_headers(self) -> dict[str, str]:
        return {
            "x-9r-cli-token": self._cli_token(),
            "Content-Type": "application/json",
        }

    def _v1_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _model_name(model: dict[str, Any]) -> str:
        full_model = str(model.get("fullModel") or "").strip()
        if full_model:
            return full_model
        routed_model = str(model.get("routedModel") or "").strip()
        if routed_model:
            return routed_model
        provider = str(model.get("provider") or "").strip()
        model_id = str(model.get("model") or "").strip()
        return f"{provider}/{model_id}" if provider and model_id else model_id

    @classmethod
    def _gemini_identity(cls, model: dict[str, Any]) -> str:
        for key in ("model", "alias"):
            value = str(model.get(key) or "").strip().casefold()
            if value in {name.casefold() for name in cls.GEMINI_PRIORITY}:
                return value
        return ""

    @classmethod
    def _is_gemini(cls, model: dict[str, Any]) -> bool:
        return bool(cls._gemini_identity(model))

    @staticmethod
    def _is_oc_free(model: dict[str, Any]) -> bool:
        provider = str(model.get("provider") or "").strip().casefold()
        model_id = str(model.get("model") or "").strip().casefold()
        full_model = str(model.get("fullModel") or "").strip().casefold()
        if provider != "oc" and not full_model.startswith("oc/"):
            return False
        return "free" in model_id

    @classmethod
    def _ordered_gemini(cls, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_identity = {
            cls._gemini_identity(model): model
            for model in models
            if cls._is_gemini(model)
        }
        return [
            by_identity[name.casefold()]
            for name in cls.GEMINI_PRIORITY
            if name.casefold() in by_identity
        ]

    @staticmethod
    def _ordered_oc_free(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[int, list[dict[str, Any]]] = {0: [], 1: []}
        for model in models:
            if not NineRouterModelPool._is_oc_free(model):
                continue
            reasoning = bool((model.get("caps") or {}).get("reasoning"))
            groups[0 if reasoning else 1].append(model)
        ordered: list[dict[str, Any]] = []
        for group in (0, 1):
            ordered.extend(
                sorted(
                    groups[group],
                    key=lambda item: NineRouterModelPool._model_name(item),
                    reverse=True,
                )
            )
        return ordered

    def discover(self, *, force: bool = False) -> list[dict[str, Any]]:
        now = time.monotonic()
        if (
            not force
            and self._cached_models
            and now - self._catalog_loaded_at < self._catalog_ttl
        ):
            return list(self._cached_models)

        with httpx.Client(timeout=min(self._timeout, 30.0)) as client:
            response = client.get(
                f"{self._base_url}/api/models",
                headers=self._catalog_headers(),
            )
            response.raise_for_status()
            payload = response.json()

        models = [
            model
            for model in payload.get("models") or []
            if isinstance(model, dict)
        ]
        self._cached_models = models
        self._catalog_loaded_at = now
        return list(self._cached_models)

    def _probe(self, model: str) -> bool:
        now = time.monotonic()
        if self._failed_until.get(model, 0.0) > now:
            return False

        try:
            with httpx.Client(timeout=min(self._timeout, 25.0)) as client:
                response = client.post(
                    f"{self._base_url}/api/models/test",
                    headers=self._catalog_headers(),
                    json={"model": model, "kind": "llm"},
                )
                response.raise_for_status()
                ok = bool(response.json().get("ok"))
        except Exception:
            ok = False

        if not ok:
            self._failed_until[model] = now + self._failure_cooldown
        return ok

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        parts: list[str] = []
        for item in payload.get("output") or []:
            if not isinstance(item, dict):
                continue
            direct = item.get("text")
            if isinstance(direct, str) and direct.strip():
                parts.append(direct)
            for content in item.get("content") or []:
                if isinstance(content, dict):
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
        if parts:
            return "\n".join(parts)

        top_content = payload.get("content")
        if isinstance(top_content, list):
            for item in top_content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
            if parts:
                return "\n".join(parts)

        choices = payload.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            for key in ("content", "reasoning_content", "reasoning", "thinking"):
                value = message.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        raise RuntimeError("9router returned no usable text content")

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        value = text.strip()
        if value.startswith("~~~"):
            value = value.strip("~").strip()
        if value.startswith("```"):
            lines = value.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            value = "\n".join(lines).strip()
            if value.lower().startswith("json\n"):
                value = value[5:].strip()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start < 0 or end <= start:
                raise RuntimeError("9router returned invalid JSON") from None
            parsed = json.loads(value[start : end + 1])
        if not isinstance(parsed, dict):
            raise RuntimeError("9router JSON must be an object")
        return parsed

    def _reason_with_model(
        self,
        model: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = request.get("evidence") or []
        allowed_ids = [str(item.get("id")) for item in evidence if item.get("id")]
        if not allowed_ids:
            return {"task_id": request["task_id"], "claims": []}

        schema = OllamaMicroReasoningBackend._schema(
            task_id=str(request["task_id"]),
            allowed_ids=allowed_ids,
        )
        prompt = (
            OllamaMicroReasoningBackend._prompt(request)
            + "\n\nReturn ONLY one JSON object matching this schema exactly:\n"
            + json.dumps(schema, ensure_ascii=False)
        )
        input_text = (
            "You are a strict evidence-grounded consolidator. "
            "Return JSON only. Never invent evidence IDs.\n\n"
            + prompt
        )
        headers = self._v1_headers()

        variants = (
            (
                "/v1/responses",
                {
                    "model": model,
                    "input": input_text,
                    "stream": False,
                    "max_output_tokens": self._max_tokens,
                },
            ),
            (
                "/v1/messages",
                {
                    "model": model,
                    "max_tokens": self._max_tokens,
                    "stream": False,
                    "messages": [{"role": "user", "content": input_text}],
                },
            ),
            (
                "/v1/chat/completions",
                {
                    "model": model,
                    "max_tokens": self._max_tokens,
                    "stream": False,
                    "messages": [{"role": "user", "content": input_text}],
                },
            ),
        )
        errors: list[str] = []
        with httpx.Client(timeout=self._timeout) as client:
            for path, body in variants:
                try:
                    response = client.post(
                        f"{self._base_url}{path}",
                        headers=headers,
                        json=body,
                    )
                    response.raise_for_status()
                    text = self._extract_content(response.json())
                    return self._parse_json(text)
                except Exception as exc:
                    errors.append(f"{path}:{type(exc).__name__}")

        raise RuntimeError(
            f"9router model {model!r} failed all compatible protocols: "
            + ",".join(errors)
        )

    def reason_task(
        self,
        request: dict[str, Any],
    ) -> tuple[dict[str, Any], str, str]:
        catalog = self.discover()
        tiers = (
            ("gemini", self._ordered_gemini(catalog)),
            ("opencode_free", self._ordered_oc_free(catalog)),
        )
        if not any(models for _tier, models in tiers):
            raise RuntimeError(
                "9router catalog contains no configured Gemini or OpenCode free models"
            )

        errors: list[str] = []
        for tier, models in tiers:
            for item in models:
                model = self._model_name(item)
                if not model:
                    continue
                if not self._probe(model):
                    errors.append(f"{tier}:{model}:probe_failed")
                    continue
                try:
                    return self._reason_with_model(model, request), model, tier
                except Exception as exc:
                    self._failed_until[model] = time.monotonic() + self._failure_cooldown
                    errors.append(f"{tier}:{model}:{type(exc).__name__}")

        raise RuntimeError("all 9router Dream models failed: " + ",".join(errors[:12]))


class FallbackReasonerRouter:
    """Fallback router only. MCP priority is owned by the Dream worker run coordinator."""

    def __init__(
        self,
        *,
        nine_router: NineRouterModelPool,
        ollama: OllamaMicroReasoningBackend,
    ) -> None:
        self._nine_router = nine_router
        self._ollama = ollama

    @staticmethod
    def _validate(request: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
        request_model = ReasonTaskRequest.model_validate(request)
        result_model = ReasonTaskResult.model_validate(raw)
        validate_task_result(request_model, result_model)
        return result_model.model_dump(mode="json")

    def reason_task(self, request: dict[str, Any]) -> dict[str, Any]:
        normalized = ReasonTaskRequest.model_validate(request).model_dump(mode="json")
        task_id = str(normalized["task_id"])

        try:
            raw, model, tier = self._nine_router.reason_task(normalized)
            result = self._validate(normalized, raw)
            print(
                f"reasoner_route 9router_ok task={task_id} tier={tier} model={model}",
                flush=True,
            )
            return result
        except Exception as exc:
            print(
                f"reasoner_route 9router_failed task={task_id} "
                f"error={type(exc).__name__}; trying_ollama",
                flush=True,
            )

        raw = self._ollama.reason_task(normalized)
        result = self._validate(normalized, raw)
        model = os.environ.get(
            "DREAM_OLLAMA_MODEL",
            "qwen3-vl:2b-thinking",
        )
        print(
            f"reasoner_route ollama_ok task={task_id} model={model}",
            flush=True,
        )
        return result


def build_backend() -> FallbackReasonerRouter:
    return FallbackReasonerRouter(
        nine_router=NineRouterModelPool(
            base_url=os.environ.get("DREAM_9ROUTER_URL", "http://9router:20128"),
            data_dir=os.environ.get("DREAM_9ROUTER_DATA_DIR", "/nine-data"),
            timeout_seconds=float(os.environ.get("DREAM_9ROUTER_TIMEOUT_SECONDS", "180")),
            max_tokens=int(os.environ.get("DREAM_9ROUTER_MAX_TOKENS", "2400")),
            catalog_ttl_seconds=float(
                os.environ.get("DREAM_9ROUTER_CATALOG_TTL_SECONDS", "900")
            ),
            failure_cooldown_seconds=float(
                os.environ.get("DREAM_9ROUTER_FAILURE_COOLDOWN_SECONDS", "600")
            ),
        ),
        ollama=OllamaMicroReasoningBackend(
            base_url=os.environ.get("DREAM_OLLAMA_URL", "http://ollama:11434"),
            model=os.environ.get("DREAM_OLLAMA_MODEL", "qwen3-vl:2b-thinking"),
            timeout_seconds=float(os.environ.get("DREAM_OLLAMA_TIMEOUT_SECONDS", "240")),
            num_predict=int(os.environ.get("DREAM_OLLAMA_NUM_PREDICT", "700")),
        ),
    )


def main() -> None:
    token = (os.environ.get("REASONER_AUTH_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("REASONER_AUTH_TOKEN is required")
    configure_micro_backend(build_backend())
    app = create_reasoner_app(auth_token=token, require_auth=True)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("REASONER_ROUTER_PORT", "8771")),
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit("fallback router does not accept command arguments")
    main()
