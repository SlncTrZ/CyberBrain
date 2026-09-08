# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re

_LITERAL_PATTERN = re.compile(
    r"\b[0-9a-f]{7,40}\b"
    r"|\b\d+\.\d+(?:\.\d+)?\b"
    r"|\b\d{4,5}\b"
    r"|\b[\w.-]+:[\w.-]+\b"
    r"|\b\d+/\d+\b",
    re.IGNORECASE,
)


def literal_heavy_query(query: str) -> bool:
    """Detect strong lexical/fingerprint signals without model inference."""

    return bool(_LITERAL_PATTERN.search(query))
