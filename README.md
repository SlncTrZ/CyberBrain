# CyberBrain

[![CI](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml/badge.svg)](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml)

CyberBrain is a portable knowledge and memory system for AI agents.

It provides canonical Knowledge, Episodic Memory, retrieval, Knowledge Evolution, and
evidence-grounded Dreaming with traceable reasoning and explicit promotion/review gates.

## Status

Current software/package version is defined only in `cyberbrain/_version.py`. Git tags, build metadata, runtime providers, CI, and release automation derive from that canonical value.

For the latest published release, use the repository's GitHub Releases page rather than a duplicated version literal in this README.

The repository is in use-and-observe mode: changes should be driven by reproducible defects,
operational evidence, security/privacy needs, or portability gaps rather than speculative feature
growth. See [Project Status](docs/PROJECT_STATUS.md) for the dated source/release/runtime snapshot.

GitHub CI validates lint, the full automated test suite, package build, Compose configuration, and
container build on supported changes.

## Core architecture

    AI clients / agents
      consume / produce memory
           ↓
    CyberBrain MCP/API
           ↓
    Knowledge + Memory + post-storage cognition
           ↓
    Qdrant + Embedding Runtime

CyberBrain intentionally keeps exactly two canonical durable Qdrant collections:

    cyberbrain_knowledge
    cyberbrain_episodic

Dreaming is a process, not a third collection. Queue, audit, and reason-task coordination state are
operational state stored separately from canonical Knowledge and Episodic Memory.

## Normal agent loop

Normal external agents are memory consumers/producers. Their ordinary workflow is intentionally small:

```text
need context → search → optionally exact get
worth persisting → knowledge_store or memory_store
```

CyberBrain owns what happens after storage: normalization, validation, embedding, Knowledge Evolution, the Episodic pending lifecycle, automatic Dream scheduling/processing, promotion/review, and Knowledge writeback. Prediction Learning preserves pre-outcome causal order and must not be reconstructed retrospectively.

## Dreaming

Dreaming is evidence-grounded consolidation. A reasoning result cannot write Knowledge directly. It must pass contract validation, evidence-ID validation, promotion policy, and review/writeback rules before canonical Knowledge changes.

Dream reasoning is deployment-configurable and provider-neutral: external MCP consumers get the first claim/submit window on unfinished tasks; only unfinished tasks continue to ordered fallback LLM routes configured by the deployer. CyberBrain hard-codes no provider, model catalog, or routing product. See [Dreaming Routing](docs/DREAMING_ROUTING.md).

## Run with Docker Compose

Base stack:

    cp .env.example .env
    # Set CYBERBRAIN_MCP_AUTH_TOKEN in .env.
    docker compose up -d

Dreaming stack:

    cp config/dream-routes.example.json config/dream-routes.json
    # Edit the route file and provide the referenced provider credentials in the runtime environment.
    # Also configure CYBERBRAIN_DREAM_REASONER_BEARER_TOKEN.
    docker compose --profile dreaming up -d

The default Compose stack includes CyberBrain, Qdrant, and the embedding runtime. The dreaming
profile additionally starts the Dream worker, configured LLM route reasoner, and server-side pending-session scheduler (nightly by default). Ordinary pending Episodes are discovered automatically; `dream_enqueue` remains an explicit/manual control path.

See [Current Runtime](docs/CURRENT_RUNTIME.md) for the source-level runtime contract.

## MCP

CyberBrain exposes authenticated MCP Streamable HTTP at /mcp with provider-local tool names.

[MCP_PROVIDER_STANDARD.md](MCP_PROVIDER_STANDARD.md) is the repository's reference integration standard for gateway-compatible provider behavior. Current tool behavior is documented in [TOOL_GUIDE.md](TOOL_GUIDE.md) and [specs/TOOL_CONTRACT.md](specs/TOOL_CONTRACT.md).

Canonical `knowledge_search` and `memory_search` are compact-first: broad recall returns a bounded excerpt or existing summary, and one selected full record is fetched via `knowledge_get` / `memory_get`. Response projection never alters stored content, embeddings, ranking, provenance, or Dreaming evidence.

## Documentation

| Need | Start here |
| --- | --- |
| Browse all documentation | [Documentation index](docs/README.md) |
| Check source/release/runtime evidence | [Project Status](docs/PROJECT_STATUS.md), [Source Acceptance](docs/SOURCE_ACCEPTANCE.md) |
| Use the MCP tools | [Tool Guide](TOOL_GUIDE.md) |
| Run or configure the service | [Current Runtime](docs/CURRENT_RUNTIME.md), [Tenancy](docs/TENANCY_OPERATIONS.md) |
| Configure Dream fallback routes | [Dreaming Routing](docs/DREAMING_ROUTING.md) |
| Migrate schema or enable relations | [V2 Migration Runbook](docs/V2_MIGRATION_RUNBOOK.md), [Relation Rollout](docs/RELATION_ROLLOUT.md) |
| Review priorities | [Plan](PLAN.md) |
| Understand a cognitive mechanism | [specs/](specs/) via the [Plan roadmap](PLAN.md#cognitive-roadmap) |

## Development rule

Keep business logic independent from individual clients, providers, models, and deployment
topologies.

Preferred sequence:

    audit → define boundaries → specify → implement deliberately → test

## License

CyberBrain is licensed under the Mozilla Public License 2.0 (MPL-2.0).
