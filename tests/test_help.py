# SPDX-License-Identifier: MPL-2.0

import asyncio
import hashlib
import json
import re

from jsonschema import Draft202012Validator
from mcp.types import Tool

from cyberbrain.mcp import server as provider
from cyberbrain.mcp.help_reference import render_tool_reference


def test_help_returns_runtime_contract_without_runtime(monkeypatch) -> None:
    monkeypatch.setattr(provider, "_runtime", None)
    result = asyncio.run(provider.call_tool("help", {}))
    text = result[0].text
    assert "provider_name: cyberbrain" in text
    assert "contract_version: 1" in text
    assert "schema_version: 2" in text
    assert "updated_at: 2026-10-02" in text
    assert "CyberBrain Tool Guide" in text
    header, content = text.split("\n\n", 1)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert f"contract_hash: {digest}" in header
    assert text == asyncio.run(provider.call_tool("help", {}))[0].text


def test_help_covers_catalog_fields_and_nested_definitions() -> None:
    tools = asyncio.run(provider.list_tools())
    reference = render_tool_reference(tools)
    for tool in tools:
        assert f"### `{tool.name}`" in reference
        for name in tool.inputSchema.get("properties", {}):
            assert f"| {name} |" in reference
        for name in tool.inputSchema.get("$defs", {}):
            assert f"#### Definition: {name}" in reference
    assert '"maximum":50' in reference
    assert '"maxLength":1024' in reference
    assert '"anyOf"' in reference
    assert '"evidence_ids"' in reference


def test_help_schema_change_updates_reference_and_fingerprint(monkeypatch) -> None:
    before = provider._help_payload()
    tools = provider._tool_catalog()
    changed = tools[0].model_copy(update={
        "inputSchema": {
            "type": "object",
            "properties": {"new_option": {"type": "integer", "default": 7, "maximum": 9}},
            "additionalProperties": False,
        },
    })
    monkeypatch.setattr(provider, "_tool_catalog", lambda: [changed, *tools[1:]])
    after = provider._help_payload()
    assert "| new_option | no / conditional | integer | 7 |" in after
    assert '"maximum":9' in after
    before_hash = before.split("contract_hash: ", 1)[1].splitlines()[0]
    after_hash = after.split("contract_hash: ", 1)[1].splitlines()[0]
    assert before_hash != after_hash


def test_reference_preserves_constraints_without_inventing_defaults() -> None:
    tool = Tool(name="fixture", description="Read fixture", inputSchema={
        "type": "object",
        "properties": {
            "unknown_default": {"type": ["string", "null"], "pattern": "a|b"},
            "explicit_null": {"type": ["string", "null"], "default": None},
            "value": {"type": "integer", "minimum": 2},
        },
        "required": ["value"],
        "additionalProperties": False,
    })
    reference = render_tool_reference([tool])
    assert "not declared" in reference
    assert "| explicit_null | no / conditional |" in reference
    assert "| null |" in reference
    assert "| value | yes | integer |" in reference
    assert "a&#124;b" in reference
    assert '"additionalProperties":false' in reference


def test_guide_call_examples_validate_against_advertised_schemas() -> None:
    guide = provider._guide_path().read_text(encoding="utf-8")
    catalog = {tool.name: tool.inputSchema for tool in asyncio.run(provider.list_tools())}
    examples = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", guide, re.S)]
    calls = [example for example in examples if "name" in example]
    assert len(calls) >= 9
    for call in calls:
        validator = Draft202012Validator(catalog[call["name"]])
        validator.validate(call["arguments"])
    assert {call["name"] for call in calls} >= {
        "knowledge_search", "knowledge_get", "knowledge_store", "memory_store",
        "knowledge_relations", "knowledge_relation_review",
    }
