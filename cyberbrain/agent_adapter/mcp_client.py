# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from cyberbrain.core.errors import ProviderResponseError
from cyberbrain.dreaming.adapters.mcp_transport import MCPStreamableHTTPInvoker


class AsyncToolInvoker(Protocol):
    async def invoke_async(self, *, tool: str, arguments: dict[str, Any]) -> Any: ...


class MCPAgentClient:
    """MCP client for the minimal Agent Adapter memory contract plus advanced controls.

    UniversalAgentAdapter uses only recall/get/store methods. Prediction and Dream operations remain
    explicit MCP control surfaces for callers that intentionally opt into those mechanisms.
    """

    def __init__(self, invoker: AsyncToolInvoker) -> None:
        self._invoker = invoker

    @classmethod
    def streamable_http(
        cls,
        *,
        url: str,
        bearer_token: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> MCPAgentClient:
        return cls(
            MCPStreamableHTTPInvoker(
                url=url,
                bearer_token=bearer_token,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
        )

    async def _call(self, tool: str, arguments: dict[str, Any]) -> Any:
        clean = {key: value for key, value in arguments.items() if value is not None}
        return await self._invoker.invoke_async(tool=tool, arguments=clean)

    @staticmethod
    def _dict_payload(tool: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ProviderResponseError(f"{tool} returned a non-object payload")
        return value

    @staticmethod
    def _list_payload(tool: str, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ProviderResponseError(f"{tool} returned a non-list payload")
        return list(value)

    async def knowledge_search(
        self,
        *,
        query: str,
        limit: int = 5,
        view: str = "compact",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        value = await self._call(
            "knowledge_search",
            {"query": query, "limit": limit, "view": view, **filters},
        )
        return self._list_payload("knowledge_search", value)

    async def knowledge_get(self, *, record_id: str) -> dict[str, Any] | None:
        try:
            value = await self._call("knowledge_get", {"id": record_id})
        except ProviderResponseError as exc:
            if exc.error_type == "not_found":
                return None
            raise
        return self._dict_payload("knowledge_get", value)

    async def knowledge_timeline(self, **identity: Any) -> list[dict[str, Any]]:
        value = await self._call("knowledge_timeline", dict(identity))
        return self._list_payload("knowledge_timeline", value)

    async def memory_search(
        self,
        *,
        query: str,
        limit: int = 5,
        view: str = "compact",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        value = await self._call(
            "memory_search",
            {"query": query, "limit": limit, "view": view, **filters},
        )
        return self._list_payload("memory_search", value)

    async def memory_get(self, *, record_id: str) -> dict[str, Any] | None:
        try:
            value = await self._call("memory_get", {"id": record_id})
        except ProviderResponseError as exc:
            if exc.error_type == "not_found":
                return None
            raise
        return self._dict_payload("memory_get", value)

    async def memory_store(
        self,
        *,
        content: str,
        session_id: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]:
        value = await self._call(
            "memory_store",
            {
                "content": content,
                "session_id": session_id,
                "event_time": event_time.isoformat(),
                **metadata,
            },
        )
        return self._dict_payload("memory_store", value)

    async def prediction_record(
        self,
        *,
        expected_outcome: str,
        confidence: float,
        session_id: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]:
        value = await self._call(
            "prediction_record",
            {
                "expected_outcome": expected_outcome,
                "confidence": confidence,
                "session_id": session_id,
                "event_time": event_time.isoformat(),
                **metadata,
            },
        )
        return self._dict_payload("prediction_record", value)

    async def prediction_resolve(
        self,
        *,
        prediction_id: str,
        observed_outcome: str,
        assessment: str,
        event_time: datetime,
        **metadata: Any,
    ) -> dict[str, Any]:
        value = await self._call(
            "prediction_resolve",
            {
                "prediction_id": prediction_id,
                "observed_outcome": observed_outcome,
                "assessment": assessment,
                "event_time": event_time.isoformat(),
                **metadata,
            },
        )
        return self._dict_payload("prediction_resolve", value)

    async def prediction_pending(
        self,
        *,
        limit: int = 5,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        value = await self._call("prediction_pending", {"limit": limit, **filters})
        if isinstance(value, dict):
            value = value.get("items")
        return self._list_payload("prediction_pending", value)

    async def dream_enqueue(
        self,
        *,
        session_id: str,
        focal_topics: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        value = await self._call(
            "dream_enqueue",
            {
                "session_id": session_id,
                "topics": list(focal_topics) if focal_topics is not None else None,
            },
        )
        return self._dict_payload("dream_enqueue", value)
