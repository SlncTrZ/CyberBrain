# CyberBrain — Current Plan

> Status: Current project guidance.
> Software/package version authority: `cyberbrain/_version.py`; release tags derive from it.
> Deployment state is managed separately from source guidance; verify the actual runtime before making deployment claims.

## Operating mode

CyberBrain has satisfied the Level-8.0 source-engineering gate and contains source-complete M6 Agent Self-Model, M7 Memory Lifecycle, canonical schema V2, and deterministic migration/validation tooling. The full corpus has completed validated schema-V2 production cutover. Source tenancy implementation and long-term M6/M7 effectiveness are assessed independently. The project should prefer evidence-driven fixes and measured improvements over speculative expansion.

## Current product boundary

CyberBrain provides:

- canonical Knowledge storage, retrieval, and evolution;
- canonical Episodic Memory storage and retrieval;
- evidence-grounded Dreaming with review/promotion gates;
- authenticated MCP/API access;
- provider-neutral Dream fallback routing;
- backup, migration, and compatibility tooling;
- active bounded M3–M7 server cognition over already-authorized recall/store events, including transient Working Memory, evidence-gated Self-Model persistence, and reversible event-driven Memory Lifecycle;
- canonical schema-V2 metadata normalization plus staged migration/validation tooling.

CyberBrain remains independent from any single AI client, model provider, routing product, or deployment topology.

Normal external agents are memory consumers/producers. Their stable responsibility is recall/get/store. CyberBrain owns post-storage cognition: normalization, validation, embedding, Knowledge Evolution, Episodic pending-state processing, automatic Dream scheduling/processing, promotion/review, and Knowledge writeback. Prediction Learning preserves causal order and may use a thin pre-action/outcome event bridge where a runtime genuinely exposes those events; it must not be reconstructed retrospectively.

### Current integration state

Wave 1 of the Level 8+ product/infrastructure track and the shared Wave 2 integration are complete on current `main`:

- authenticated MCP requests bind server-owned authority and trusted identity; `single_owner` remains default, while broader modes require an authenticated principal registry and complete runtime quotas;
- canonical `knowledge_get(id)` and `memory_get(id)` perform exact full fetch with storage-side scope eligibility and indistinguishable absent/out-of-scope not-found behavior;
- `cyberbrain.agent_adapter` has a real MCP Streamable HTTP client bridge over the canonical tool contract;
- M3 Salience and M4 Concept Formation are active after authorized prefetch/store observation under their bounded advisory/evidence contracts;
- M5 Working Memory is active as exact scope/session/task transient state with relevance → Salience → dedupe → token-budget selection, TTL/closeout, and bounded M4/M6 advisory context;
- M6 runs automatically on trusted Prediction→Outcome resolution and remains fail-closed until readiness passes;
- current single-owner production pools all shared-credential coding agents under trusted principal `coding-agents` for M6 evidence accumulation; this is intentionally simpler than per-agent P3 identity and does not enable broader multi-user authority;
- M7 records access and applies reversible lifecycle decisions event-by-event, with no automatic historical bulk sweep;
- the Level-8.0 source gate is satisfied and the production cognitive integration path is active.

The retrieval benchmark/fusion foundation remains observational rather than caller-visible. A 28-case reviewed benchmark against the current vector path rejected always-on global hybrid fusion: it improved Recall@5 but slightly reduced MRR and introduced rank regressions. A deterministic literal/fingerprint router that uses lexical retrieval only for literal-heavy queries while retaining vector retrieval elsewhere improved Recall@5 and MRR with no observed rank regressions in the reviewed set. Shadow observation is implemented and the reusable pre-tokenized BM25 corpus has cleared the earlier recurring scoring-cost blocker, but the observer remains **SHADOW ONLY**. Foreground Knowledge literal/hybrid modes are now implemented behind explicit configuration; vector remains the default until larger controlled relevance/reliability evidence is reviewed. The Agent Adapter remains optional foreground convenience rather than a cognitive lifecycle owner. Bound MCP requests enforce operation grants, storage-side scope filters for search/get/timeline, concrete write attribution, and identity-partitioned Knowledge Evolution. Source also implements a server-owned principal registry, durable Dream queue/audit/inbox scope, scoped Prediction/Calibration/Self-Model evidence, atomic persisted quotas, bounded MCP sessions/request bodies, and scoped numeric telemetry. `agent_ready`/`multi_user` are opt-in: authenticated principal configuration and every runtime quota limit are required; missing or incompatible configuration fails closed. Source acceptance, deployment acceptance, and longitudinal live evaluation are separate. See `docs/SOURCE_ACCEPTANCE.md`, `docs/TENANCY_OPERATIONS.md`, and `docs/LIVE_EVALUATION.md`. Public release packaging remains a separate explicit decision.

