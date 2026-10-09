# CyberBrain — Current Plan

> Status: Current project guidance.
> Software/package version authority: `cyberbrain/_version.py`; release tags derive from it.
> Deployment state is managed separately from source guidance; verify the actual runtime before making deployment claims.

## Operating mode

CyberBrain has satisfied the Level-8.0 source-engineering gate and completed the validated schema-V2 production cutover with the M3–M7 cognitive path active. The project should prefer evidence-driven fixes and measured improvements over speculative expansion.

The remaining program is operational and evidence-driven; see [Project Status](docs/PROJECT_STATUS.md) for the dated F0–F4 checklist. Global Workspace or additional broad cognitive architecture is not a completion requirement.

## Current product boundary

CyberBrain provides:

- canonical Knowledge storage, retrieval, and evolution;
- canonical Episodic Memory storage and retrieval;
- evidence-grounded Dreaming with review/promotion gates;
- authenticated MCP/API access;
- provider-neutral Dream fallback routing;
- backup, migration, and compatibility tooling;
- active bounded M3–M7 server cognition over already-authorized recall/store events;
- canonical schema-V2 metadata normalization plus staged migration/validation tooling.

CyberBrain remains independent from any single AI client, model provider, routing product, or deployment topology.

Normal external agents are memory consumers/producers. Their stable responsibility is recall/get/store. CyberBrain owns post-storage cognition: normalization, validation, embedding, Knowledge Evolution, Episodic pending-state processing, automatic Dream scheduling/processing, promotion/review, and Knowledge writeback. Prediction Learning preserves causal order and may use a thin pre-action/outcome event bridge where a runtime genuinely exposes those events; it must not be reconstructed retrospectively.

Shared integration is serialized rather than parallel. The security/order invariant is:

```text
authenticated caller
→ effective authority/scope
→ hard storage/read eligibility
→ scope-safe exact fetch / retrieval
→ optional foreground Agent Adapter context packing
→ server-owned post-storage cognition
```

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
11. Canonical broad recall is compact-first at the MCP response boundary. Full stored content remains available only through an explicit full-view request; response projection must not change ranking, storage, provenance, or evidence semantics.
12. External agents are memory consumers/producers; CyberBrain owns post-storage cognition.
13. `dream_enqueue` is an explicit/manual control path, not a required step after ordinary Episodic storage.
14. Prediction evidence must preserve pre-outcome causal order; retrospective prediction fabrication is invalid.

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

## Cognitive roadmap

The roadmap extracts useful mechanisms from human cognition into measurable technical primitives.
It is a dependency graph with explicit ownership, not a rigid feature checklist. By default, keep
only one new mechanism in active implementation at a time.

| Mechanism | Status | Contract |
| --- | --- | --- |
| Prediction Learning | Implemented; observation active | [specs/PREDICTION_LEARNING.md](specs/PREDICTION_LEARNING.md) |
| Calibration | Read-only analysis implemented; observation active | [specs/METACOGNITION_CALIBRATION.md](specs/METACOGNITION_CALIBRATION.md) |
| Salience / Priority (M3) | Complete, active after authorized prefetch | [specs/SALIENCE.md](specs/SALIENCE.md) |
| Concept Formation (M4) | Complete as bounded discovery; durable promotion reviewed separately | [specs/CONCEPT_FORMATION.md](specs/CONCEPT_FORMATION.md) |
| Working Memory (M5) | Complete, active transient scope/session/task state | [specs/WORKING_MEMORY.md](specs/WORKING_MEMORY.md) |
| Agent Self-Model (M6) | Source-complete; fail-closed until trusted readiness passes | [specs/AGENT_SELF_MODEL.md](specs/AGENT_SELF_MODEL.md) |
| Memory Lifecycle (M7) | Source-complete; event-by-event actuation, no bulk sweep | [specs/MEMORY_LIFECYCLE.md](specs/MEMORY_LIFECYCLE.md) |
| Typed relation traversal | Source-complete; explicit caller/Dream opt-in | [specs/RELATION_TRAVERSAL.md](specs/RELATION_TRAVERSAL.md) |

A mechanism's source implementation is complete when it has a written contract, one clearly owned
decision class, explicit data ownership/lifecycle, deterministic validation where possible, tests
for correctness and failure modes, provenance/evidence boundaries, and safe defaults with explicit
rollout boundaries.

Post-deployment usefulness belongs to [docs/LIVE_EVALUATION.md](docs/LIVE_EVALUATION.md), normally
reviewed after 30 days and again after 60 days of real use. Existing prospective evidence
thresholds still control each runtime conclusion.

The roadmap must preserve these distinctions:

```text
observation != belief
belief != knowledge
confidence != truth
salience != truth
repetition != correctness
self-model != identity truth
```

No cognitive mechanism may bypass the existing evidence, review, provenance, or Knowledge Evolution
gates. The intended long-term direction is continuity of learning for agents without requiring CyberBrain
to modify the underlying model weights.

## Current documentation

Normative/current guidance:

- README.md
- TOOL_GUIDE.md
- MCP_PROVIDER_STANDARD.md
- docs/CURRENT_RUNTIME.md
- docs/PROJECT_STATUS.md
- docs/ — acceptance, tenancy, evaluation, routing, migration, and rollout guides,
  including [docs/V2_MIGRATION_RUNBOOK.md](docs/V2_MIGRATION_RUNBOOK.md)
- specs/ — canonical data, retrieval, evolution, Dreaming, security, Reasoner, M3–M7 cognition, migration/schema, and tool contracts

Historical development and migration evidence lives under docs/history/ and is non-normative.
The original V1 development plan is preserved at docs/history/DEVELOPMENT_PLAN_V1.md.
