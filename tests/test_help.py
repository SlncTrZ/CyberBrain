# SPDX-License-Identifier: MPL-2.0

import asyncio

from cyberbrain.mcp.server import call_tool


def test_help_returns_runtime_contract() -> None:
    result = asyncio.run(call_tool("help", {}))
    text = result[0].text
    assert "provider_name: cyberbrain" in text
    assert "contract_version: 1" in text
    assert "contract_hash:" in text
    assert "CyberBrain Tool Guide" in text
