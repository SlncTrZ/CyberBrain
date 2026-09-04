# SPDX-License-Identifier: MPL-2.0

import json

import httpx

from cyberbrain.reasoner_provider.backends.ollama import OllamaMicroReasoningBackend


def _request() -> dict:
    return {
        "task_id": "task-1",
        "request_id": "request-1",
        "topic": "CyberBrain",
        "kind": "current_state",
        "instruction": "Extract one current fact.",
        "evidence": [
            {
                "id": "e1",
                "record_type": "knowledge",
                "content": "OpenMontage was removed.",
                "score": 0.9,
                "event_time": None,
                "metadata": {},
            }
        ],
    }


def test_ollama_backend_accepts_response_field_and_constrains_evidence_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gemma-test"
        assert body["format"]["properties"]["task_id"]["enum"] == ["task-1"]
        evidence_enum = body["format"]["properties"]["claims"]["items"]["properties"][
            "evidence_ids"
        ]["items"]["enum"]
        assert evidence_enum == ["e1"]
        result = {
            "task_id": "task-1",
            "claims": [
                {
                    "claim": "OpenMontage was removed.",
                    "evidence_ids": ["e1"],
                    "confidence": 0.9,
                }
            ],
        }
        return httpx.Response(200, json={"response": json.dumps(result)}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    backend = OllamaMicroReasoningBackend(
        base_url="http://ollama:11434",
        model="gemma-test",
        client=client,
    )

    result = backend.reason_task(_request())

    assert result["task_id"] == "task-1"
    assert result["claims"][0]["evidence_ids"] == ["e1"]


def test_ollama_backend_accepts_thinking_field_for_thinking_models() -> None:
    result = {
        "task_id": "task-1",
        "claims": [
            {
                "claim": "OpenMontage was removed.",
                "evidence_ids": ["e1"],
                "confidence": 0.85,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"response": "", "thinking": json.dumps(result)},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    backend = OllamaMicroReasoningBackend(
        base_url="http://ollama:11434",
        model="thinking-test",
        client=client,
    )

    assert backend.reason_task(_request()) == result


def test_ollama_backend_returns_empty_claims_without_evidence() -> None:
    backend = OllamaMicroReasoningBackend(
        base_url="http://ollama:11434",
        model="test",
    )
    request = _request()
    request["evidence"] = []

    assert backend.reason_task(request) == {"task_id": "task-1", "claims": []}
