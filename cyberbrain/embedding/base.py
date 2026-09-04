# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def version(self) -> str: ...

    def embed(self, text: str) -> list[float]: ...
