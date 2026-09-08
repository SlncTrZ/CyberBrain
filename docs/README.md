# CyberBrain Documentation

The documentation tree separates current normative guidance from historical evidence.

## Current guidance

- CURRENT_RUNTIME.md — current deployment-neutral runtime contract and service boundaries.
- DREAMING_ROUTING.md — provider-neutral MCP-first Dream routing and ordered LLM route configuration.
- ../TOOL_GUIDE.md — current MCP tool behavior.
- ../PLAN.md — current operating mode and architectural invariants.
- ../specs/RETRIEVAL_POLICY.md — canonical retrieval/ranking rules plus compact/full MCP response projection.
- ../specs/TOOL_CONTRACT.md — canonical MCP tool contract, including compact-first search views.
- ../specs/VERSIONING.md — single software/package version authority and independent contract/schema versioning.
- ../specs/SALIENCE.md — canonical M3 Salience signals, policy, authorization boundary, benchmark, and advisory/shadow contract.
- ../specs/CONCEPT_FORMATION.md — canonical E1/M4 evidence quality, concept candidate identity/discovery, stability, counterexamples, and fail-closed promotion contract.
- ../specs/WORKING_MEMORY.md — canonical M5 exact task-scoped transient active-set, relevance/Salience ordering, token budget, TTL/closeout, delta emission, and benchmark contract.
- ../specs/ — remaining canonical data, evolution, Dreaming, Reasoner, security, Prediction Learning, and Calibration contracts.

## Historical evidence

All migration, cutover, freeze, release-candidate, data-audit, and earlier runtime snapshots live in:

- history/

Historical files are preserved for provenance. They may contain dates, counts, temporary collection
names, compatibility service slots, acceptance-window instructions, or benchmark results that were
true at the time but are not current operating instructions.

When current and historical documents differ, current guidance and canonical specs take precedence.

## Source versus runtime status

Current `main` contains the integrated single-owner caller authority binding, expanded tenancy domain foundations, scope-safe exact `knowledge_get` / `memory_get`, the real MCP Agent Adapter client bridge, literal/fingerprint shadow observation with a reusable BM25 corpus, completed source-level M3 Salience, M4 Concept Formation, and M5 Working Memory primitives, the tested server-owned post-storage cognition boundary, and the single software/package version authority. Normal agents recall/get/store; CyberBrain owns Dream scheduling/processing, Knowledge Evolution, promotion/review, and writeback. Caller-visible lexical promotion and broader multi-user/search/write tenancy enforcement remain pending. `CURRENT_RUNTIME.md`, `../TOOL_GUIDE.md`, and `../specs/TOOL_CONTRACT.md` describe the source-level contract; release and deployment state are independent and may differ.
