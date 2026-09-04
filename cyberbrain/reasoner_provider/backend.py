# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any, Protocol


class ReasoningBackend(Protocol):
    def reason(self, request: dict[str, Any]) -> dict[str, Any]: ...


class MicroReasoningBackend(Protocol):
    def reason_task(self, request: dict[str, Any]) -> dict[str, Any]: ...
