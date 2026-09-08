# CyberBrain — Current Plan

> Status: Current project guidance.
> Software/package version authority: `cyberbrain/_version.py`; release tags derive from it.
> Deployment state is managed separately from source guidance; verify the actual runtime before making deployment claims.

## Operating mode

CyberBrain is in a use-and-observe phase. Dreaming V1 historical replay acceptance is complete. The project should prefer evidence-driven fixes and measured improvements over speculative expansion.

## Current product boundary

CyberBrain provides:

- canonical Knowledge storage, retrieval, and evolution;
- canonical Episodic Memory storage and retrieval;
- evidence-grounded Dreaming with review/promotion gates;
- authenticated MCP/API access;
- provider-neutral Dream fallback routing;
- backup, migration, and compatibility tooling.

CyberBrain remains independent from any single AI client, model provider, routing product, or deployment topology.

Normal external agents are memory consumers/producers. Their stable responsibility is recall/get/store. CyberBrain owns post-storage cognition: normalization, validation, embedding, Knowledge Evolution, Episodic pending-state processing, automatic Dream scheduling/processing, promotion/review, and Knowledge writeback. Prediction Learning preserves causal order and may use a thin pre-action/outcome event bridge where a runtime genuinely exposes those events; it must not be reconstructed retrospectively.

### Current integration state

Wave 1 of the Level 8+ product/infrastructure track and the shared Wave 2 integration are complete on current `main`:

- authenticated MCP source requests bind to explicit `CallerAuthority` in `single_owner` mode; future identity-bearing modes remain fail-closed until a trusted identity source exists;
- canonical `knowledge_get(id)` and `memory_get(id)` perform exact full fetch with storage-side scope eligibility and indistinguishable absent/out-of-scope not-found behavior;
- `cyberbrain.agent_adapter` has a real MCP Streamable HTTP client bridge over the canonical tool contract.

The retrieval benchmark/fusion foundation remains observational rather than caller-visible. A 28-case reviewed benchmark against the current vector path rejected always-on global hybrid fusion: it improved Recall@5 but slightly reduced MRR and introduced rank regressions. A deterministic literal/fingerprint router that uses lexical retrieval only for literal-heavy queries while retaining vector retrieval elsewhere improved Recall@5 and MRR with no observed rank regressions in the reviewed set. Shadow observation is implemented and the reusable pre-tokenized BM25 corpus has cleared the earlier recurring scoring-cost blocker, but lexical output remains **SHADOW ONLY** until larger live relevance/reliability evidence is reviewed. The Agent Adapter remains optional foreground convenience rather than a cognitive lifecycle owner. Broader tenancy enforcement across existing search/write paths is still pending. Public release packaging remains a separate explicit decision.

### Current engineering phase — observation and product-boundary hardening

Shared integration is serialized rather than parallel. The security/order invariant is:

```text
authenticated caller
→ effective authority/scope
→ hard storage/read eligibility
→ scope-safe exact fetch / retrieval
→ optional foreground Agent Adapter context packing
→ server-owned post-storage cognition
```

The scope/auth, exact-fetch, real Agent Adapter client bridge, real retrieval benchmark, shadow literal-routing instrumentation, reusable BM25 shadow corpus, server-owned post-storage cognition contract/tests, and single software/package version authority are implemented on source `main`. The benchmark decision remains **do not promote global hybrid retrieval**. The shadow path is disabled by default in source and, when enabled by a deployment, evaluates only literal/fingerprint-heavy Knowledge queries in a non-blocking worker; the vector result remains caller-visible and unchanged. Its cache is bounded/TTL-controlled, explicit metadata filters are reapplied before BM25, and failures are fail-open to the canonical search path. The next retrieval gate is larger organic relevance/reliability evidence, not another performance fix. There is no remaining goal to make Agent Adapter orchestrate Dreaming or other background cognition.

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

A mechanism is not considered complete until it has:

- a written contract/specification;
- one clearly owned class of decisions that does not duplicate another mechanism;
- explicit data ownership and lifecycle;
- deterministic validation rules where possible;
- tests for correctness and failure modes;
- provenance/evidence boundaries;
- an observation period before persistent or behavioral authority expands.

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
   - Status: source-level M3 complete; runtime search integration remains intentionally inactive until
     broader authorization/search-path prerequisites are complete.
   - Owns: bounded, explainable priority signals over already-authorized memories/events/candidates.
   - Uses the canonical signals prediction error, unresolvedness, contradiction, novelty, recurrence,
     consequence, explicit user emphasis, and recency.
   - The reviewed policy makes material evidence stronger than novelty/recency and is validated
     against the fixed Salience benchmark; the generic scorer remains independently configurable.
   - `SalienceAdvisor` is the bounded integration seam for future Concept Formation, Working Memory,
     and Lifecycle work; `SalienceShadowObserver` changes no caller-visible ordering.
   - Does not select or persist the active task context; that belongs to Working Memory.
   - Does not decide truth, authorization, promotion, forgetting, or Knowledge mutation.

4. Concept Formation / Abstraction
   - Status: source-level M4 complete; durable promotion remains fail-closed because the reviewed
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
   - Status: source-level M5 complete; production/runtime activation remains intentionally inactive
     until shared read-path authorization and an explicit integration gate are complete.
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
   - Status: next cognitive mechanism after M5 source acceptance.
   - Owns: evidence-backed, agent-scoped hypotheses about recurring capabilities, limitations,
     operating tendencies, and strategy constraints.
   - Calibration is one input, not the Self-Model itself.
   - Self-model claims remain revisable hypotheses and never become identity truth from one success
     or failure.

7. Memory Lifecycle
   - Status: planned; add only when real data volume demonstrates the need.
   - Owns: retention strength/decay, retrieval suppression or forgetting policy, and lifecycle
     triggers for reconsideration.
   - Provenance must not be silently erased.
   - Reconsolidation should reuse Dreaming and Knowledge Evolution where reasoning or supersession is
     required rather than create a second consolidation engine.

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

Reaching the checkpoint triggers review of evidence quality and mechanism behavior only. It does not
automatically start or activate any downstream mechanism.

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
- specs/
  - including specs/PREDICTION_LEARNING.md, specs/METACOGNITION_CALIBRATION.md, specs/SALIENCE.md, and specs/CONCEPT_FORMATION.md for the current cognitive mechanisms.

Historical development and migration evidence lives under docs/history/ and is non-normative.

## Historical plan

The original V1 development plan is preserved at:

docs/history/DEVELOPMENT_PLAN_V1.md
