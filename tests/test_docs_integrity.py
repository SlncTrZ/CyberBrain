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
    "V2_MIGRATION_RUNBOOK.md",
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
    text = (ROOT / "config" / "cyberbrain.example.yaml").read_text(encoding="utf-8")

    assert "runtime does NOT load this YAML file" in text


def test_level8_current_guidance_includes_m7_and_v2_runbook() -> None:
    docs_index = (DOCS / "README.md").read_text(encoding="utf-8")
    plan = (ROOT / "PLAN.md").read_text(encoding="utf-8")

    assert "V2_MIGRATION_RUNBOOK.md" in docs_index
    assert "MEMORY_LIFECYCLE.md" in docs_index
    assert "V2_MIGRATION_RUNBOOK.md" in plan
    assert (ROOT / "specs" / "MEMORY_LIFECYCLE.md").exists()


def test_current_guidance_does_not_embed_private_deployment_paths() -> None:
    files = [
        ROOT / "README.md",
        ROOT / "PLAN.md",
        ROOT / "TOOL_GUIDE.md",
        ROOT / "AGENTS.md",
        *sorted(DOCS.glob("*.md")),
        *sorted((ROOT / "specs").glob("*.md")),
        ROOT / "config" / "docker-compose.v2-canary.example.yml",
    ]
    forbidden = ("/home/dinhtc", "/mnt/pc-dev", "docker-all_default")

    leaked: list[tuple[str, str]] = []
    for source in files:
        text = source.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                leaked.append((str(source.relative_to(ROOT)), marker))

    assert leaked == []


def test_active_cognition_runtime_contract_is_current() -> None:
    runtime_spec = ROOT / "specs" / "COGNITIVE_RUNTIME_PATH.md"
    assert runtime_spec.exists()
    text = runtime_spec.read_text(encoding="utf-8")
    assert "M3 Salience" in text
    assert "M4" in text and "M5" in text and "M6" in text and "M7" in text
    assert "no automatic full-corpus suppression sweep" in text
    current = (DOCS / "CURRENT_RUNTIME.md").read_text(encoding="utf-8")
    assert "actively wires M3–M7" in current
    assert "M7 Memory Lifecycle is active event-by-event" in current
