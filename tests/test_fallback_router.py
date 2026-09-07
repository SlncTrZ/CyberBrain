# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json

import pytest

from cyberbrain.dreaming.fallback_router import (
    ConfiguredLLMRoutePool,
    DreamLLMRoutesConfig,
    FallbackReasonerRouter,
    LLMRouteConfig,
    load_route_config,
)


def _request() -> dict:
    return {
        "task_id": "task-1",
        "request_id": "request-1",
        "topic": "routing",
        "kind": "current_state",
        "instruction": "Extract one supported fact.",
        "evidence": [
            {
                "id": "e1",
                "record_type": "knowledge",
                "content": "Configured LLM routes are tried in user-defined order.",
                "score": 1.0,
                "event_time": None,
                "metadata": {},
            }
        ],
    }


def _result(claim: str) -> dict:
    return {
        "task_id": "task-1",
        "claims": [
            {
                "claim": claim,
                "evidence_ids": ["e1"],
                "confidence": 0.9,
            }
        ],
    }


def _config() -> DreamLLMRoutesConfig:
    return DreamLLMRoutesConfig(
        routes=[
            LLMRouteConfig(
                name="provider-1",
                base_url="http://provider-1.invalid",
                models=["model-1A", "model-1B"],
                auth="none",
            ),
            LLMRouteConfig(
                name="provider-2",
                base_url="http://provider-2.invalid",
                models=["model-2A", "model-2B"],
                auth="none",
            ),
        ]
    )


