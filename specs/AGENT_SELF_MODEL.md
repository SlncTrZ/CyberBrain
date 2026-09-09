# CyberBrain Agent Self-Model Specification v2

> Status: M6 source implementation complete. Real-corpus quality evaluation and broader behavioral activation remain separately gated.

## Purpose

Agent Self-Model owns revisable, evidence-backed hypotheses about one trusted agent's recurring capabilities, limitations, workflow tendencies, and strategy constraints.

It does **not** own identity truth, caller authorization, tool policy, routing, prompt mutation, Knowledge truth, model-weight updates, or autonomous strategy mutation.

## Safety invariants

```text
self-model hypothesis != identity truth
calibration label != self-model belief
one success/failure != recurring capability/limitation
recorded agent string != trusted runtime identity
working-memory state != self-model evidence
correlation != causation
accepted hypothesis != permission to self-modify
```

Every M6 hypothesis must remain traceable to prospective outcome evidence and remain explicitly reviewable/revisable.

## Source architecture

Current source implements:

```text
trusted prospective Prediction/Outcome evidence
→ M6 evidence extraction
→ fail-closed readiness gate
→ deterministic hypothesis generation
→ explicit human/reviewer decision
→ accepted-only persistence through Knowledge Evolution
→ optional bounded Working Memory advisory projection
```

No new durable collection is introduced.

## Trusted identity and evidence boundary

Trusted runtime identity can be bound only after MCP Bearer/X-API-Key authentication succeeds and only from a server-configured `CYBERBRAIN_TRUSTED_AGENT_ID`. Caller-supplied identity headers or tool arguments do not create trusted identity.

Prediction Learning enforces that boundary:

- `prediction_record` forces the trusted `agent`, rejects a conflicting payload agent, and marks trusted prospective events `identity_trust=authenticated`;
- `prediction_observe`, `prediction_pending`, and `calibration_observe` force the trusted agent filter when the context is bound;
- `prediction_resolve` verifies that the referenced Prediction belongs to the trusted agent before writing the Outcome;
- Outcome records inherit Prediction identity context and `identity_trust` rather than accepting a new agent value.

Historical/pre-P3 agent strings may remain useful provenance, but they are `legacy_untrusted` and are never retroactively upgraded into trusted Self-Model evidence.

## Prospective evidence contract

`extract_self_model_evidence(...)` accepts canonical Prediction/Outcome pairs only when causal and identity integrity are preserved.

Eligible evidence requires:

```text
canonical Episode Prediction
+ matching canonical Outcome prediction_id
+ outcome_time >= prediction_time
+ unchanged session / agent / project / topic
+ unchanged expected_outcome / prediction_confidence
+ assessment in confirmed | partially_confirmed | contradicted
```

`indeterminate` outcomes do not establish capability/limitation support.

Each `SelfModelEvidenceSample` contains:

```text
prediction_id
outcome_id
agent_id
session_id
project
topic
assessment
prediction_confidence
prediction_error
identity_trust
strategy_tags[]
```

Only samples marked `identity_trust=authenticated` count toward trusted M6 readiness and generation.

`strategy_tags[]` are explicit labels recorded prospectively with the Prediction. M6 must not reconstruct workflow/strategy evidence retrospectively from outcome prose.

## M6.0 readiness gate

`SelfModelReadinessEvaluator` remains deterministic and fail-closed.

Default gate:

```text
trusted resolved prospective outcomes >= 20
distinct sessions                    >= 3
distinct topics                      >= 3
evidence scan                         complete
all counted outcomes                  trusted
```

A live request may additionally require exact current `TrustedIdentityEvidence` for the same agent. Offline/corpus evaluation may use persisted `identity_trust=authenticated` evidence without requiring an active request context.

Failure returns:

```text
insufficient_evidence
```

Passing returns:

```text
ready_read_only
```

The readiness gate authorizes hypothesis analysis only. It does not authorize persistence or behavior mutation by itself.

## M6.1 deterministic hypothesis generation

`SelfModelHypothesisEngine` generates bounded hypotheses only after readiness passes.

Canonical hypothesis kinds:

```text
capability
limitation
workflow_tendency
strategy_constraint
uncertain_capability
```

### Topic hypotheses

Topic-scoped recurrence is reviewed only after a minimum topic sample/session floor. The default source policy uses:

```text
minimum topic samples   5
minimum topic sessions  2
capability rate         0.80
limitation rate         0.40
```

A weighted success rate uses:

```text
confirmed            = 1.0
partially_confirmed  = 0.5
contradicted         = 0.0
```

