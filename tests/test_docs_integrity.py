# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HISTORY = DOCS / "history"

CURRENT_DOC_FILES = {
    "README.md",
    "CURRENT_RUNTIME.md",
    "DREAMING_ROUTING.md",
}

REFERENCE_PATTERN = re.compile(r"`([^`]+.(?:md|json|ya?ml))`")
GENERATED_REFERENCES = {
    "config/dream-routes.json",
}


def test_docs_top_level_contains_only_current_guidance() -> None:
    actual = {path.name for path in DOCS.glob("*.md")}

    assert actual == CURRENT_DOC_FILES


def test_every_historical_document_is_explicitly_labeled() -> None:
    for path in HISTORY.glob("*.md"):
        if path.name == "README.md":
            continue
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:8]).casefold()
        assert "historical" in head, f"{path} is missing a historical label"


def test_current_runtime_document_is_date_independent() -> None:
    text = (DOCS / "CURRENT_RUNTIME.md").read_text(encoding="utf-8")

    assert "source-level runtime contract" in text
    assert "CURRENT_RUNTIME_2026-09-04" not in text
    assert "V1_FREEZE_2026-09-04" not in text


def test_document_references_resolve() -> None:
    files = [
        ROOT / "README.md",
        ROOT / "PLAN.md",
        ROOT / "TOOL_GUIDE.md",
        ROOT / "AGENTS.md",
        ROOT / "MCP_PROVIDER_STANDARD.md",
        *sorted(DOCS.rglob("*.md")),
        *sorted((ROOT / "specs").glob("*.md")),
    ]

    missing: list[tuple[str, str]] = []
    for source in files:
        text = source.read_text(encoding="utf-8")
        for reference in REFERENCE_PATTERN.findall(text):
            if reference in GENERATED_REFERENCES or "<" in reference or ">" in reference:
                continue

            candidates = (
                ROOT / reference,
                source.parent / reference,
            )
            if not any(candidate.exists() for candidate in candidates):
                missing.append((str(source.relative_to(ROOT)), reference))

    assert missing == []


def test_illustrative_yaml_states_that_runtime_does_not_load_it() -> None:
    text = (ROOT / "config" / "cyberbrain.example.yaml").read_text(
        encoding="utf-8"
    )

    assert "runtime does NOT load this YAML file" in text
