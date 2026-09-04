# SPDX-License-Identifier: MPL-2.0

import socket
import threading
import time
from datetime import UTC, datetime

import uvicorn

from cyberbrain.dreaming.adapters.mcp_micro_reasoner import MCPMicroReasoner
from cyberbrain.dreaming.adapters.mcp_transport import MCPStreamableHTTPInvoker
from cyberbrain.dreaming.reasoner import EvidenceItem, ReasoningTask, ReasoningTaskKind
from cyberbrain.reasoner_provider.http import create_reasoner_app
from cyberbrain.reasoner_provider.server import configure_micro_backend


class NetworkMicroBackend:
    def reason_task(self, request: dict):
        return {
            "task_id": request["task_id"],
            "claims": [
                {
                    "claim": "Network MCP round-trip succeeded.",
                    "evidence_ids": [item["id"] for item in request["evidence"]],
                    "confidence": 0.93,
                }
            ],
        }


def test_real_streamable_http_micro_reasoner_round_trip() -> None:
    configure_micro_backend(NetworkMicroBackend())
    app = create_reasoner_app(auth_token="network-secret", require_auth=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    config = uvicorn.Config(app, log_level="critical", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started

    try:
        invoker = MCPStreamableHTTPInvoker(
            url=f"http://127.0.0.1:{port}/mcp",
            bearer_token="network-secret",
            timeout_seconds=5,
        )
        reasoner = MCPMicroReasoner(invoker=invoker, tool="reason_task")
        task = ReasoningTask(
            task_id="network-task-1",
            request_id="network-request-1",
            topic="CyberBrain",
            kind=ReasoningTaskKind.DURABLE_LESSON,
            instruction="Return one evidence-grounded lesson.",
            evidence=[
                EvidenceItem(
                    id="11111111-1111-4111-8111-111111111111",
                    record_type="knowledge",
                    content="MCP is the preferred Reasoner transport.",
                    score=0.9,
                    event_time=datetime(2026, 9, 4, tzinfo=UTC),
                )
            ],
        )

        result = reasoner.reason_task(task)

        assert result.task_id == task.task_id
        assert result.claims[0].claim == "Network MCP round-trip succeeded."
        assert result.claims[0].evidence_ids == ["11111111-1111-4111-8111-111111111111"]
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()
