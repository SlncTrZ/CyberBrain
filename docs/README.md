# CyberBrain Documentation

The documentation tree separates current normative guidance from historical evidence.

## Current guidance

- CURRENT_RUNTIME.md — current deployment-neutral runtime contract and service boundaries.
- DREAMING_ROUTING.md — provider-neutral MCP-first Dream routing and ordered LLM route configuration.
- V2_MIGRATION_RUNBOOK.md — current schema-V2 staging, independent validation, metadata review, canary, cutover gate, rollback, and stop conditions.
- ../TOOL_GUIDE.md — current MCP tool behavior.
- ../PLAN.md — current operating mode and architectural invariants.
- ../specs/RETRIEVAL_POLICY.md — canonical retrieval/ranking rules plus compact/full MCP response projection.
- ../specs/TOOL_CONTRACT.md — canonical MCP tool contract, including compact-first search views.
- ../specs/VERSIONING.md — single software/package version authority and independent contract/schema versioning.
- ../specs/SALIENCE.md — canonical M3 Salience signals, policy, authorization boundary, benchmark, and advisory/shadow contract.
- ../specs/CONCEPT_FORMATION.md — canonical E1/M4 evidence quality, concept candidate identity/discovery, stability, counterexamples, and fail-closed promotion contract.
- ../specs/WORKING_MEMORY.md — canonical M5 exact task-scoped transient active-set, relevance/Salience ordering, token budget, TTL/closeout, delta emission, and benchmark contract.
- ../specs/AGENT_SELF_MODEL.md — canonical M6 trusted evidence, readiness, deterministic hypothesis generation, review, persistence, and bounded Working Memory advisory contract.
- ../specs/MEMORY_LIFECYCLE.md — canonical M7 shadow scoring, reversible suppression/reactivation, access tracking, and real-corpus activation gates.
- ../specs/KNOWLEDGE_SCHEMA.md / MEMORY_SCHEMA.md — canonical schema-V2 metadata contracts, including identity provenance and lifecycle fields.
- ../specs/ — remaining canonical evolution, Dreaming, Reasoner, security, Prediction Learning, Calibration, retrieval, and schema contracts.

## Historical evidence

All migration, cutover, freeze, release-candidate, data-audit, and earlier runtime snapshots live in:

- history/

Historical files are preserved for provenance. They may contain dates, counts, temporary collection
names, compatibility service slots, acceptance-window instructions, or benchmark results that were
true at the time but are not current operating instructions.

When current and historical documents differ, current guidance and canonical specs take precedence.

## Source versus runtime status

Current local source contains the integrated single-owner caller authority binding, expanded tenancy foundations, scope-safe exact fetch, the MCP Agent Adapter client bridge, literal/fingerprint shadow observation, completed M3 Salience/M4 Concept Formation/M5 Working Memory, complete source-level M6 Agent Self-Model, complete source-level M7 Memory Lifecycle, schema-V2 metadata contracts, V2 migration/validation tooling, the server-owned post-storage cognition boundary, and single software/package version authority. Level-8.0 remains a source-engineering checkpoint, not a deployment claim. M6/M7 controlled fixtures demonstrate contract behavior only; real-corpus assessment follows full V2 migration/validation. Caller-visible lexical promotion and broader multi-user/search/write tenancy enforcement remain pending. `CURRENT_RUNTIME.md`, `../TOOL_GUIDE.md`, and canonical specs describe source state; release, deployed runtime, and migrated-data state remain independent.
