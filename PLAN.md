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

CyberBrain may evolve from a memory system into a learning substrate for agents by adding
observable, testable cognitive mechanisms one at a time.

This roadmap is not an attempt to reproduce human consciousness. It extracts useful mechanisms
from human cognition and turns them into explicit technical primitives that can be measured,
validated, and kept evidence-grounded.

### Development rule

Implement exactly one cognitive mechanism at a time.

A mechanism is not considered complete until it has:

- a written contract/specification;
- explicit data ownership and lifecycle;
- deterministic validation rules where possible;
- tests for correctness and failure modes;
- provenance/evidence boundaries;
- an observation period before the next mechanism is promoted into active development.

Do not start implementation of the next mechanism merely because the previous one has code. The
previous mechanism should first produce enough operational evidence to justify the next layer.

### Ordered roadmap

1. Prediction / Outcome / Prediction Error
   - Status: implemented and released in v0.1.6; initial end-to-end gateway validation passed; observation remains active.
   - Record what an agent expected before an action or decision.
   - Record what actually happened.
   - Derive the mismatch without treating the prediction as truth.
   - Use prediction error as learning evidence.

2. Metacognition / Calibration
   - Status: initial read-only calibration analysis released in v0.1.6; initial end-to-end gateway validation passed; observation evidence must be reviewed before mechanism 3 begins.
   - Compare prior confidence with actual outcomes.
   - Detect recurring overconfidence, underconfidence, and reasoning failure patterns.
   - Learn about reasoning quality without granting self-assessment direct Knowledge write
     authority.

3. Salience / Attention
   - Status: planned; do not implement until calibration observation evidence is reviewed.
   - Prioritize experiences using signals such as novelty, prediction error, consequence,
     contradiction, repetition, user emphasis, and unresolved uncertainty.
   - Use salience to influence what is surfaced, retained, or scheduled for deeper Dreaming.
   - Do not equate salience with truth or importance in every context.

4. Concept Formation / Induction
   - Generalize repeated evidence-backed episodes into reusable patterns or concepts.
   - Preserve links to the source episodes and counterexamples.
   - Require promotion/evidence gates before generalized concepts become canonical Knowledge.

5. Working Memory / Active Context
   - Maintain bounded task-local state such as current goals, active hypotheses, assumptions,
     blockers, evidence, and open questions.
   - Keep this state transient and distinct from Episodic Memory and canonical Knowledge.
   - Consolidate only useful outcomes after the working context closes.

6. Agent Self-Model
   - Accumulate evidence about recurring strengths, weaknesses, strategies, calibration, and
     failure modes for a specific agent identity.
   - Treat self-model claims as hypotheses derived from repeated observations, not permanent truth.
   - Prevent one failure or one success from becoming a canonical self-belief.

7. Decay / Forgetting / Reconsolidation
   - Reduce retrieval priority for stale or low-utility memories without silently erasing
     provenance.
   - Strengthen repeatedly useful knowledge.
   - Reconsider knowledge when contradiction or supersession evidence appears.
   - Add this only after real data volume demonstrates the need.

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
