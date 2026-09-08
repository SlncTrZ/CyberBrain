# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import unicodedata

_RESERVED = {"*", "all", "any", "__all__", "__any__"}


def normalize_identifier(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("identity identifier must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError("identity identifier must not be empty")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise ValueError("identity identifier must not contain control characters")
    if normalized.casefold() in _RESERVED or "*" in normalized:
        raise ValueError("wildcard-like identity identifiers are not allowed")
    if len(normalized) > 128:
        raise ValueError("identity identifier exceeds 128 characters")
    return normalized
