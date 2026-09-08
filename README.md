# CyberBrain

[![CI](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml/badge.svg)](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml)

CyberBrain is a portable knowledge and memory system for AI agents.

It provides canonical Knowledge, Episodic Memory, retrieval, Knowledge Evolution, and
evidence-grounded Dreaming with traceable reasoning and explicit promotion/review gates.

## Status

Current software/package version is defined only in `cyberbrain/_version.py`. Git tags, build metadata, runtime providers, CI, and release automation derive from that canonical value.

For the latest published release, use the repository's GitHub Releases page rather than a duplicated version literal in this README.

Current `main` includes the integrated Level 8+ infrastructure completed through the server-owned post-storage cognition and single-version-authority work. Public release state and deployed runtime state are separate from source state; verify them independently rather than inferring either from this README.

The repository is in use-and-observe mode: changes should be driven by reproducible defects,
operational evidence, security/privacy needs, or portability gaps rather than speculative feature
growth.

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

## Current Level 8+ integration

The current source integrates the completed Wave 1 foundations and the shared Wave 2 wiring:

- `cyberbrain/agent_adapter/` includes a real MCP Streamable HTTP client bridge for optional foreground convenience such as token budgeting, duplicate-context suppression, compact recall, and bounded exact fetch. It is not the owner of Dreaming, Knowledge Evolution, Calibration, or other background cognition;
- `cyberbrain/retrieval/` includes a reproducible real-snapshot benchmark harness. The reviewed 28-case current-vector comparison rejects always-on global hybrid fusion; the deterministic literal/fingerprint lexical route remains SHADOW ONLY pending larger reviewed relevance/reliability evidence;
- `cyberbrain/tenancy/` now binds authenticated source requests to explicit caller authority in `single_owner` mode and supplies storage-side eligibility for canonical exact fetch. `agent_ready` and `multi_user` modes fail closed until trusted caller identity and the required persisted identity fields are wired.

Current source exposes scope-safe `knowledge_get` and `memory_get` and supports the preferred compact-search → selected-ID → exact-full-fetch flow. Normal external agents are memory consumers/producers: they recall/get/store while CyberBrain owns normalization, Knowledge Evolution, the Episodic pending lifecycle, automatic Dream scheduling/processing, promotion/review, and Knowledge writeback. The canonical retrieval backend remains vector search: the real benchmark did **not** justify replacing it with always-on hybrid fusion. Source also includes disabled-by-default literal/fingerprint shadow instrumentation with a reusable pre-tokenized BM25 corpus so repeated shadow queries do not rebuild lexical document statistics. Live observation has cleared the earlier recurring shadow-scoring performance blocker, but caller-visible lexical routing remains unpromoted pending larger relevance/reliability evidence. Broader tenancy enforcement on all search/write paths remains pending. Public release packaging remains a separate explicit decision.

## Learning primitives

Main now includes the first bounded cognitive-learning mechanism: Prediction Learning (Prediction / Outcome / Prediction Error).

Prediction Learning can record an explicit expected outcome and prior confidence before an action, then resolve that prediction with an observed outcome and finite assessment. CyberBrain stores both as canonical Episodic evidence and derives a transparent prediction-error signal. This is an explicit causal-learning surface, not a required ordinary-agent read/write loop; predictions must not be fabricated retrospectively after the outcome is known.

See specs/PREDICTION_LEARNING.md. Main also contains an initial read-only Calibration analysis over resolved Prediction Learning evidence. It does not persist self-beliefs or change agent strategy. Initial end-to-end MCP gateway validation has passed; both mechanisms remain in observation. See specs/METACOGNITION_CALIBRATION.md.

## Dreaming

Dreaming is evidence-grounded consolidation. Dreaming V1 historical replay acceptance is complete and the mechanism is in use-and-observe mode.

A reasoning result cannot write Knowledge directly. It must pass contract validation, evidence-ID
validation, promotion policy, and review/writeback rules before canonical Knowledge changes.

Dream reasoning is deployment-configurable and provider-neutral:

    MCP reasoner session
           ↓ unfinished tasks only
    LLM provider 1: model 1A → model 1B → ...
           ↓
    LLM provider 2: model 2A → model 2B → ...
           ↓
    ...

CyberBrain does not hard-code a provider, model catalog, commercial routing policy, or external
routing product.

For fallback LLM routing, copy:

    config/dream-routes.example.json

to:

    config/dream-routes.json

Then define providers and models in the exact order they should be attempted. Credentials are
referenced by environment-variable name through auth_env; secret values do not belong in the route
file or Git.

See docs/DREAMING_ROUTING.md.

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

See docs/CURRENT_RUNTIME.md for the source-level runtime contract.

## MCP

CyberBrain exposes authenticated MCP Streamable HTTP at /mcp and provider-local MCP tool names.

MCP_PROVIDER_STANDARD.md is the repository's reference integration standard for gateway-compatible
provider behavior. CyberBrain's domain model does not depend on one specific gateway deployment.

Current tool behavior is documented in TOOL_GUIDE.md and specs/TOOL_CONTRACT.md.

Canonical `knowledge_search` and `memory_search` are compact-first at the MCP response boundary: existing summaries are returned when available, otherwise recall falls back to a bounded 1,200-character excerpt. Current source also exposes scope-safe `knowledge_get` and `memory_get` so a client can fetch one selected full record without repeating semantic search. Broad-search `view=full` remains available when explicitly required. None of these response paths alter stored content, embeddings, ranking, provenance, or Dreaming evidence.

## Documentation

Current guidance:

- PLAN.md — current project operating mode and architectural invariants.
- TOOL_GUIDE.md — current MCP tool behavior.
- specs/VERSIONING.md — single software/package version authority and independent contract/schema versioning.
- docs/CURRENT_RUNTIME.md — deployment-neutral runtime contract.
- docs/DREAMING_ROUTING.md — provider-neutral Dream fallback routing.
- specs/ — canonical data, retrieval, evolution, Dreaming, security, Reasoner, and tool contracts.

Historical evidence:

- docs/history/ — V1 development plan, migration audits, staged migration reports, freeze/release
  snapshots, and earlier runtime evidence.

Historical documents are preserved for provenance and are not current operating instructions.

## Development rule

Keep business logic independent from individual clients, providers, models, and deployment
topologies.

Preferred sequence:

    audit → define boundaries → specify → implement deliberately → test

## License

CyberBrain is licensed under the Mozilla Public License 2.0 (MPL-2.0).
