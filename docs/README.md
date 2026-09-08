# CyberBrain Documentation

The documentation tree separates current normative guidance from historical evidence.

## Current guidance

- CURRENT_RUNTIME.md — current deployment-neutral runtime contract and service boundaries.
- DREAMING_ROUTING.md — provider-neutral MCP-first Dream routing and ordered LLM route configuration.
- ../TOOL_GUIDE.md — current MCP tool behavior.
- ../PLAN.md — current operating mode and architectural invariants.
- ../specs/RETRIEVAL_POLICY.md — canonical retrieval/ranking rules plus compact/full MCP response projection.
- ../specs/TOOL_CONTRACT.md — canonical MCP tool contract, including compact-first search views.
- ../specs/ — remaining canonical data, evolution, Dreaming, Reasoner, security, Prediction Learning, and Calibration contracts.

## Historical evidence

All migration, cutover, freeze, release-candidate, data-audit, and earlier runtime snapshots live in:

- history/

Historical files are preserved for provenance. They may contain dates, counts, temporary collection
names, compatibility service slots, acceptance-window instructions, or benchmark results that were
true at the time but are not current operating instructions.

When current and historical documents differ, current guidance and canonical specs take precedence.

## Source versus runtime status

Current `main` contains unreleased Wave 2 integration for single-owner caller authority binding, scope-safe exact `knowledge_get` / `memory_get`, and the real MCP Agent Adapter client bridge. Hybrid retrieval, automatic Agent Adapter lifecycle activation, and broader multi-user/search/write tenancy enforcement remain pending. `CURRENT_RUNTIME.md`, `../TOOL_GUIDE.md`, and `../specs/TOOL_CONTRACT.md` describe the current source-level contract; deployment may remain on an older explicitly managed source until a separate release/deployment decision.
