# Concept Formation / Abstraction Specification v1

## Purpose

Concept Formation (M4) identifies recurring, evidence-backed abstraction candidates from already-authorized CyberBrain evidence.

A concept candidate answers:

> Which bounded set of evidence appears to express one recurring topic-level abstraction worth later review or use?

Concept Formation does **not** decide truth, authorization, canonical Knowledge mutation, Dreaming outcomes, Working Memory membership, or Memory Lifecycle policy.

## Ownership boundary

M4 owns:

```text
candidate concept identity
supporting evidence IDs
counterexample IDs
evidence diversity / recurrence indicators
candidate stability
formation confidence
review / reject eligibility for future durable promotion
```

M4 does not own:

```text
truth
retrieval eligibility
caller authorization
free-form synthesis
session consolidation
Knowledge Evolution
Dreaming
Salience semantics
task relevance
```

The required ordering is:

```text
authentication / trusted authority
→ hard evidence eligibility
→ E1 evidence-quality classification
→ Concept candidate discovery
→ optional same-scope Salience prioritization
→ shadow stability / human review
→ only then, if separately approved, existing Knowledge Evolution
```

## E1 evidence-quality gate

Historical evidence is not assumed clean enough for automatic concept discovery.

The read-only census classifies records as:

```text
eligible_shadow
review_only
excluded
```

Current rules:

- inactive Knowledge is excluded;
- `legacy_chunk` / `legacy_source_chunk` evidence is excluded;
- generic or missing topics are excluded;
- research-domain / research-verified / web-research evidence is review-only;
- mixed operational/event-heavy Knowledge is review-only;
- migrated canonical provenance is review-only unless a reviewed benchmark explicitly opts it in;
- native, active, non-generic, non-research, non-mixed evidence may enter strict shadow discovery.

E1 never reconstructs historical Prediction/Outcome pairs from prose. A Prediction is causal evidence only when it genuinely existed before its Outcome.

## Concept evidence

`ConceptEvidence` is metadata-only and contains a reference to already-visible evidence:

```text
evidence_id
record_type              knowledge | episode
scope_marker
domain
topic
project
entity_type
entity_name
session_id
source
verification
counterexample
```

M4 receives evidence after upstream authorization. It does not fetch around authorization or infer a broader scope.

Evidence IDs in one discovery run must be unique.

## Candidate identity

M4 V1 uses deterministic candidate identity over:

```text
candidate_version + scope_marker + normalized domain + normalized topic
```

The ID is content-free and stable for the same concept key.

A candidate retains:

```text
candidate_concept_id
scope_marker
domain
topic
label
summary_candidate
project
supporting_evidence_ids
counterexample_ids
distinct_session_count
distinct_source_count
distinct_entity_count
record_types
strong_verification_count
formation_confidence
reason_codes
support_fingerprint
candidate_version
```

`summary_candidate` is intentionally `None` in M4 V1 discovery. M4.1/M4.2 do not introduce an LLM abstraction/summarization path.

## Recurrence and abstraction breadth

Repeated records are not automatically a concept. In particular, several versions or operational snapshots of the same entity may only represent evolution/history.

Default policy therefore requires:

### Knowledge-only clusters

```text
minimum support count = 5
minimum distinct entities = 2
```

This intentionally favors precision over recall for the first durable cognitive abstraction mechanism.

### Episode or mixed Knowledge/Episode clusters

```text
minimum support count = 3
minimum distinct sessions when Episodes are present = 2
```

A cluster must also demonstrate abstraction breadth through at least one of:

```text
distinct entity breadth
multi-session evidence
mixed Knowledge/Episode record types
```

Generic topics such as `chat_history` and `legacy_source_chunk` never form candidates.

## Counterexamples

Counterexamples are retained explicitly and never counted as positive support.

```text
supporting_evidence_ids ∩ counterexample_ids = ∅
```

An unresolved counterexample blocks the default promotion gate.

Counterexample presence is evidence against premature generalization, not a request to erase the candidate.

