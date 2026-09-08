# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import cyberbrain
from cyberbrain.reasoner_provider import server as reasoner_server

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "cyberbrain" / "_version.py"


def test_pyproject_derives_version_from_canonical_file() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)

    project = config["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]
    assert config["tool"]["hatch"]["version"]["path"] == "cyberbrain/_version.py"


def test_runtime_providers_use_canonical_package_version() -> None:
    assert f"provider_version: {cyberbrain.__version__}\n" in reasoner_server._help_text()


def test_current_version_literal_has_one_authority() -> None:
    canonical = cyberbrain.__version__
    authority_files = [
        ROOT / "pyproject.toml",
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / ".github" / "workflows" / "release.yml",
        *sorted((ROOT / "cyberbrain").rglob("*.py")),
    ]

    duplicates = []
    for path in authority_files:
        if path == VERSION_FILE:
            continue
        if canonical in path.read_text(encoding="utf-8"):
            duplicates.append(str(path.relative_to(ROOT)))

    assert duplicates == []


def test_current_normative_docs_do_not_duplicate_semver_literals() -> None:
    semver = re.compile(r"(?<![A-Za-z0-9])v?\d+\.\d+\.\d+(?![A-Za-z0-9])")
    docs = [
        ROOT / "README.md",
        ROOT / "PLAN.md",
        ROOT / "TOOL_GUIDE.md",
        ROOT / "AGENTS.md",
        ROOT / "MCP_PROVIDER_STANDARD.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "specs").glob("*.md")),
    ]

    duplicates = []
    for path in docs:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if semver.search(line):
                duplicates.append(f"{path.relative_to(ROOT)}:{line_number}")

    assert duplicates == []
