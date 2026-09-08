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
