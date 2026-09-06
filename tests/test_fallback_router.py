# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from cyberbrain.dreaming.fallback_router import (
    FallbackReasonerRouter,
    NineRouterModelPool,
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
                "content": "Gemini is preferred before OpenCode free and Ollama.",
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


def _catalog() -> list[dict]:
    return [
        {
            "provider": "oc",
            "model": "mimo-v2.5-free",
            "fullModel": "oc/mimo-v2.5-free",
            "caps": {"reasoning": False},
        },
        {
            "provider": "gem",
            "model": "gemini-flash",
            "fullModel": "gem/gemini-flash",
            "caps": {"reasoning": False},
        },
        {
            "provider": "oc",
            "model": "muse-spark-1.2-contributor-free",
            "fullModel": "oc/muse-spark-1.2-contributor-free",
            "caps": {"reasoning": True},
        },
        {
            "provider": "gem",
            "model": "gemini-pro",
            "fullModel": "gem/gemini-pro",
            "caps": {"reasoning": True},
        },
        {
            "provider": "oc",
            "model": "muse-spark-1.3-contributor-free",
            "fullModel": "oc/muse-spark-1.3-contributor-free",
            "caps": {"reasoning": True},
        },
        {
            "provider": "other",
            "model": "paid-model",
            "fullModel": "other/paid-model",
            "caps": {"reasoning": True},
        },
    ]


class DeterministicPool(NineRouterModelPool):
    def __init__(
        self,
        *,
        fail_models: set[str] | None = None,
        probe_fail_models: set[str] | None = None,
    ) -> None:
        super().__init__(
            base_url="http://9router.invalid",
            data_dir="/tmp/unused",
            timeout_seconds=1,
            max_tokens=128,
        )
        self.fail_models = fail_models or set()
        self.probe_fail_models = probe_fail_models or set()
        self.attempts: list[str] = []

    def discover(self, *, force: bool = False) -> list[dict]:
        del force
        return _catalog()

    def _probe(self, model: str) -> bool:
        self.attempts.append(f"probe:{model}")
        return model not in self.probe_fail_models

    def _reason_with_model(self, model: str, request: dict) -> dict:
        del request
        self.attempts.append(f"reason:{model}")
        if model in self.fail_models:
            raise RuntimeError(f"{model} failed")
        return _result(f"result from {model}")


class FakeNineRouter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def reason_task(self, request):  # noqa: ANN001
        del request
        self.calls += 1
        if self.fail:
            raise RuntimeError("9router unavailable")
        return _result("9router result"), "gem/gemini-pro", "gemini"


class FakeOllama:
    def __init__(self) -> None:
        self.calls = 0

    def reason_task(self, request):  # noqa: ANN001
        del request
        self.calls += 1
        return _result("ollama result")


def test_model_tiers_filter_and_order_correctly() -> None:
    catalog = _catalog()

    gemini = NineRouterModelPool._ordered_gemini(catalog)
    oc_free = NineRouterModelPool._ordered_oc_free(catalog)

    assert [NineRouterModelPool._model_name(model) for model in gemini] == [
        "gem/gemini-pro",
        "gem/gemini-flash",
    ]
    assert [NineRouterModelPool._model_name(model) for model in oc_free] == [
        "oc/muse-spark-1.3-contributor-free",
        "oc/muse-spark-1.2-contributor-free",
        "oc/mimo-v2.5-free",
    ]


def test_pool_uses_gemini_before_opencode_free() -> None:
    pool = DeterministicPool()

    result, model, tier = pool.reason_task(_request())

    assert result["claims"][0]["claim"] == "result from gem/gemini-pro"
    assert model == "gem/gemini-pro"
    assert tier == "gemini"
    assert pool.attempts == [
        "probe:gem/gemini-pro",
        "reason:gem/gemini-pro",
    ]


def test_pool_uses_gemini_flash_when_pro_fails() -> None:
    pool = DeterministicPool(fail_models={"gem/gemini-pro"})

    result, model, tier = pool.reason_task(_request())

    assert result["claims"][0]["claim"] == "result from gem/gemini-flash"
    assert model == "gem/gemini-flash"
    assert tier == "gemini"
    assert pool.attempts == [
        "probe:gem/gemini-pro",
        "reason:gem/gemini-pro",
        "probe:gem/gemini-flash",
        "reason:gem/gemini-flash",
    ]


def test_pool_falls_back_to_opencode_free_after_all_gemini_fail() -> None:
    pool = DeterministicPool(
        fail_models={
            "gem/gemini-pro",
            "gem/gemini-flash",
        }
    )

    result, model, tier = pool.reason_task(_request())

    assert result["claims"][0]["claim"] == (
        "result from oc/muse-spark-1.3-contributor-free"
    )
    assert model == "oc/muse-spark-1.3-contributor-free"
    assert tier == "opencode_free"
    assert pool.attempts[:6] == [
        "probe:gem/gemini-pro",
        "reason:gem/gemini-pro",
        "probe:gem/gemini-flash",
        "reason:gem/gemini-flash",
        "probe:oc/muse-spark-1.3-contributor-free",
        "reason:oc/muse-spark-1.3-contributor-free",
    ]


def test_probe_failure_skips_model_without_reason_call() -> None:
    pool = DeterministicPool(
        probe_fail_models={
            "gem/gemini-pro",
            "gem/gemini-flash",
        }
    )

    _result_value, model, tier = pool.reason_task(_request())

    assert model == "oc/muse-spark-1.3-contributor-free"
    assert tier == "opencode_free"
    assert "reason:gem/gemini-pro" not in pool.attempts
    assert "reason:gem/gemini-flash" not in pool.attempts


def test_router_uses_9router_without_touching_ollama() -> None:
    nine = FakeNineRouter()
    ollama = FakeOllama()
    router = FallbackReasonerRouter(nine_router=nine, ollama=ollama)

    result = router.reason_task(_request())

    assert result["claims"][0]["claim"] == "9router result"
    assert nine.calls == 1
    assert ollama.calls == 0


def test_router_uses_ollama_only_after_all_9router_tiers_fail() -> None:
    nine = FakeNineRouter(fail=True)
    ollama = FakeOllama()
    router = FallbackReasonerRouter(nine_router=nine, ollama=ollama)

    result = router.reason_task(_request())

    assert result["claims"][0]["claim"] == "ollama result"
    assert nine.calls == 1
    assert ollama.calls == 1