### Current engineering phase — Level-8 source accepted; readiness and product-boundary hardening

Shared integration is serialized rather than parallel. The security/order invariant is:

```text
authenticated caller
→ effective authority/scope
→ hard storage/read eligibility
→ scope-safe exact fetch / retrieval
→ optional foreground Agent Adapter context packing
→ server-owned post-storage cognition
```

The scope/auth, exact-fetch, real Agent Adapter client bridge, real retrieval benchmark, shadow literal-routing instrumentation, reusable BM25 shadow corpus, server-owned post-storage cognition contract/tests, M3 Salience, M4 Concept Formation, M5 Working Memory, P3.1 trusted-agent binding, E2 prospective-outcome census, complete source-level M6 Self-Model, complete source-level M7 Memory Lifecycle, schema-V2 metadata contracts, hardened V2 migration/validation tooling, and the current V2 migration runbook are implemented. The complete corpus has been staged, independently validated, canary-tested, and cut over to schema V2. The benchmark decision remains **do not promote global hybrid retrieval**. The literal shadow path remains observational. Caller-visible Knowledge retrieval defaults to vector and can select foreground literal/hybrid modes explicitly; Memory and Dream retrieval retain their existing contracts. The immediate program frontier is now evidence accumulation and tuning of the active integration: M6 remains fail-closed until prospective trusted evidence matures, while M7 is active only on touched/prefetched events rather than as a full-corpus sweep. P3 source isolation and resource controls are implemented; broader deployment activation remains an explicit configuration and rollout decision.

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

## Cognitive learning roadmap

CyberBrain may evolve from a memory system into a learning substrate for agents through
observable, testable cognitive mechanisms with explicit ownership and evidence dependencies.

This roadmap is not an attempt to reproduce human consciousness. It extracts useful mechanisms
from human cognition and turns them into explicit technical primitives that can be measured,
validated, and kept evidence-grounded.

### Development rule

Treat the cognitive roadmap as a dependency graph with explicit ownership, not as a rigid seven-step
feature checklist. By default, keep only one new mechanism in active implementation at a time, while
allowing specification or read-only/shadow observation of downstream mechanisms when dependencies
are explicit and current project guidance permits it.

A mechanism's source implementation is complete when it has:

- a written contract/specification;
- one clearly owned class of decisions that does not duplicate another mechanism;
- explicit data ownership and lifecycle;
- deterministic validation rules where possible;
- tests for correctness and failure modes;
- provenance/evidence boundaries;
- safe defaults and explicit configuration/rollout boundaries.

Post-deployment usefulness and continual-learning conclusions belong to `docs/LIVE_EVALUATION.md`, normally reviewed after 30 days and again after 60 days of real use. These observations are excluded from source completion; existing prospective evidence thresholds still control each runtime conclusion.

Dreaming V1 is a stable consolidation substrate rather than one of the numbered mechanisms. New
mechanisms should consume its evidence-grounded outputs instead of reimplementing Dream reasoning,
lesson induction, or promotion logic.

### Roadmap and mechanism ownership

The numbering preserves roadmap continuity; it does not imply that every dependency is strictly
linear.

1. Prediction Learning
   - Status: implemented; observation remains active.
   - Owns: explicit Prediction → observed Outcome → deterministic Prediction Error.
   - Produces learning evidence; it does not decide what is salient, what becomes a concept, or how
     the agent should describe itself.

2. Calibration
   - Status: initial read-only analysis implemented; observation remains active.
   - Owns: epistemic performance statistics over resolved predictions, including confidence bias
     and calibration error.
   - Calibration labels describe evidence samples only. They must not become persistent self-beliefs
     or strategy mutations.

