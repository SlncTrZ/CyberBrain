# SPDX-License-Identifier: MPL-2.0
"""Read-only help reference derived from the public MCP catalog."""

from __future__ import annotations

import json

from mcp.types import Tool


def _cell(value: str) -> str:
    return value.replace("|", "&#124;").replace("\n", " ")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema_table(schema: dict, label: str) -> list[str]:
    lines = [f"#### {label}", ""]
    required = set(schema.get("required", []))
    properties = schema.get("properties", {})
    if properties:
        lines.extend([
            "| Parameter | Required | Type | Declared default | Constraints / nested schema |",
            "| --- | --- | --- | --- | --- |",
        ])
        for name, field in properties.items():
            kind = field.get("type", field.get("$ref", "see schema"))
            constraints = {
                key: value for key, value in field.items()
                if key not in {"type", "default", "title", "description"}
            }
            default = _json(field["default"]) if "default" in field else "not declared"
            cells = [
                name, "yes" if name in required else "no / conditional",
                _json(kind) if isinstance(kind, list) else str(kind),
                default, _json(constraints) if constraints else "—",
            ]
            lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
        lines.append("")
    else:
        lines.extend(["No named parameters.", ""])
    # Preserve alternatives, nested validation, enums and future schema keywords.
    rules = {
        key: value for key, value in schema.items()
        if key not in {"properties", "$defs", "title", "description", "type", "required"}
    }
    if rules:
        lines.extend(["Object/value rules: `" + _cell(_json(rules)) + "`.", ""])
    if schema.get("required"):
        lines.extend(["Required fields: `" + _cell(_json(schema["required"])) + "`.", ""])
    return lines


def render_tool_reference(tools: list[Tool]) -> str:
    lines = [
        "## Runtime parameter reference",
        "",
        "Generated from the same catalog returned by MCP tools/list. Names are provider-local;",
        "use the gateway namespace when applicable. Required alternatives and nested constraints",
        "are part of the input contract. No / conditional does not override object/value rules.",
        "Not declared means the schema has no default; omission is resolved by runtime logic,",
        "not inferred here. Domain validation, authorization and evidence gates still apply.",
        "",
    ]
    for tool in tools:
        lines.extend([f"### `{tool.name}`", "", tool.description or "", ""])
        schema = tool.inputSchema
        lines.extend(_schema_table(schema, "Arguments"))
        for name, definition in schema.get("$defs", {}).items():
            lines.extend(_schema_table(definition, f"Definition: {name}"))
    return "\n".join(lines)
