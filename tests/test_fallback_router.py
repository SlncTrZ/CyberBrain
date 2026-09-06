# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from cyberbrain.dreaming.fallback_router import (
    FallbackReasonerRouter,
    NineRouterOCFreePool,
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
                "content": "9router is preferred before Ollama.",
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


class FakeNineRouter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def reason_task(self, request):  # noqa: ANN001
        self.calls += 1
        if self.fail:
            raise RuntimeError("9router unavailable")
        return _result("9router result"), "oc/muse-spark-1.2-contributor-free"


class FakeOllama:
    def __init__(self) -> None:
        self.calls = 0

    def reason_task(self, request):  # noqa: ANN001
        self.calls += 1
        return _result("ollama result")


def test_oc_free_filter_and_order_prefers_reasoning_models() -> None:
    models = [
        {
            "provider": "oc",
            "model": "mimo-v2.5-free",
            "fullModel": "oc/mimo-v2.5-free",
            "caps": {"reasoning": False},
        },
        {
            "provider": "oc",
            "model": "muse-spark-1.2-contributor-free",
            "fullModel": "oc/muse-spark-1.2-contributor-free",
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

    filtered = [
        model for model in models if NineRouterOCFreePool._is_oc_free(model)
    ]
    ordered = NineRouterOCFreePool._ordered(filtered)

    assert [model["fullModel"] for model in ordered] == [
        "oc/muse-spark-1.3-contributor-free",
        "oc/muse-spark-1.2-contributor-free",
        "oc/mimo-v2.5-free",
    ]


def test_router_uses_9router_without_touching_ollama() -> None:
    nine = FakeNineRouter()
    ollama = FakeOllama()
    router = FallbackReasonerRouter(nine_router=nine, ollama=ollama)

    result = router.reason_task(_request())

    assert result["claims"][0]["claim"] == "9router result"
    assert nine.calls == 1
    assert ollama.calls == 0


def test_router_uses_ollama_only_after_9router_failure() -> None:
    nine = FakeNineRouter(fail=True)
    ollama = FakeOllama()
    router = FallbackReasonerRouter(nine_router=nine, ollama=ollama)

    result = router.reason_task(_request())

    assert result["claims"][0]["claim"] == "ollama result"
    assert nine.calls == 1
    assert ollama.calls == 1