class DeterministicPool(ConfiguredLLMRoutePool):
    def __init__(
        self,
        *,
        fail: set[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(_config(), environ={})
        self.fail = fail or set()
        self.attempts: list[tuple[str, str]] = []

    def _reason_with_model(self, route, model, request):  # noqa: ANN001
        del request
        key = (route.name, model)
        self.attempts.append(key)
        if key in self.fail:
            raise RuntimeError("configured model failed")
        return _result(f"result from {route.name}/{model}")


class FakeRoutePool:
    def __init__(self, *, invalid: bool = False) -> None:
        self.invalid = invalid
        self.calls = 0

    def reason_task(self, request):  # noqa: ANN001
        del request
        self.calls += 1
        if self.invalid:
            return (
                {
                    "task_id": "task-1",
                    "claims": [
                        {
                            "claim": "unsupported",
                            "evidence_ids": ["unknown"],
                            "confidence": 1.0,
                        }
                    ],
                },
                "provider-1",
                "model-1A",
            )
        return _result("configured result"), "provider-1", "model-1A"


def test_config_preserves_provider_and_model_order() -> None:
    config = _config()

    assert [route.name for route in config.routes] == ["provider-1", "provider-2"]
    assert config.routes[0].models == ["model-1A", "model-1B"]
    assert config.routes[1].models == ["model-2A", "model-2B"]


def test_pool_uses_first_model_of_first_provider() -> None:
    pool = DeterministicPool()

    result, route_name, model = pool.reason_task(_request())

    assert result["claims"][0]["claim"] == "result from provider-1/model-1A"
    assert route_name == "provider-1"
    assert model == "model-1A"
    assert pool.attempts == [("provider-1", "model-1A")]


def test_pool_uses_next_model_before_next_provider() -> None:
    pool = DeterministicPool(fail={("provider-1", "model-1A")})

    result, route_name, model = pool.reason_task(_request())

    assert result["claims"][0]["claim"] == "result from provider-1/model-1B"
    assert route_name == "provider-1"
    assert model == "model-1B"
    assert pool.attempts == [
        ("provider-1", "model-1A"),
        ("provider-1", "model-1B"),
    ]


def test_pool_uses_next_provider_only_after_current_provider_models_fail() -> None:
    pool = DeterministicPool(
        fail={
            ("provider-1", "model-1A"),
            ("provider-1", "model-1B"),
        }
    )

    result, route_name, model = pool.reason_task(_request())

    assert result["claims"][0]["claim"] == "result from provider-2/model-2A"
    assert route_name == "provider-2"
    assert model == "model-2A"
    assert pool.attempts == [
        ("provider-1", "model-1A"),
        ("provider-1", "model-1B"),
        ("provider-2", "model-2A"),
    ]


def test_pool_raises_after_every_configured_model_fails() -> None:
    pool = DeterministicPool(
        fail={
            ("provider-1", "model-1A"),
            ("provider-1", "model-1B"),
            ("provider-2", "model-2A"),
            ("provider-2", "model-2B"),
        }
    )

    with pytest.raises(RuntimeError, match="all configured Dream LLM routes failed"):
        pool.reason_task(_request())


def test_config_requires_auth_env_for_authenticated_route() -> None:
    with pytest.raises(ValueError, match="auth_env"):
        LLMRouteConfig(
            name="provider-1",
            base_url="https://provider.invalid",
            models=["model-1A"],
            auth="bearer",
        )


def test_pool_fails_closed_when_configured_secret_env_is_missing() -> None:
    config = DreamLLMRoutesConfig(
        routes=[
            LLMRouteConfig(
                name="provider-1",
                base_url="https://provider.invalid",
                models=["model-1A"],
                auth="bearer",
                auth_env="PROVIDER_1_TOKEN",
            )
        ]
    )

    with pytest.raises(ValueError, match="PROVIDER_1_TOKEN"):
        ConfiguredLLMRoutePool(config, environ={})


def test_headers_resolve_secret_from_environment_without_storing_it_in_config() -> None:
    route = LLMRouteConfig(
        name="provider-1",
        base_url="https://provider.invalid",
        models=["model-1A"],
        auth="bearer",
        auth_env="PROVIDER_1_TOKEN",
    )
    pool = ConfiguredLLMRoutePool(
        DreamLLMRoutesConfig(routes=[route]),
        environ={"PROVIDER_1_TOKEN": "runtime-secret"},
    )

    headers = pool._headers(route)

    assert headers["Authorization"] == "Bearer runtime-secret"
    assert "runtime-secret" not in route.model_dump_json()


def test_load_route_config_from_inline_json() -> None:
    payload = {
        "routes": [
            {
                "name": "provider-1",
                "base_url": "http://provider-1.invalid",
                "models": ["model-1A"],
            }
        ]
    }

    config = load_route_config(inline_json=json.dumps(payload), file_path="")

    assert config.routes[0].name == "provider-1"
    assert config.routes[0].models == ["model-1A"]


def test_public_example_route_config_matches_schema() -> None:
    config = load_route_config(
        file_path="config/dream-routes.example.json",
        inline_json="",
    )

    assert [route.name for route in config.routes] == ["provider-1", "provider-2"]
    assert config.routes[0].models == ["model-1A", "model-1B"]


def test_load_route_config_from_file(tmp_path) -> None:
    path = tmp_path / "dream-routes.json"
    path.write_text(
        json.dumps(
            {
                "routes": [
                    {
                        "name": "provider-1",
                        "base_url": "http://provider-1.invalid",
                        "models": ["model-1A"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    config = load_route_config(file_path=str(path), inline_json="")

    assert config.routes[0].name == "provider-1"


def test_load_route_config_rejects_ambiguous_sources(tmp_path) -> None:
    path = tmp_path / "dream-routes.json"
    path.write_text('{"routes":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="only one"):
        load_route_config(
            file_path=str(path),
            inline_json='{"routes":[]}',
        )


def test_protocol_paths_are_standard_and_order_is_configurable() -> None:
    responses_path, _ = ConfiguredLLMRoutePool._body(
        "responses",
        model="model-1A",
        input_text="prompt",
        max_tokens=100,
    )
    messages_path, _ = ConfiguredLLMRoutePool._body(
        "messages",
        model="model-1A",
        input_text="prompt",
        max_tokens=100,
    )
    chat_path, _ = ConfiguredLLMRoutePool._body(
        "chat_completions",
        model="model-1A",
        input_text="prompt",
        max_tokens=100,
    )

    assert responses_path == "/v1/responses"
    assert messages_path == "/v1/messages"
    assert chat_path == "/v1/chat/completions"


def test_router_returns_valid_configured_result() -> None:
    pool = FakeRoutePool()
    router = FallbackReasonerRouter(route_pool=pool)

    result = router.reason_task(_request())

    assert result["claims"][0]["claim"] == "configured result"
    assert pool.calls == 1


def test_router_rejects_result_with_unknown_evidence() -> None:
    router = FallbackReasonerRouter(route_pool=FakeRoutePool(invalid=True))

    with pytest.raises(ValueError, match="unknown evidence ids"):
        router.reason_task(_request())
