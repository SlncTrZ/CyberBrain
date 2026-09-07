# CyberBrain — Current Plan

> Status: Current project guidance.
> Release baseline: v0.1.5.

## Operating mode

CyberBrain is in a use-and-observe phase. The project should prefer evidence-driven fixes and
measured improvements over speculative expansion.

## Current product boundary

CyberBrain provides:

- canonical Knowledge storage, retrieval, and evolution;
- canonical Episodic Memory storage and retrieval;
- evidence-grounded Dreaming with review/promotion gates;
- authenticated MCP/API access;
- provider-neutral Dream fallback routing;
- backup, migration, and compatibility tooling.

CyberBrain remains independent from any single AI client, model provider, routing product, or
deployment topology.

## Current architectural invariants

1. Canonical durable data uses exactly two Qdrant collections:
   - cyberbrain_knowledge
   - cyberbrain_episodic
2. Dreaming is a process, not a third collection.
3. Dreaming reasoning is evidence-grounded and cannot write Knowledge directly.
4. External MCP reasoning gets the first common run-level opportunity; unfinished tasks may then
   use ordered LLM routes configured by the deployer.
5. Provider/model choice belongs to deployment configuration, not core domain logic.
6. Operational Dream state uses SQLite unless a demonstrated requirement justifies a different
   mechanism.
7. Storage and embedding remain behind adapters.
8. Authentication fails closed when required credentials are missing.
9. Secrets never belong in tracked configuration, prompts, logs, or tool results.
10. Compatibility aliases are adapters only and must not become a second business-logic path.

## Change policy

New work should be justified by one or more of:

- a reproducible correctness defect;
- observed operational friction;
- security or privacy risk;
- portability/reproducibility gap;
- measurable quality evidence;
- a compatibility requirement with a clear owner and retirement path.

Do not add architecture, UI, distributed coordination, provider-specific discovery, or model policy
only because it may become useful later.

## Current documentation

Normative/current guidance:

- README.md
- TOOL_GUIDE.md
- MCP_PROVIDER_STANDARD.md
- docs/CURRENT_RUNTIME.md
- docs/DREAMING_ROUTING.md
- specs/

Historical development and migration evidence lives under docs/history/ and is non-normative.

## Historical plan

The original V1 development plan is preserved at:

docs/history/DEVELOPMENT_PLAN_V1.md
