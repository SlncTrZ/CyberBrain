# Memory Lifecycle Specification v1

> Status: M7 source implementation complete. Real-corpus shadow evaluation and any production activation remain separate gates.

## Purpose

Memory Lifecycle owns reversible retrieval availability over time. It answers:

> Should an already-stored record remain in ordinary recall, be softly suppressed, remain suppressed, or be reactivated?

M7 does **not** own truth revision, Knowledge Evolution, Dream consolidation, caller authorization, or physical deletion as its normal forgetting mechanism.

## Core invariants

```text
lifecycle state != Knowledge truth status
retention score != truth confidence
suppression != deletion
reactivation != truth promotion
usage frequency != correctness
Salience != lifecycle policy
```

All lifecycle decisions are downstream of authorization and canonical storage.

## Canonical metadata

Knowledge and Episodic schema V2 include:

```text
lifecycle_state       active | suppressed
ordinary_recall       true | false
retention_score       0..1
retention_directive   default | keep
access_count          non-negative integer
last_accessed_at      timezone-aware timestamp | null
lifecycle_updated_at  timezone-aware timestamp | null
lifecycle_reason_codes[]
```

These fields are metadata only. M7 must not rewrite canonical record content merely to age/suppress/reactivate a record.

## Decision classes

`LifecycleDecisionKind` is:

```text
keep_active
suppress
remain_suppressed
reactivate
```

### keep_active

Record remains `lifecycle_state=active` and `ordinary_recall=true`.

### suppress

Record transitions to:

```text
lifecycle_state = suppressed
ordinary_recall = false
```

Canonical content, vector, point ID, evidence, provenance, and Knowledge status remain preserved.

### remain_suppressed

Record remains excluded from ordinary recall without repeated destructive changes.

### reactivate

Record transitions back to:

```text
lifecycle_state = active
ordinary_recall = true
```

Reactivation is a retrieval-availability change only. It does not make a deprecated/rejected/superseded Knowledge record active truth.

## Input signals

`LifecycleSignals` contains:

```text
record_id
lifecycle_state
retention_directive
age_days
access_count
days_since_last_access
salience_score
superseded_or_contradicted
concept_linked
unresolved
storage_pressure
explicit_relevance
```

Rules:

- time/score values must be finite;
- `age_days` and `days_since_last_access` must be non-negative;
- `salience_score` and `storage_pressure` are bounded to `[0,1]`;
- unresolved/relevance/contradiction/concept signals must be explicitly derived by upstream logic;
- missing evidence must not be fabricated to force a lifecycle decision.

## Default policy

`LifecyclePolicy` defaults:

```text
suppression threshold   0.35
reactivation threshold  0.65
recent window           30 days
stale window            180 days
frequent access count   8
```

The higher reactivation threshold creates hysteresis so records do not oscillate between active/suppressed due to small score changes.

`retention_directive=keep` overrides normal decay pressure and preserves/reactivates the record.

## Retention scoring

The current evaluator is deterministic and combines bounded signals for:

- recency;
- time since last access;
- access frequency;
- Salience;
- Concept linkage;
- unresolved state;
- superseded/contradicted state;
- storage pressure.

Reason codes explain why a score/decision was produced. Current codes include:

```text
explicit_keep
recent
frequently_accessed
high_salience
concept_linked
unresolved
explicit_relevance
stale
never_accessed
superseded_or_contradicted
storage_pressure
below_suppression_threshold
above_reactivation_threshold
```

A record protected by explicit relevance or unresolved state remains active even when other decay signals are weak.

## Salience relationship

M7 may consume an already-authorized Salience score as one signal.

Required ordering:

```text
authentication / authority
→ hard record eligibility
→ upstream signal derivation
→ Salience where available
→ M7 lifecycle evaluation
→ metadata-only lifecycle decision
```

Salience cannot itself suppress/delete a record and cannot broaden caller visibility.

M7 owns the lifecycle decision semantics.

## Knowledge-status relationship

For Knowledge records, lifecycle metadata is deliberately independent from:

```text
active
superseded
deprecated
rejected
```

Knowledge status remains controlled by Knowledge Evolution/review. M7 may use superseded/deprecated/rejected state as a negative retention signal, but it cannot change the truth/evolution status merely because the record is old or rarely accessed.

## Dreaming and reconsolidation relationship

M7 does not implement a second consolidation/reasoning engine.

If a stale/conflicting record requires semantic reconsideration or truth revision:

```text
M7 signal
→ existing Dreaming / evidence review / Knowledge Evolution path
```

M7 itself only changes ordinary recall availability and lifecycle metadata.

## M7.1 shadow evaluation

`MemoryLifecycleService.shadow(...)` evaluates a batch of records without persistence.

It reports counts of:

```text
scanned
keep_active
suppress
remain_suppressed
reactivate
```

plus deterministic decisions/reason codes.

Shadow evaluation is the required real-corpus evaluation mode before lifecycle actuation is promoted.

## M7.2 reversible soft suppression

`apply_decision(...)` writes only lifecycle metadata with `PointRepository.set_payload`.

No hard delete is performed.

Suppression writes:

```text
lifecycle_state = suppressed
ordinary_recall = false
retention_score
lifecycle_updated_at
lifecycle_reason_codes
updated_at
```

Normal Knowledge/Episodic search is schema-V2 aware and requires ordinary-recall eligibility, so suppressed records disappear from ordinary recall without disappearing from storage/history.

## M7.3 reactivation and access tracking

Explicit relevance, unresolvedness, strong Salience, sufficient retention score, or `retention_directive=keep` may reactivate a suppressed record.

`record_access(...)` increments:

```text
access_count
last_accessed_at
updated_at
```

This supports measured use-based retention without modifying content/provenance.

## Migration baseline

Schema-V2 migration initializes lifecycle metadata conservatively:

- normal canonical Knowledge/Episodes default active/ordinary-recall with retention score `1.0`;
- Self-Model hypotheses are not ordinary recall;
- migration quarantine is suppressed and non-recallable;
- lifecycle migration metadata records source/provenance without treating migration time as evidence that the record is semantically recent.

M7 real-corpus evaluation should occur **after** the full V2 union migration/validation so the evaluator sees one normalized lifecycle contract instead of mixed legacy payloads.

## Controlled source benchmark

`benchmarks/lifecycle/benchmark.py` is a deterministic contract benchmark, not real-corpus acceptance evidence.

Current fixture covers:

```text
fresh high-value keep
stale contradicted suppression
explicit keep protection
explicit relevance reactivation
remain suppressed
unresolved protection
```

The current controlled fixture matches all 6 expected decisions with zero false suppression and zero false reactivation. This demonstrates source-policy correctness against the fixture only.

## Real-corpus acceptance

Production/caller-visible lifecycle activation requires post-migration evidence at minimum for:

```text
false-suppression rate
useful-reactivation rate
recall-quality impact
storage/latency impact
reason-code distribution
suppressed-record recoverability
cross-scope safety
```

A source-complete M7 engine is not proof that a particular retention threshold is optimal for the real corpus.

## Non-goals

M7 does not add:

- a third canonical collection;
- hard deletion as default forgetting;
- a new truth/confidence system;
- caller-visible reranking authority;
- automatic Knowledge status mutation;
- independent semantic reconsolidation;
- an LLM lifecycle classifier;
- cross-scope visibility;
- autonomous strategy or identity mutation.