3. Salience / Priority
   - Status: M3 complete and active after normal authorization/search eligibility; it reorders only
     the bounded authorized prefetch and never creates eligibility.
   - Owns: bounded, explainable priority signals over already-authorized memories/events/candidates.
   - Uses the canonical signals prediction error, unresolvedness, contradiction, novelty, recurrence,
     consequence, explicit user emphasis, and recency.
   - The reviewed policy makes material evidence stronger than novelty/recency and is validated
     against the fixed Salience benchmark; the generic scorer remains independently configurable.
   - `SalienceAdvisor` is the bounded integration seam consumed by Concept Formation and Working Memory; implemented M7 may consume an already-derived Salience score as one lifecycle signal. `SalienceShadowObserver` changes no caller-visible ordering.
   - Does not select or persist the active task context; that belongs to Working Memory.
   - Does not decide truth, authorization, promotion, forgetting, or Knowledge mutation.

4. Concept Formation / Abstraction
   - Status: M4 complete and active as bounded same-scope runtime discovery/registry; durable promotion remains governed separately because the reviewed
     historical acceptance sample lacks strong verification evidence.
   - Owns: deterministic recurring abstraction candidates, stable concept identity, supporting
     evidence IDs, counterexamples, evidence diversity, and shadow stability.
   - E1 classifies historical evidence as strict-shadow eligible, review-only, or excluded before
     Concept discovery. Legacy chunks, research evidence, mixed operational Knowledge, and migrated
     provenance are never silently treated as clean concept truth.
   - Default Knowledge-only discovery favors precision: broad recurrence plus entity diversity is
     required. Multi-session/mixed evidence may use a lower support threshold when diversity is real.
   - Salience may prioritize same-scope candidates but cannot define concept identity or truth.
   - The promotion gate returns only review/reject and has no automatic Knowledge writer. Any future
     durable concept must pass explicit review and existing Knowledge Evolution.
   - Dreaming remains responsible for evidence-grounded consolidation and durable lesson candidates;
     Concept Formation does not implement a second Dream/induction engine.
   - No graph database or third durable collection is introduced.

5. Working Memory / Active Context
   - Status: M5 complete and active on normal MCP/Agent Adapter recall after existing authorization.
     Transient context remains process-local and bounded.
   - Owns: an exact scope/session/task transient active set for goals, subgoals, assumptions,
     hypotheses, evidence, Concept/memory references, blockers, open questions, and recent decisions.
   - Selection is task relevance → Salience → duplicate suppression → Token Governor budget.
     Relevance and Salience remain separate signals and neither broadens authorization.
   - Hard defaults bound candidates, item count, per-item tokens, total tokens, and TTL.
   - `WorkingMemoryEmissionLedger` suppresses unchanged reinjection while changed revisions emit again.
   - Closeout/expiry removes transient state only; no automatic Episode or Knowledge persistence exists.
   - The controlled 4-task/16-step benchmark improves required-context coverage from 67.35% to 100%
     while reducing context tokens 1045→458, recall calls 16→4, and exact fetches 12→4; stale
     contamination and cross-task leakage are zero. This is source benchmark evidence, not an LLM
     quality or production-success claim.
   - No third collection, graph database, public Working Memory MCP tool, or retrieval reranking is
     introduced.

6. Agent Self-Model
   - Status: source implementation complete; real-corpus acceptance requires fresh trusted prospective evidence; validated schema V2 is already live.
   - Owns: trusted prospective evidence extraction, fail-closed readiness, deterministic agent-scoped capability/limitation/workflow/strategy hypotheses, explicit review, accepted-only Knowledge Evolution persistence, and bounded accepted-only Working Memory advisory projection.
   - The default readiness floor remains at least 20 trusted resolved prospective outcomes, 3 sessions, 3 topics, and a complete scan.
   - Calibration is one input discipline, not the Self-Model itself. Historical/pre-P3 identity is not retroactively trusted.
   - Self-model claims remain revisable hypotheses; they do not mutate prompts, tools, permissions, routing, model weights, or identity truth.

