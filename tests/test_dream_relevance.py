# SPDX-License-Identifier: MPL-2.0

from cyberbrain.dreaming.relevance import TopicRelevanceGuard


def test_service_persistence_allows_systemd_boot_fact() -> None:
    guard = TopicRelevanceGuard()

    assert guard.text_relevant(
        topic="MCP service persistence after reboot",
        text=(
            "systemd units om-mcp.service and dia-mcp.service use Restart=always "
            "and auto-start on boot"
        ),
    )


def test_service_persistence_rejects_stale_removed_provider_fact() -> None:
    guard = TopicRelevanceGuard()

    assert not guard.text_relevant(
        topic="MCP service persistence after reboot",
        text="DeepDive MCP was removed but stale configuration still causes ECONNREFUSED.",
    )


def test_hardening_runtime_identity_rejects_add_mcp_and_clean_room_identity() -> None:
    guard = TopicRelevanceGuard()

    assert not guard.text_relevant(
        topic="SlncTrZ-MCP hardening runtime identity",
        text="Form Add MCP on owner web added an args field for stdio transport.",
    )
    assert not guard.text_relevant(
        topic="SlncTrZ-MCP hardening runtime identity",
        text=(
            "SlncTrZ-MCP project identity uses independent clean-room implementation "
            "with TypeScript and Node.js runtime."
        ),
    )
    assert guard.text_relevant(
        topic="SlncTrZ-MCP hardening runtime identity",
        text="Runtime identity hardening removed hard-coded build version values.",
    )


def test_phase_anchor_rejects_neighboring_phase_and_requires_standalone_anchor() -> None:
    guard = TopicRelevanceGuard()
    topic = "SlncTrZ-MCP Phase 8 standalone quality gates"

    assert guard.text_relevant(
        topic=topic,
        text="Phase 8 standalone SEA Linux x64 quality validation passed.",
    )
    assert not guard.text_relevant(
        topic=topic,
        text="Phase 5 extension gateway baseline has a clean working tree.",
    )
    assert not guard.text_relevant(
        topic=topic,
        text="Phase 8 owner UI permissions passed all checks.",
    )


def test_core_write_phase_three_rejects_gpu_benchmark() -> None:
    guard = TopicRelevanceGuard()
    topic = "SlncTrZ-MCP core.write Phase 3 quality gates"

    assert guard.text_relevant(
        topic=topic,
        text="core.write Phase 3 passed Linux CI but mode-bit validation failed on Windows.",
    )
    assert not guard.text_relevant(
        topic=topic,
        text="qwen3 CPU outperformed GPU 940MX during benchmark testing.",
    )


def test_clean_room_oauth_requires_clean_room_plus_another_anchor() -> None:
    guard = TopicRelevanceGuard()
    topic = "SlncTrZ-MCP clean-room OAuth provenance"

    assert guard.text_relevant(
        topic=topic,
        text="Clean-room OAuth authorization provenance was derived from public RFCs.",
    )
    assert not guard.text_relevant(
        topic=topic,
        text="Phase 2 authorization completed with a bounded dynamic client pool.",
    )
