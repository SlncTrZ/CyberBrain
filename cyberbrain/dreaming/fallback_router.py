# SPDX-License-Identifier: MPL-2.0
"""Configured fallback LLM routes for Dream micro-reasoning."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal

import httpx
import uvicorn
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cyberbrain.reasoner_provider.contracts import (
    ReasonTaskRequest,
    ReasonTaskResult,
    validate_task_result,
)
from cyberbrain.reasoner_provider.http import create_reasoner_app
from cyberbrain.reasoner_provider.server import configure_micro_backend

ProtocolName = Literal["responses", "messages", "chat_completions"]
AuthMode = Literal["none", "bearer", "api_key"]


class LLMRouteConfig(BaseModel):
    """One ordered LLM provider route and its ordered model candidates."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1)
    models: list[str] = Field(min_length=1)
    protocols: list[ProtocolName] = Field(
        default_factory=lambda: ["responses", "chat_completions", "messages"]
    )
    auth: AuthMode = "none"
    auth_env: str | None = None
    timeout_seconds: float = Field(default=120.0, gt=0)
    max_tokens: int = Field(default=2400, ge=64)
    failure_cooldown_seconds: float = Field(default=60.0, ge=0)

    @field_validator("name", "base_url")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("models")
    @classmethod
    def _validate_models(cls, values: list[str]) -> list[str]:
        models = [value.strip() for value in values]
        if any(not value for value in models):
            raise ValueError("model names must not be empty")
        if len(models) != len(set(models)):
            raise ValueError("model names must be unique within a route")
        return models

    @field_validator("protocols")
    @classmethod
    def _validate_protocols(cls, values: list[ProtocolName]) -> list[ProtocolName]:
        if not values:
            raise ValueError("protocols must not be empty")
        if len(values) != len(set(values)):
            raise ValueError("protocols must be unique within a route")
        return values

    @model_validator(mode="after")
    def _validate_route(self) -> LLMRouteConfig:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http or https")
        if self.auth != "none" and not (self.auth_env or "").strip():
            raise ValueError("auth_env is required when auth is enabled")
        if self.auth == "none" and self.auth_env is not None:
            raise ValueError("auth_env must be omitted when auth is none")
        if self.auth_env is not None:
            self.auth_env = self.auth_env.strip()
        return self


class DreamLLMRoutesConfig(BaseModel):
    """Ordered fallback routes. MCP priority is handled before this list."""

    model_config = ConfigDict(extra="forbid")

    routes: list[LLMRouteConfig] = Field(min_length=1)

    @field_validator("routes")
    @classmethod
    def _unique_route_names(cls, routes: list[LLMRouteConfig]) -> list[LLMRouteConfig]:
        names = [route.name for route in routes]
        if len(names) != len(set(names)):
            raise ValueError("route names must be unique")
        return routes


def load_route_config(
    *,
    file_path: str | None = None,
    inline_json: str | None = None,
) -> DreamLLMRoutesConfig:
    path_value = (
        file_path
        if file_path is not None
        else os.environ.get("CYBERBRAIN_DREAM_LLM_ROUTES_FILE")
    )
    json_value = (
        inline_json
        if inline_json is not None
        else os.environ.get("CYBERBRAIN_DREAM_LLM_ROUTES_JSON")
    )

    if (path_value or "").strip() and (json_value or "").strip():
        raise ValueError(
            "set only one of CYBERBRAIN_DREAM_LLM_ROUTES_FILE "
            "or CYBERBRAIN_DREAM_LLM_ROUTES_JSON"
        )

    if (path_value or "").strip():
        path = Path(str(path_value).strip())
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif (json_value or "").strip():
        payload = json.loads(str(json_value))
    else:
        raise ValueError(
            "Dream fallback routes are not configured; set "
            "CYBERBRAIN_DREAM_LLM_ROUTES_FILE or CYBERBRAIN_DREAM_LLM_ROUTES_JSON"
        )

    return DreamLLMRoutesConfig.model_validate(payload)


