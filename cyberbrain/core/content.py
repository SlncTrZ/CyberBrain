# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib


def normalize_content(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("content must not be empty")
    return normalized


def content_hash(content: str) -> str:
    normalized = normalize_content(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
