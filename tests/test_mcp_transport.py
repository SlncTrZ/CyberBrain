# SPDX-License-Identifier: MPL-2.0

import json

import mcp.types as types
import pytest

from cyberbrain.core.errors import ProviderResponseError, ProviderUnavailableError
from cyberbrain.dreaming.adapters.mcp_transport import MCPStreamableHTTPInvoker


def test_transport_parses_structured_content() -> None:
    result = types.CallToolResult(content=[], structuredContent={"task_id": "t1", "claims": []})

    parsed = MCPStreamableHTTPInvoker._parse_result(result)

    assert parsed == {"task_id": "t1", "claims": []}


def test_transport_parses_json_text_content() -> None:
    payload = {"task_id": "t1", "claims": []}
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload))]
    )

    assert MCPStreamableHTTPInvoker._parse_result(result) == payload


def test_transport_rejects_provider_error_envelope() -> None:
    result = types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": {
                            "type": "validation_error",
                            "message": "bad task",
                            "retryable": False,
                        }
                    }
                ),
            )
        ]
    )

    with pytest.raises(ProviderResponseError, match="validation_error: bad task"):
        MCPStreamableHTTPInvoker._parse_result(result)


def test_transport_rejects_non_json_content() -> None:
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text="not json")]
    )

    with pytest.raises(ProviderResponseError, match="JSON object"):
        MCPStreamableHTTPInvoker._parse_result(result)


def test_transport_wraps_connection_failure_without_exposing_credentials() -> None:
    class FailingInvoker(MCPStreamableHTTPInvoker):
        async def _call_tool(self, tool, arguments):  # noqa: ANN001, ANN201
            raise RuntimeError("low-level transport error")

    invoker = FailingInvoker(
        url="http://reasoner.test/mcp",
        bearer_token="secret-bearer-value",
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        invoker.invoke(tool="reason_task", arguments={})

    assert "secret-bearer-value" not in str(exc_info.value)
    assert "reason_task" in str(exc_info.value)
