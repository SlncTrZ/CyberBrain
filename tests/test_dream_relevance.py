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


def test_commit_identifier_requires_exact_identifier_match() -> None:
    guard = TopicRelevanceGuard()
    topic = "SlncTrZ-MCP commit 396bd64 hidden bugs"

    assert guard.text_relevant(
        topic=topic,
        text="Commit 396bd64 exposed Windows ACL failures and hidden bugs.",
    )
    assert not guard.text_relevant(
        topic=topic,
        text=(
            "SlncTrZ-MCP architecture checkpoint records commit history and hidden "
            "runtime caveats without the audited commit identifier."
        ),
    )


def test_topic_excerpt_is_bounded_and_keeps_phase_local_context() -> None:
    guard = TopicRelevanceGuard()
    topic = "SlncTrZ-MCP Phase 5 extension gateway"
    transcript = "\n".join(
        [
            *(f"unrelated historical line {index}" for index in range(300)),
            "Phase 5 — Universal MCP Extension Gateway",
            "The extension gateway routes authorized extension tools through MCP.",
            "Phase 5 acceptance was completed with transport lifecycle boundaries.",
            *(f"unrelated later line {index}" for index in range(300)),
        ]
    )

    excerpt = guard.topic_excerpt(topic=topic, text=transcript)

    assert excerpt is not None
    assert len(excerpt) <= 3600
    assert "Phase 5" in excerpt
    assert "extension gateway" in excerpt.casefold()
    assert "unrelated historical line 0" not in excerpt


def test_claim_relevance_allows_single_anchor_topic_without_repetition() -> None:
    guard = TopicRelevanceGuard()

    assert guard.claim_relevant(
        topic="routing",
        text="Configured provider order is deterministic.",
    )


def test_claim_relevance_keeps_entity_fact_without_repeating_process_word() -> None:
    guard = TopicRelevanceGuard()
    topic = "ComfyUI update v0.30.2 v0.33.3"

    assert guard.claim_relevant(
        topic=topic,
        text="ComfyUI official version is 0.33.x.",
    )
    assert not guard.claim_relevant(
        topic=topic,
        text="Kernel and plugin packages are already aligned.",
    )


def test_claim_relevance_keeps_exact_phase_and_identifier_guards() -> None:
    guard = TopicRelevanceGuard()

    assert guard.claim_relevant(
        topic="SlncTrZ-MCP Phase 5 extension gateway",
        text="Phase 5 gateway acceptance passed on Windows.",
    )
    assert not guard.claim_relevant(
        topic="SlncTrZ-MCP Phase 5 extension gateway",
        text="Phase 6 gateway acceptance passed on Windows.",
    )
    assert guard.claim_relevant(
        topic="SlncTrZ-MCP commit 396bd64 hidden bugs",
        text="Commit 396bd64 exposed Windows ACL failures.",
    )
    assert not guard.claim_relevant(
        topic="SlncTrZ-MCP commit 396bd64 hidden bugs",
        text="Commit 77cafd1 completed read-only hardening.",
    )


def test_topic_excerpt_can_combine_distributed_session_anchors() -> None:
    guard = TopicRelevanceGuard()
    topic = "SlncTrZ-MCP Phase 0 infrastructure foundation"
    transcript = "\n".join(
        [
            "Phase 0 completed and pushed.",
            *(f"phase context {index}" for index in range(20)),
            "The gateway is infrastructure-grade rather than a script.",
            *(f"middle context {index}" for index in range(20)),
            "Root commit initializes the repository foundation.",
        ]
    )

    excerpt = guard.topic_excerpt(
        topic=topic,
        text=transcript,
        max_chars=1200,
        context_lines=1,
    )

    assert excerpt is not None
    assert "Phase 0" in excerpt
    assert "infrastructure-grade" in excerpt
    assert "repository foundation" in excerpt


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
