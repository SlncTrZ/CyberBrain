# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
from collections.abc import Iterable

from cyberbrain.dreaming.reasoner import EvidenceItem

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PHASE_RE = re.compile(r"\bphase[\s._-]*(\d+)\b", re.IGNORECASE)
_IDENTIFIER_RE = re.compile(r"(?=.*[a-z])(?=.*\d)[a-z0-9]{6,}")

_GENERIC_TOPIC_TOKENS = {
    "a",
    "an",
    "and",
    "after",
    "before",
    "for",
    "from",
    "gate",
    "gates",
    "in",
    "mcp",
    "of",
    "on",
    "phase",
    "project",
    "quality",
    "slnctrz",
    "the",
    "to",
    "with",
}

_ANCHOR_ALIASES = {
    "oauth": {"authorization", "authorisation", "oauth"},
    "persistence": {"autostart", "persist", "persistence", "persistent"},
    "reboot": {"boot", "reboot", "restart", "restarted", "restarting"},
    "standalone": {"sea", "standalone"},
    "write": {"write", "writes", "writing"},
}


class TopicRelevanceGuard:
    """Deterministic lexical guard for focal-topic Dream evidence and claims.

    Vector similarity remains useful for recall, but a bounded Dream topic must also keep a
    recognizable lexical anchor. Structured ``Phase N`` topics additionally require the same
    phase number so neighboring project phases cannot be consolidated into each other.
    """

    def filter_evidence(
        self,
        *,
        topic: str,
        items: Iterable[EvidenceItem],
    ) -> list[EvidenceItem]:
        return [item for item in items if self.evidence_relevant(topic=topic, item=item)]

    def evidence_relevant(self, *, topic: str, item: EvidenceItem) -> bool:
        searchable = " ".join(
            value
            for value in (
                item.content,
                str(item.metadata.get("domain") or ""),
                str(item.metadata.get("topic") or ""),
                str(item.metadata.get("entity_name") or ""),
                str(item.metadata.get("association_query") or ""),
            )
            if value
        )
        return self.text_relevant(topic=topic, text=searchable)

    def text_relevant(self, *, topic: str, text: str) -> bool:
        anchors = self._anchors(topic)
        if not anchors:
            return True

        tokens = set(_TOKEN_RE.findall(text.casefold()))
        identifiers = [anchor for anchor in anchors if _IDENTIFIER_RE.fullmatch(anchor)]
        if identifiers:
            return all(identifier in tokens for identifier in identifiers)

        topic_phase = self._phase(topic)
        if len(anchors) == 1 and topic_phase is None:
            return True

        text_phases = set(_PHASE_RE.findall(text))
        if topic_phase is not None and topic_phase not in text_phases:
            return False

        matched = [anchor for anchor in anchors if self._anchor_matches(anchor, tokens)]
        if not matched or matched[0] != anchors[0]:
            return False

        required = 1 if len(anchors) == 1 else 2
        return len(matched) >= required

    def topic_excerpt(
        self,
        *,
        topic: str,
        text: str,
        max_chars: int = 3600,
        context_lines: int = 3,
        max_windows: int = 4,
    ) -> str | None:
        value = text.strip()
        if not value:
            return None
        if len(value) <= max_chars:
            return value if self.text_relevant(topic=topic, text=value) else None

        lines = [line.strip() for line in value.splitlines() if line.strip()]
        if not lines:
            return None

        anchors = self._anchors(topic)
        topic_phase = self._phase(topic)
        identifiers = [anchor for anchor in anchors if _IDENTIFIER_RE.fullmatch(anchor)]
        ranked: list[tuple[int, int]] = []
        for index, line in enumerate(lines):
            tokens = set(_TOKEN_RE.findall(line.casefold()))
            score = 0
            if topic_phase is not None and topic_phase in set(_PHASE_RE.findall(line)):
                score += 8
            for identifier in identifiers:
                if identifier in tokens:
                    score += 12
            for position, anchor in enumerate(anchors):
                if self._anchor_matches(anchor, tokens):
                    score += 4 if position == 0 else 2
            if score:
                ranked.append((score, index))

        if not ranked:
            return None

        selected: list[tuple[int, int]] = []
        for _score, index in sorted(ranked, key=lambda item: (-item[0], item[1])):
            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)
            window = "\n".join(lines[start:end])
            if not self.text_relevant(topic=topic, text=window):
                continue
            overlaps = any(
                not (end <= prior_start or start >= prior_end)
                for prior_start, prior_end in selected
            )
            if overlaps:
                continue
            selected.append((start, end))
            if len(selected) >= max_windows:
                break

        if not selected:
            return None

        parts: list[str] = []
        used = 0
        for start, end in sorted(selected):
            part = "\n".join(lines[start:end])
            separator = "\n...\n" if parts else ""
            remaining = max_chars - used - len(separator)
            if remaining <= 0:
                break
            if len(part) > remaining:
                part = part[:remaining].rstrip()
            if part:
                parts.append(part)
                used += len(separator) + len(part)
        return "\n...\n".join(parts) or None

    @staticmethod
    def _phase(value: str) -> str | None:
        match = _PHASE_RE.search(value)
        return match.group(1) if match is not None else None

    @staticmethod
    def _anchors(topic: str) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for token in _TOKEN_RE.findall(topic.casefold()):
            if token.isdigit() or token in _GENERIC_TOPIC_TOKENS or token in seen:
                continue
            seen.add(token)
            result.append(token)
        return result

    @staticmethod
    def _anchor_matches(anchor: str, tokens: set[str]) -> bool:
        aliases = _ANCHOR_ALIASES.get(anchor, {anchor})
        if aliases & tokens:
            return True
        if len(anchor) < 6:
            return False
        prefix = anchor[:5]
        return any(len(token) >= 6 and token.startswith(prefix) for token in tokens)
