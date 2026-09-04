# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
from dataclasses import dataclass

from cyberbrain.core.errors import SensitiveDataError

_PLACEHOLDER_MARKERS = (
    "redacted",
    "example",
    "placeholder",
    "your_api_key",
    "your-api-key",
    "your_token",
    "your-token",
    "changeme",
    "dummy",
    "fake",
)

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.IGNORECASE),
    ),
    (
        "openai_api_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "github_token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    (
        "aws_access_key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    (
        "bearer_token",
        re.compile(r"\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    ),
    (
        "credential_assignment",
        re.compile(
            r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd)\s*[:=]\s*"
            r"['\"]?([^\s'\";,]{10,})",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_url",
        re.compile(r"https?://[^\s/:@]+:[^\s/@]{6,}@[^\s]+", re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class SecretFinding:
    kind: str


class SecretScanner:
    def scan(self, text: str) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for kind, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                candidate = match.group(0)
                if self._looks_like_placeholder(candidate):
                    continue
                findings.append(SecretFinding(kind=kind))
                break
        return findings

    def assert_safe(self, *texts: str | None) -> None:
        kinds: set[str] = set()
        for text in texts:
            if not text:
                continue
            kinds.update(finding.kind for finding in self.scan(str(text)))
        if kinds:
            joined = ", ".join(sorted(kinds))
            raise SensitiveDataError(f"sensitive data rejected before ingestion: {joined}")

    @staticmethod
    def _looks_like_placeholder(candidate: str) -> bool:
        lowered = candidate.casefold()
        if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            return True
        if "${" in candidate or "{{" in candidate or "<" in candidate:
            return True
        return False
