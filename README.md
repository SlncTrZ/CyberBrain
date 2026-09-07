# CyberBrain

[![CI](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml/badge.svg)](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml)

CyberBrain is a portable knowledge + memory infrastructure for AI agents.

It provides durable knowledge storage, episodic memory, retrieval, Knowledge Evolution, and a first-class Dreaming Engine that consolidates experience into smaller evidence-backed conclusions.

## Status

V1 complete / production use-and-observe mode.

CyberBrain now implements canonical Knowledge, Episodic Memory, Dreaming, MCP/API, migration, backup/restore, Reasoner integration, and legacy compatibility. The current production compatibility endpoint is running the CyberBrain V1 provider against staged canonical V1 collections while the original legacy collections and snapshots remain available for rollback.

Current verification baseline:

- automated unit and contract tests enforced by GitHub CI
- Ruff clean
- canonical staged migration validated with preserved point IDs/vectors
- no duplicate-active canonical identities in the V1 stage
- Dreaming full lifecycle verified through review approval and Knowledge Evolution writeback
- Dream worker routing verified with MCP-first reasoning and user-configured ordered LLM fallback routes
- dependency-aware `/ready` probe verified for Qdrant + embedding availability
- MCP Streamable HTTP `/mcp`, authenticated `help`, canonical tools, and temporary MeiLin compatibility aliases verified

## Core architecture

```text
AI clients / agents
       ↓
CyberBrain MCP/API
       ↓
Knowledge Engine + Memory Engine + Dreaming Engine
       ↓
Qdrant + Embedding Runtime
```

CyberBrain V1 intentionally keeps two canonical Qdrant collections:

```text
cyberbrain_knowledge
cyberbrain_episodic
```

During migration/cutover, validated staged collections may use explicit temporary names such as `cyberbrain_knowledge_v1_stage` and `cyberbrain_episodic_v1_stage`; those names are deployment artifacts, not additional domain concepts.

Dreaming is a consolidation process, not a third collection.

## MCP standard

CyberBrain follows `MCP_PROVIDER_STANDARD.md` and is intended to become the first reference provider implementation for the SlncTrZ-MCP ecosystem.

Key requirements include:

- MCP Streamable HTTP at `/mcp`
- authenticated network access
- canonical gateway namespace `cyberbrain.*`
- mandatory read-only `cyberbrain.help`
- provider-local MCP tool names with gateway-owned canonical namespacing
- stable tool/version/error contracts
- no credentials in source, prompts, URLs, logs, or tool results

## Dreaming routes

Dreaming routing is deployment-configurable and provider-neutral:

```text
MCP reasoner session
       ↓ unfinished tasks only
LLM provider 1: model 1A → model 1B → ...
       ↓
LLM provider 2: model 2A → model 2B → ...
       ↓
...
```

CyberBrain does not hard-code a provider, model catalog, or external routing service. Copy
`config/dream-routes.example.json` to `config/dream-routes.json`, then define providers and
models in the exact order you want them tried. Provider credentials are referenced by environment
variable name through `auth_env`; secret values do not belong in the route file or Git.

The `dreaming` Docker Compose profile starts the Dream worker, configured LLM route reasoner,
and nightly scheduler from code contained in this repository.

## Project documents

- `PLAN.md` — development roadmap and architecture direction
- `MCP_PROVIDER_STANDARD.md` — shared MCP provider contract
- `specs/` — data, retrieval, evolution, dreaming, security, and tool specifications
- `docs/` — audit, migration, release, and operations documents
- `migration_artifacts/` — local/private migration evidence (snapshots, manifests, validation reports, checksums); intentionally excluded from source control because it may contain real production data

## Development rule

Do not copy MeiLin wholesale and refactor blindly.

```text
audit → define boundaries → specify → extract deliberately
```

## License

CyberBrain is licensed under the Mozilla Public License 2.0 (`MPL-2.0`).
