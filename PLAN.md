# CyberBrain — Current Plan

> Status: Current project guidance.
> Release baseline: v0.1.7.

## Operating mode

CyberBrain is in a use-and-observe phase. Dreaming V1 historical replay acceptance is complete in
v0.1.7. The project should prefer evidence-driven fixes and measured improvements over speculative
expansion.

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
   - Status: implemented and released in v0.1.6; observation remains active.
   - Owns: explicit Prediction → observed Outcome → deterministic Prediction Error.
   - Produces learning evidence; it does not decide what is salient, what becomes a concept, or how
     the agent should describe itself.

2. Calibration
   - Status: initial read-only analysis released in v0.1.6; observation remains active.
   - Owns: epistemic performance statistics over resolved predictions, including confidence bias
     and calibration error.
   - Calibration labels describe evidence samples only. They must not become persistent self-beliefs
     or strategy mutations.

3. Salience / Priority
   - Status: planned; not in active development.
   - Owns: bounded, explainable priority signals over memories/events/candidates.
   - May use novelty, prediction error, contradiction, repetition, consequence, user emphasis, and
     unresolvedness.
   - Does not select or persist the active task context; that belongs to Working Memory.
   - Does not decide truth, promotion, forgetting, or Knowledge mutation.

4. Concept Formation / Abstraction
   - Status: planned.
   - Owns: identifying recurring clusters, concept identities, and abstraction relationships across
     evidence-backed memories and durable lessons.
   - Dreaming remains responsible for evidence-grounded consolidation and durable lesson candidates;
     Concept Formation must not implement a second Dream/induction engine.
   - Concepts must retain links to supporting evidence, counterexamples, and provenance.

5. Working Memory / Active Context
   - Status: planned.
   - Owns: a bounded transient active set for the current task: goals, hypotheses, assumptions,
     blockers, evidence, and open questions.
   - May consume Salience/Priority and task relevance, but must not redefine salience itself.
   - Active context remains distinct from Episodic Memory and canonical Knowledge.

6. Agent Self-Model
   - Status: planned.
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
- TOOL_GUIDE.md
- MCP_PROVIDER_STANDARD.md
- docs/CURRENT_RUNTIME.md
- docs/DREAMING_ROUTING.md
- specs/
  - including specs/PREDICTION_LEARNING.md and specs/METACOGNITION_CALIBRATION.md for the current cognitive learning mechanisms.

Historical development and migration evidence lives under docs/history/ and is non-normative.

## Historical plan

The original V1 development plan is preserved at:

docs/history/DEVELOPMENT_PLAN_V1.md