class ConfiguredLLMRoutePool:
    """Try configured provider routes and models exactly in user-defined order."""

    def __init__(
        self,
        config: DreamLLMRoutesConfig,
        *,
        environ: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._environ = os.environ if environ is None else environ
        self._failed_until: dict[tuple[str, str], float] = {}
        self._validate_secrets()

    def _validate_secrets(self) -> None:
        missing = [
            route.auth_env
            for route in self._config.routes
            if route.auth != "none"
            and route.auth_env is not None
            and not (self._environ.get(route.auth_env) or "").strip()
        ]
        if missing:
            raise ValueError(
                "configured Dream route credential environment variables are missing: "
                + ", ".join(sorted(set(missing)))
            )

    def _headers(self, route: LLMRouteConfig) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if route.auth == "none":
            return headers

        assert route.auth_env is not None
        token = (self._environ.get(route.auth_env) or "").strip()
        if not token:
            raise ValueError(
                f"configured credential environment variable is empty: {route.auth_env}"
            )
        if route.auth == "bearer":
            headers["Authorization"] = f"Bearer {token}"
        elif route.auth == "api_key":
            headers["X-API-Key"] = token
        return headers

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

        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
            if parts:
                return "\n".join(parts)

        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            if isinstance(message, dict):
                for key in ("content", "reasoning_content", "reasoning", "thinking"):
                    value = message.get(key)
                    if isinstance(value, str) and value.strip():
                        return value

        raise RuntimeError("LLM provider returned no usable text content")

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
                raise RuntimeError("LLM provider returned invalid JSON") from None
            parsed = json.loads(value[start : end + 1])
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM provider JSON must be an object")
        return parsed

    @staticmethod
    def _prompt(request: dict[str, Any]) -> str:
        task_id = str(request["task_id"])
        topic = str(request.get("topic") or "")
        kind = str(request.get("kind") or "")
        instruction = str(request.get("instruction") or "")
        evidence = request.get("evidence") or []
        return (
            "You are a strict evidence-grounded consolidator. "
            "Use only supplied evidence. Preserve negation exactly. Never invent. "
            "Do not give advice, plans, or future recommendations. "
            "Every claim must cite only evidence IDs supplied below. "
            "If the task cannot be supported, return an empty claims array. "
            f"Echo task_id exactly as {task_id!r}. "
            "Return concise factual claims as JSON only.\n\n"
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

    @classmethod
    def _input_text(cls, request: dict[str, Any]) -> str:
        evidence = request.get("evidence") or []
        allowed_ids = [str(item.get("id")) for item in evidence if item.get("id")]
        schema = cls._schema(
            task_id=str(request["task_id"]),
            allowed_ids=allowed_ids,
        )
        return (
            cls._prompt(request)
            + "\n\nReturn ONLY one JSON object matching this schema exactly:\n"
            + json.dumps(schema, ensure_ascii=False)
        )

    @staticmethod
    def _body(
        protocol: ProtocolName,
        *,
        model: str,
        input_text: str,
        max_tokens: int,
    ) -> tuple[str, dict[str, Any]]:
        if protocol == "responses":
            return (
                "/v1/responses",
                {
                    "model": model,
                    "input": input_text,
                    "stream": False,
                    "max_output_tokens": max_tokens,
                },
            )
        if protocol == "messages":
            return (
                "/v1/messages",
                {
                    "model": model,
                    "max_tokens": max_tokens,
                    "stream": False,
                    "messages": [{"role": "user", "content": input_text}],
                },
            )
        return (
            "/v1/chat/completions",
            {
                "model": model,
                "max_tokens": max_tokens,
                "stream": False,
                "messages": [{"role": "user", "content": input_text}],
            },
        )

    def _reason_with_model(
        self,
        route: LLMRouteConfig,
        model: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = request.get("evidence") or []
        if not [item for item in evidence if item.get("id")]:
            return {"task_id": request["task_id"], "claims": []}

        input_text = self._input_text(request)
        headers = self._headers(route)
        errors: list[str] = []

        with httpx.Client(timeout=route.timeout_seconds) as client:
            for protocol in route.protocols:
                path, body = self._body(
                    protocol,
                    model=model,
                    input_text=input_text,
                    max_tokens=route.max_tokens,
                )
                try:
                    response = client.post(
                        f"{route.base_url.rstrip('/')}{path}",
                        headers=headers,
                        json=body,
                    )
                    response.raise_for_status()
                    text = self._extract_content(response.json())
                    return self._parse_json(text)
                except Exception as exc:
                    errors.append(f"{protocol}:{type(exc).__name__}")

        raise RuntimeError(
            f"configured route {route.name!r} model {model!r} failed: "
            + ",".join(errors)
        )

    def reason_task(
        self,
        request: dict[str, Any],
    ) -> tuple[dict[str, Any], str, str]:
        errors: list[str] = []
        now = time.monotonic()

        for route in self._config.routes:
            for model in route.models:
                key = (route.name, model)
                if self._failed_until.get(key, 0.0) > now:
                    continue
                try:
                    return self._reason_with_model(route, model, request), route.name, model
                except Exception as exc:
                    self._failed_until[key] = (
                        time.monotonic() + route.failure_cooldown_seconds
                    )
                    errors.append(f"{route.name}:{model}:{type(exc).__name__}")

        raise RuntimeError(
            "all configured Dream LLM routes failed: " + ",".join(errors[:20])
        )


class FallbackReasonerRouter:
    """Fallback LLM endpoint. MCP priority is owned by the Dream worker."""

    def __init__(self, *, route_pool: ConfiguredLLMRoutePool) -> None:
        self._route_pool = route_pool

    @staticmethod
    def _validate(request: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
        request_model = ReasonTaskRequest.model_validate(request)
        result_model = ReasonTaskResult.model_validate(raw)
        validate_task_result(request_model, result_model)
        return result_model.model_dump(mode="json")

    def reason_task(self, request: dict[str, Any]) -> dict[str, Any]:
        normalized = ReasonTaskRequest.model_validate(request).model_dump(mode="json")
        task_id = str(normalized["task_id"])
        raw, route_name, model = self._route_pool.reason_task(normalized)
        result = self._validate(normalized, raw)
        print(
            f"reasoner_route llm_ok task={task_id} route={route_name} model={model}",
            flush=True,
        )
        return result


def build_backend() -> FallbackReasonerRouter:
    config = load_route_config()
    return FallbackReasonerRouter(
        route_pool=ConfiguredLLMRoutePool(config),
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
