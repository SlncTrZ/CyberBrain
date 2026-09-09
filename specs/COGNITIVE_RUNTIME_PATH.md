# Active Cognitive Runtime Path Specification v1

> Status: M3–M7 active integration contract for normal authenticated MCP recall/store operation.

## Purpose

CyberBrain owns one bounded server-side cognitive execution path over records that have **already passed** normal authorization, storage eligibility, and canonical search filtering.

The active recall order is:

```text
authorization + ordinary-recall eligibility
→ canonical vector prefetch
→ M3 Salience assessment
→ M4 bounded Concept discovery/stability observation
→ M5 bounded Working Memory selection
→ M7 event-driven access/lifecycle evaluation
→ bounded caller-visible recall rows
```

M6 is an outcome-triggered side path:

```text
trusted prospective Prediction → Outcome
→ M6 evidence extraction/readiness
→ deterministic hypotheses
→ configured accepted-only review policy
→ Knowledge Evolution outside ordinary recall
→ bounded M5 advisory on later recalls
```

No M3–M7 step may widen authorization, create a cross-tenant/cross-user/cross-agent read, or make an otherwise ineligible record visible.

## M3 — active Salience

For each already-visible prefetched recall candidate, the coordinator derives bounded signals only from canonical metadata already present on the row:

- prospective prediction error where available;
- unresolved/pending state;
- contradiction/outcome assessment;
- same-prefetch topic recurrence;
- importance/consequence/user emphasis;
- deterministic timestamp recency.

Unknown signals remain `None`; they are not guessed by an LLM.

The reviewed `SalienceAdvisor` scores same-scope candidates. The active path may use Salience to break/adjust ordering among already-authorized candidates. Salience still does not create retrieval eligibility or truth.

## M4 — active Concept discovery

Every normal recall/store event may contribute metadata-only Concept evidence to a bounded in-memory same-scope evidence window.

The coordinator runs deterministic `ConceptDiscoveryEngine` + `ConceptShadowRegistry` over this bounded evidence window. Concept candidates may enter M5 as references when task-relevant.

Active M4 does **not**:

- auto-create a third collection;
- auto-write canonical Concept Knowledge merely because a candidate exists;
- promote a candidate to truth;
- use an LLM abstraction pass.

The existing Concept promotion/evidence contract remains authoritative.

## M5 — active Working Memory

Normal recall calls now instantiate exact transient Working Memory identity from:

```text
scope marker + context session + task ID
```

Clients may provide `context_session_id` and `task_id`. The official Agent Adapter supplies them automatically. Older callers remain compatible: the server derives deterministic transient fallback identifiers without changing data filters.

The active path prefetches a bounded multiple of the requested recall count, then applies:

```text
task relevance
→ M3 Salience
→ dedupe
→ token/item budget
```

Two bounded M5 slots are reserved for M4 Concept and M6 accepted Self-Model advisory context so large raw candidate sets cannot starve downstream cognition entirely. M5 remains process-memory only and does not become a caller-managed durable scratchpad.

## M6 — active Self-Model trigger

`prediction_resolve` triggers an M6 evaluation for the currently authenticated trusted agent.

M6 still requires the canonical readiness gate:

- trusted runtime agent identity;
- all usable Prediction/Outcome pairs trusted;
- at least 20 trusted resolved outcomes;
- at least 3 distinct sessions;
- at least 3 distinct topics;
- complete bounded evidence scan.

Topic hypotheses additionally require their existing sample/session breadth. Strategy hypotheses require at least 5 supporting samples across at least 2 distinct sessions.

If readiness fails, the active result remains `insufficient_evidence`; no threshold is lowered and no historical confidence is fabricated.

When readiness passes, deterministic hypotheses are generated. Under the current owner-authorized runtime policy, generated hypotheses are automatically marked accepted through the existing review transition and persisted through Knowledge Evolution. Persisted Self-Model records remain:

```text
record_class=self_model_hypothesis
ordinary_recall=false
identity_trust=system_derived
```

The runtime keeps stable logical hypothesis identity. If the claim text remains stable while support IDs, sample count, diversity, confidence, or reason metadata changes, Knowledge Evolution performs a metadata-bearing revision instead of incorrectly returning `NO_CHANGE`.

Accepted active hypotheses may enter later M5 snapshots as bounded advisory context. They never become factual ordinary Knowledge merely by being active.

## M7 — active event-driven Lifecycle

M7 actuation is active on records touched by normal recall/exact-fetch flow. There is deliberately **no automatic full-corpus suppression sweep**.

On selected recall candidates, the coordinator records access and treats current task relevance as explicit relevance. This protects useful touched records and may reactivate suppressed normal records.

On authorized prefetched candidates that are not selected into the active context, M7 may evaluate and apply reversible soft suppression based on the existing lifecycle policy plus M3/M4 signals available for that event.

M7 only applies metadata transitions:

```text
lifecycle_state
ordinary_recall
retention_score
lifecycle_updated_at
lifecycle_reason_codes
access_count
last_accessed_at
```

It does not hard-delete canonical memory and does not change Knowledge truth/evolution status.

Exact fetch may reactivate an explicitly requested normal Knowledge/Episodic record. Knowledge classes such as `self_model_hypothesis` or `migration_quarantine` are excluded from this normal-record reactivation seam, so M7 cannot accidentally make them ordinary recall.

## Compatibility

Canonical MCP tool names remain unchanged. `knowledge_search` additionally accepts optional `context_session_id` and `task_id`; `memory_search` additionally accepts optional `context_session_id` and `task_id`. These fields identify transient M5 context only and do not widen or replace canonical data filters.

Legacy aliases remain mapped to the same canonical services and pass through the same cognitive coordinator where they perform recall/store operations.

Returned recall rows may include additive `_cognition` metadata describing active M3/M4/M5/M6/M7 decisions. Clients must not treat this metadata as canonical record content or truth.

## Runtime switches

The active path is controlled by explicit settings:

```text
CYBERBRAIN_COGNITION_M3_M7_ENABLED
CYBERBRAIN_COGNITION_M6_AUTO_ACCEPT_ENABLED
CYBERBRAIN_COGNITION_M7_ACTUATION_ENABLED
CYBERBRAIN_COGNITION_PREFETCH_MULTIPLIER
CYBERBRAIN_COGNITION_CONCEPT_EVIDENCE_LIMIT
```

Current defaults enable M3–M7, M6 accepted-only automatic review after readiness, and event-driven M7 actuation. Operators may disable individual behavioral layers without changing schema or rolling back the V2 corpus.

## Safety invariants

```text
hard authorization precedes cognition
M3 score != authorization
M4 candidate != truth
M5 selection != durable memory
M6 hypothesis != identity truth
M7 suppression != deletion
explicit V2 non-recallable classes stay non-recallable
no bulk M7 historical sweep
no retrospective Prediction fabrication
no threshold lowering to force M6 readiness
```