High repeated success may produce a `capability` hypothesis. Repeated negative outcomes may produce a `limitation`. Mixed recurring outcomes become `uncertain_capability` rather than forcing a confident identity claim.

### Strategy/workflow hypotheses

Repeated prospective `strategy_tags` may produce:

```text
workflow_tendency
strategy_constraint
```

These are explicitly correlational. Their reason codes include `correlational_not_causal`; they must not claim that a strategy caused success/failure merely because it co-occurred.

### Stable identity

Hypothesis identity is deterministic from agent + hypothesis kind + scope, producing a stable `smh-*` ID. Repeated analysis of the same semantic scope can therefore evolve one logical Self-Model entity through Knowledge Evolution instead of creating uncontrolled duplicates.

## Hypothesis contract

`SelfModelHypothesis` contains:

```text
hypothesis_id
agent_id
kind
claim
support_evidence_ids[]
counterexample_evidence_ids[]
confidence
sample_count
evidence diversity
generated_at
scope_topic
reason_codes[]
review_status
reviewed_at
contract version
```

Rules:

- support and counterexample IDs are unique and non-overlapping;
- support evidence is mandatory;
- confidence is bounded to `[0,1]`;
- review state is `pending | accepted | rejected`;
- pending hypotheses cannot have `reviewed_at`;
- accepted/rejected hypotheses require a timezone-aware review time;
- no hypothesis becomes authoritative automatically from generation.

## M6.2 review and persistence

Persistent Self-Model writes are **accepted-only**.

`SelfModelPersistence` rejects pending/rejected hypotheses and stores accepted hypotheses through the existing `KnowledgeEvolutionService` using the canonical Knowledge collection.

Canonical storage shape:

```text
record_class        = self_model_hypothesis
domain              = cognition
topic               = agent_self_model
entity_type         = self_model_hypothesis
agent               = hypothesis.agent_id
identity_trust      = system_derived
verification        = derived
origin              = cognition
source              = m6_self_model
ordinary_recall     = false
retention_directive = keep
```

Hypothesis-specific structure remains under `extensions.self_model`, including support/counterexample IDs, diversity, review status/time, reason codes, and Self-Model contract version.

This reuse of Knowledge Evolution provides stable entity revision/supersession semantics without creating a third collection.

A persisted Self-Model hypothesis is **not ordinary Knowledge recall**. `record_class=self_model_hypothesis` plus `ordinary_recall=false` prevents it from silently appearing in normal factual Knowledge searches.

## M6.3 Working Memory advisory seam

An accepted hypothesis may be converted into a `WorkingMemoryCandidate(kind=hypothesis)` through `SelfModelWorkingMemoryAdapter`.

This seam is informational and bounded:

- pending/rejected hypotheses cannot enter Working Memory through this adapter;
- Working Memory still requires exact task identity, explicit task relevance, Salience ordering, dedupe, and token budgets;
- the adapter creates context text only; it does not mutate prompts globally, choose tools, change permissions, reroute models, or alter Knowledge truth;
- an accepted hypothesis can therefore advise a task without becoming autonomous behavioral authority.

## Controlled source benchmark

`benchmarks/self_model/benchmark.py` is a deterministic contract benchmark, not real-corpus quality evidence.

Current controlled fixture covers:

```text
capability
limitation
uncertain_capability
workflow_tendency
strategy_constraint
```

The current source fixture generates all 5 expected kind/scope outcomes with no unexpected hypothesis class/scope. This demonstrates implementation correctness against the declared fixture only; it must not be used to claim that the migrated production corpus supports accurate Self-Model conclusions.

## Current evaluation boundary

M6 **source implementation is complete**. The remaining M6 evaluation question is empirical:

```text
complete schema-V2 corpus
→ trusted identity normalization
→ prospective evidence census
→ real M6 readiness
→ real hypothesis precision/usefulness review
```

Until the V2 migration/validation and real-corpus review are complete, source completeness must not be confused with evidence that durable Self-Model hypotheses are useful in production.

## Non-goals

M6 does not add:

- a new Qdrant collection;
- a public caller-managed Self-Model MCP tool in the current tool contract;
- automatic strategy mutation;
- prompt mutation;
- tool/permission/routing changes;
- model-weight updates;
- cross-agent inference from one agent's evidence;
- historical prediction/confidence fabrication;
- identity truth from generated or accepted hypotheses.

## Relationship to P3

P3.1 trusted agent attribution is sufficient for source-level prospective evidence integrity. It is **not** sufficient to enable `agent_ready` or `multi_user` runtime modes.

Broader P3 read/write/background isolation and persisted identity requirements remain independent product-safety gates before multi-agent persistent authority can be activated.
