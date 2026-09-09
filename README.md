# CyberBrain

[![CI](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml/badge.svg)](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml)

CyberBrain is a portable knowledge and memory system for AI agents.

It provides canonical Knowledge, Episodic Memory, retrieval, Knowledge Evolution, and
evidence-grounded Dreaming with traceable reasoning and explicit promotion/review gates.

## Status

Current software/package version is defined only in `cyberbrain/_version.py`. Git tags, build metadata, runtime providers, CI, and release automation derive from that canonical value.

For the latest published release, use the repository's GitHub Releases page rather than a duplicated version literal in this README.

Current source has satisfied the Level-8.0 source-engineering gate and contains source-complete M6 Agent Self-Model, M7 Memory Lifecycle, canonical schema V2, and deterministic migration/validation tooling alongside the server-owned post-storage cognition and single-version-authority foundations. The current production storage configuration has completed a validated schema-V2 cutover. This is still not a final Level-8.5+ behavioral-evidence claim: M6 remains evidence-gated and M7 remains shadow-only pending richer real-corpus lifecycle evidence.

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
- `cyberbrain/tenancy/` includes trusted-identity/enforcement/quota/readiness foundations. Authenticated source requests may additionally bind a server-configured trusted agent only after credential verification; `agent_ready`/`multi_user` still remain fail-closed while broader search/write/background enforcement and persisted identity requirements are incomplete;
- `cyberbrain/salience/` provides the completed source-level M3 deterministic scorer, reviewed priority policy, same-scope advisory seam, and metrics-only shadow observer. Salience is not wired into canonical search and cannot broaden authorization;
- `cyberbrain/concepts/` provides completed source-level M4 deterministic concept-candidate discovery, evidence/counterexample retention, same-scope Salience prioritization, an in-memory stability registry, and a fail-closed review/reject promotion gate. It adds no graph database, no concept collection, and no automatic Knowledge writer;
- `cyberbrain/working_memory/` provides completed source-level M5 exact task-scoped transient active context with explicit task relevance, Salience-informed ordering, duplicate suppression, Token Governor limits, TTL/closeout, and delta emission. It adds no durable store or public MCP surface and remains unwired from production runtime pending shared authorization integration.

Current source exposes scope-safe `knowledge_get` and `memory_get` and supports the preferred compact-search → selected-ID → exact-full-fetch flow. Normal external agents are memory consumers/producers: they recall/get/store while CyberBrain owns normalization, Knowledge Evolution, the Episodic pending lifecycle, automatic Dream scheduling/processing, promotion/review, and Knowledge writeback. The canonical retrieval backend remains vector search: the real benchmark did **not** justify replacing it with always-on hybrid fusion. Source also includes disabled-by-default literal/fingerprint shadow instrumentation with a reusable pre-tokenized BM25 corpus so repeated shadow queries do not rebuild lexical document statistics. Live observation has cleared the earlier recurring shadow-scoring performance blocker, but caller-visible lexical routing remains unpromoted pending larger relevance/reliability evidence. Broader tenancy enforcement on all search/write paths remains pending. Public release packaging remains a separate explicit decision.

## Learning primitives

Main now includes the first bounded cognitive-learning mechanism: Prediction Learning (Prediction / Outcome / Prediction Error).

Prediction Learning can record an explicit expected outcome and prior confidence before an action, then resolve that prediction with an observed outcome and finite assessment. CyberBrain stores both as canonical Episodic evidence and derives a transparent prediction-error signal. This is an explicit causal-learning surface, not a required ordinary-agent read/write loop; predictions must not be fabricated retrospectively after the outcome is known.

See specs/PREDICTION_LEARNING.md. Main also contains an initial read-only Calibration analysis over resolved Prediction Learning evidence. It does not persist self-beliefs or change agent strategy. Initial end-to-end MCP gateway validation has passed; both mechanisms remain in observation. See specs/METACOGNITION_CALIBRATION.md.

Salience / Priority M3 is now complete at the source level. The scorer is deterministic and explainable, the reviewed policy is benchmarked against trivial baselines, cross-scope advisory calls fail closed, and shadow observation is metrics-only. Salience remains advisory and is intentionally not connected to caller-visible retrieval while full search-path tenancy enforcement is still pending. See specs/SALIENCE.md.

Concept Formation / Abstraction M4 is also complete at the source level. A read-only E1 census separates clean shadow evidence from review-only or excluded historical evidence before concept discovery. The accepted high-precision policy requires broad recurrence for Knowledge-only clusters, retains evidence IDs and counterexamples, rejects same-entity repetition as insufficient abstraction, and records candidate stability without durable persistence. Reviewed historical candidates currently fail durable promotion because they lack strong verification, so no automatic concept Knowledge write exists. See specs/CONCEPT_FORMATION.md.

Working Memory / Active Context M5 is complete at the source level. `WorkingMemoryService` keeps exact scope/session/task transient state only; candidate selection is explicit task relevance → Salience → duplicate suppression → token budget, with hard limits, TTL, closeout, and unchanged-context emission suppression. A controlled 4-task/16-step benchmark improves required-context coverage from 67.35% to 100% while lowering context tokens from 1045 to 458, recall calls from 16 to 4, and exact fetches from 12 to 4, with zero stale contamination or cross-task leakage in the fixture. This does not activate a production Working Memory path or claim LLM task-quality improvement. See specs/WORKING_MEMORY.md.

Agent Self-Model M6 is now source-complete as a bounded evidence/review pipeline. Trusted prospective Prediction/Outcome evidence passes a fail-closed readiness gate before deterministic capability/limitation/workflow hypotheses can be generated. Hypotheses start `pending`; only explicitly accepted hypotheses may persist through Knowledge Evolution as `record_class=self_model_hypothesis`, with `ordinary_recall=false`, and only accepted hypotheses may be projected into M5 as bounded advisory context. M6 still has no authority to mutate prompts, tools, permissions, routing, model weights, or identity truth. Real-corpus M6 quality remains unevaluated until schema-V2 migration/validation is complete. See specs/AGENT_SELF_MODEL.md.

Memory Lifecycle M7 is also source-complete. It owns deterministic shadow lifecycle scoring, reversible soft suppression through `lifecycle_state=suppressed` + `ordinary_recall=false`, reactivation, and access metadata. It does not hard-delete canonical memory as its normal forgetting path and does not change Knowledge truth/evolution status. Controlled source fixtures cover keep/suppress/reactivate behavior; real-corpus lifecycle thresholds remain an evaluation question after V2 migration. See specs/MEMORY_LIFECYCLE.md.

Canonical Knowledge and Episodic payloads now use schema V2. V2 adds explicit identity provenance (`identity_trust`), lifecycle metadata, Knowledge `record_class`, and Episode `updated_at`. Migration tooling stages a union of canonical V1 stage data plus raw legacy deltas, preserves point IDs/content/vectors, and quarantines records that cannot be normalized safely instead of fabricating required metadata. Source schema/tooling completeness is not a claim that the production Qdrant collections have already been migrated or cut over.

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
- docs/V2_MIGRATION_RUNBOOK.md — current stage-before-cutover schema-V2 migration, independent validation, canary, rollback, and stop-condition procedure.
- specs/MEMORY_LIFECYCLE.md — canonical M7 lifecycle contract.
- specs/ — canonical data, retrieval, evolution, Dreaming, security, Reasoner, M3–M7 cognition, migration/schema, and tool contracts.

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