## Formation confidence

`formation_confidence` measures bounded cluster/evidence support quality only. It is **not truth confidence**.

The current deterministic score combines bounded contributions from:

```text
support count
distinct sessions
distinct sources
distinct entities
record-type diversity
```

The score does not use an LLM, wall clock, network call, model state, or hidden randomness.

## Salience relationship

Salience may prioritize already-discovered candidates inside one authorization scope through `SalienceAdvisor`.

Salience must not:

- create a Concept candidate;
- alter Concept identity;
- add/remove supporting evidence;
- redefine formation confidence;
- compare candidates across scope markers;
- turn a candidate into truth.

Concept discovery remains deterministic regardless of Salience ordering.

## Shadow registry

`ConceptShadowRegistry` is in-memory observation state only.

Across repeated runs it reports:

```text
added
removed
stable
changed-support
candidate IDs
```

Candidate support stability is compared through a deterministic support fingerprint. The registry adds no durable collection and writes no canonical data.

## Promotion gate

`ConceptPromotionGate` never auto-promotes a discovered candidate.

A candidate is rejected by default when it lacks any configured maturity condition, including:

```text
minimum support
minimum formation confidence
minimum strong verification evidence
resolved counterexamples
```

A candidate satisfying the gate receives only:

```text
review
```

not `promote`.

Human/reviewer approval and an explicit canonical write integration are required before any durable concept is passed to existing Knowledge Evolution. M4 must never bypass Knowledge Evolution with a direct repository write.

Current source does not add an automatic Concept Knowledge writer because the reviewed historical sample does not contain strong enough verification evidence to justify durable promotion.

## Real-evidence acceptance

The reviewed current-project read-only Knowledge snapshot contains 344 records.

E1 census found:

```text
active Knowledge                328
native strict shadow eligible     6
review-only                     322
excluded                         16
research-domain/evidence          90
migrated provenance              330
mixed operational Knowledge      179
historical Prediction backfill     0
```

Strict mode formed no candidates from the six native-clean records, which is a valid safe-empty result.

Before the default M4 policy was tightened, reviewed historical metadata grouping produced:

```text
9 candidates
precision                       25%
false-abstraction rate          75%
stability                      100%
duplicate candidate rate         0%
```

The review labels were frozen before policy refinement.

The default high-precision recurrence rule then produced:

```text
2 candidates
reviewed useful concepts       2 / 2
precision                      100%
useful-concept recall          100%
false-abstraction rate           0%
stability                      100%
duplicate candidate rate         0%
```

Both candidates were rejected for durable promotion because the migrated evidence had zero strong verification support. This is the intended fail-closed result.

This benchmark is current-project source acceptance evidence. It is not a claim that the policy is universally optimal or that migrated evidence has become canonical concept truth.

## Storage model

M4 creates no third Qdrant collection and no graph database.

Candidate discovery and shadow stability are transient/read-only. If a concept later becomes durable, it must use the existing canonical Knowledge collection and Knowledge Evolution semantics with supporting evidence/provenance retained.

## Non-goals

M4 V1 does not add:

- a graph database;
- a concept collection;
- an MCP Concept tool;
- an LLM concept classifier;
- free-form abstraction generation;
- automatic historical backfill;
- automatic durable promotion;
- cross-scope clustering;
- direct repository writes;
- caller-visible retrieval reranking.

## Completion boundary

M4 source-level development is complete when:

- E1 evidence quality is explicit and reproducible;
- deterministic candidate identity/discovery is implemented;
- same-entity repetition is not sufficient by itself;
- supporting IDs and counterexamples remain traceable;
- reviewed real-evidence precision/recall is acceptable under a frozen review set;
- shadow candidate identity/support is stable;
- duplicate candidate rate is bounded to zero in the accepted sample;
- Salience integration changes priority only;
- promotion fails closed and cannot write Knowledge automatically;
- no graph DB or new durable collection is introduced;
- full regression, lint, and integrity gates pass.