7. Memory Lifecycle
   - Status: source implementation complete; event-driven actuation is active; full-corpus evaluation requires fresh access/relevance evidence.
   - Owns: deterministic retention scoring, reversible `keep_active | suppress | remain_suppressed | reactivate`, ordinary-recall eligibility, access metadata, and lifecycle reason codes.
   - Suppression is metadata-only (`lifecycle_state=suppressed`, `ordinary_recall=false`) and does not physically delete canonical records or alter Knowledge truth/evolution status.
   - Salience/usage/recency/contradiction/storage pressure are bounded signals, not authorization or truth.
   - Reconsolidation/reasoning continues to reuse Dreaming and Knowledge Evolution rather than create a second consolidation engine.

### Dependency view

    Prediction Learning ──→ Calibration
            │
            └──────────────→ Dreaming

    Episodic Memory ───────→ Dreaming ───────→ durable lessons
                                  │
                                  ├───────────→ Salience / Priority
                                  └───────────→ Concept Formation / Abstraction

    Salience + task relevance ────────────────→ Working Memory / Active Context
    Calibration + repeated evidence ──────────→ Agent Self-Model
    Memory/Knowledge usage + contradiction ──→ Memory Lifecycle

These are data and authority dependencies, not permission to bypass current development gates.

### Observation checkpoint

Prediction Learning and Calibration remain in observation after release. The configured Calibration
minimum of 20 usable resolved Prediction/Outcome pairs is the first review checkpoint for whether the
sample is large enough to interpret aggregate calibration statistics. It is not an automatic feature
or activation gate.

Review should also consider evidence diversity and integrity:

- predictions should be recorded prospectively before meaningful outcomes are known;
- evidence should span multiple meaningful task/topic categories rather than one narrow test path;
- unresolved and duplicate Outcome behavior must remain explainable;
- causal ordering and inherited Prediction identity must remain intact;
- outcome diversity must emerge from real operation rather than manufactured failures.

The current owner-authorized runtime now exercises M3–M7. Evidence gates still control what each mechanism is allowed to conclude: M6 cannot persist until trusted readiness passes, M7 cannot hard-delete, and broader deployment requires the configured P3 principal and resource boundaries.

### Cognitive safety invariants

The roadmap must preserve these distinctions:

    observation != belief
    belief != knowledge
    confidence != truth
    salience != truth
    repetition != correctness
    self-model != identity truth

No cognitive mechanism may bypass the existing evidence, review, provenance, or Knowledge Evolution
gates.

The intended long-term direction is continuity of learning for agents without requiring CyberBrain
to modify the underlying model weights.

## Current documentation

Normative/current guidance:

- README.md
- specs/VERSIONING.md
- TOOL_GUIDE.md
- MCP_PROVIDER_STANDARD.md
- docs/CURRENT_RUNTIME.md
- docs/DREAMING_ROUTING.md
- docs/V2_MIGRATION_RUNBOOK.md
- specs/
  - including specs/PREDICTION_LEARNING.md, specs/METACOGNITION_CALIBRATION.md, specs/SALIENCE.md, specs/CONCEPT_FORMATION.md, specs/WORKING_MEMORY.md, specs/AGENT_SELF_MODEL.md, specs/MEMORY_LIFECYCLE.md, and specs/SECURITY.md for the current cognitive and authority boundaries.

Historical development and migration evidence lives under docs/history/ and is non-normative.

## Historical plan

The original V1 development plan is preserved at:

docs/history/DEVELOPMENT_PLAN_V1.md

## Typed relation traversal program

Slices 1–4 implement strict typed assertions, scoped entity Fingerprinting, endpoint/evidence admission, relation-aware Evolution, Qdrant indexed adjacency/reverse lookup and bounded BFS with typed path provenance. Source tests distinguish referential validity from reviewed semantic acceptance and validate scope/time/version/budget gates. Explicit caller/Dream integration, proposal/review workflows and controlled benchmark/rollout tooling are source-complete. Deployment and longitudinal observations have separate checkpoints. The full normative boundary is `specs/RELATION_TRAVERSAL.md`; ordinary search does not follow typed edges yet.
