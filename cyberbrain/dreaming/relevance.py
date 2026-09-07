# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
from collections.abc import Iterable

from cyberbrain.dreaming.reasoner import EvidenceItem

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PHASE_RE = re.compile(r"\bphase[\s._-]*(\d+)\b", re.IGNORECASE)

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

        topic_phase = self._phase(topic)
        if len(anchors) == 1 and topic_phase is None:
            return True

        text_phases = set(_PHASE_RE.findall(text))
        if topic_phase is not None and topic_phase not in text_phases:
            return False

        tokens = set(_TOKEN_RE.findall(text.casefold()))
        matched = [anchor for anchor in anchors if self._anchor_matches(anchor, tokens)]
        if not matched or matched[0] != anchors[0]:
            return False

        required = 1 if len(anchors) == 1 else 2
        return len(matched) >= required

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
