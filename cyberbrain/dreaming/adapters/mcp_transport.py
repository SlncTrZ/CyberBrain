# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from datetime import timedelta
from time import monotonic
from typing import Any

import anyio
import httpx
import mcp.types as types
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from cyberbrain.core.errors import ProviderResponseError, ProviderUnavailableError
from cyberbrain.core.metrics import MetricsRegistry


class MCPStreamableHTTPInvoker:
    """Concrete synchronous tool invoker backed by MCP Streamable HTTP."""

    def __init__(
        self,
        *,
        url: str,
        bearer_token: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError("MCP URL must use http or https")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self._url = url
        self._bearer_token = bearer_token
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics

    def invoke(self, *, tool: str, arguments: dict[str, Any]) -> Any:
        if not tool.strip():
            raise ValueError("tool must not be empty")
        started = monotonic()
        try:
            result = anyio.run(self._call_tool, tool, dict(arguments))
            if self._metrics is not None:
                self._metrics.increment("reasoner_calls_total")
                self._metrics.observe("reasoner_call_seconds", monotonic() - started)
        except ProviderResponseError:
            if self._metrics is not None:
                self._metrics.increment("reasoner_response_failures_total")
                self._metrics.observe("reasoner_call_seconds", monotonic() - started)
            raise
        except Exception as exc:
            if self._metrics is not None:
                self._metrics.increment("reasoner_transport_failures_total")
                self._metrics.observe("reasoner_call_seconds", monotonic() - started)
            raise ProviderUnavailableError(
                f"MCP provider unavailable for tool {tool!r}: {type(exc).__name__}"
            ) from exc
        return self._parse_result(result)

    async def _call_tool(self, tool: str, arguments: dict[str, Any]) -> types.CallToolResult:
        headers: dict[str, str] = {}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        timeout = httpx.Timeout(self._timeout_seconds)
        read_timeout = timedelta(seconds=self._timeout_seconds)
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
            async with streamable_http_client(
                self._url,
                http_client=client,
                terminate_on_close=True,
            ) as (read_stream, write_stream, _session_id):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=read_timeout,
                ) as session:
                    await session.initialize()
                    return await session.call_tool(
                        tool,
                        arguments,
                        read_timeout_seconds=read_timeout,
                    )

    @staticmethod
    def _parse_result(result: types.CallToolResult) -> Any:
        if result.structuredContent is not None:
            payload = result.structuredContent
            return MCPStreamableHTTPInvoker._validate_payload(payload, result.isError)

        texts = [
            content.text
            for content in result.content
            if isinstance(content, types.TextContent)
        ]
        if not texts:
            raise ProviderResponseError("MCP tool returned no JSON-compatible content")

        parsed: Any = None
        for text in texts:
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, (dict, list)):
                parsed = value
                break
        if parsed is None:
            raise ProviderResponseError("MCP tool did not return a JSON object or array")
        return MCPStreamableHTTPInvoker._validate_payload(parsed, result.isError)

    @staticmethod
    def _validate_payload(payload: Any, is_error: bool) -> Any:
        error = payload.get("error") if isinstance(payload, dict) else None
        if is_error or isinstance(error, dict):
            error_type = "provider_error"
            message = "MCP provider returned an error"
            if isinstance(error, dict):
                error_type = str(error.get("type") or error_type)
                message = str(error.get("message") or message)
            raise ProviderResponseError(f"{error_type}: {message}")
        return payload
