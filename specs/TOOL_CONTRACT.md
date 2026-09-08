# CyberBrain MCP Tool Contract v1

CyberBrain complies with the repository integration standard in `../MCP_PROVIDER_STANDARD.md`.

## Canonical provider tools

```text
help
knowledge_search
knowledge_get
knowledge_store
knowledge_timeline
memory_search
memory_get
memory_store
prediction_record
prediction_resolve
prediction_observe
prediction_pending
calibration_observe
dream_enqueue
dream_status
dream_reason_claim
dream_reason_submit
dream_reviews
dream_review_resolve
```

Gateway namespacing is an integration concern. A gateway may expose these as `cyberbrain.<tool>` or another configured provider namespace without changing the provider-local contract.

Compatibility aliases may also be exposed for legacy clients:

```text
tech_store
tech_find
ai_memory_read
conversation_save
conversation_recall
```

Aliases are adapters only and do not define a second persistence or business-logic path.

## Agent / cognition responsibility boundary

Normal external agents consume and produce memory through the canonical search/get/store operations. They are not responsible for orchestrating post-storage cognition.

CyberBrain owns normalization/validation, embedding, Knowledge Evolution, the Episodic pending lifecycle, automatic Dream scheduling/processing, evidence and provenance validation, promotion/review, and Knowledge writeback. Advanced/control operations may remain exposed in MCP without becoming mandatory steps in a normal agent workflow.

Prediction Learning is causally different: Prediction evidence must be captured before its outcome is known. Implementations must not synthesize prior predictions retrospectively. A client/runtime may supply a thin pre-action/outcome event bridge when it has a genuine causal event seam.

## `help`

Read-only, zero side effects. Returns current provider contract/version metadata, capabilities, authentication description, contract hash, and usage guide content. Provider software version derives from `cyberbrain/_version.py`; tool-contract and schema versions are independently governed by `VERSIONING.md`.

## `knowledge_search`

Inputs:

```text
query (required)
domain
topic
entity_type
entity_name
project
status
verification
origin
negative_knowledge
view = compact | full
limit
```

Default lifecycle scope is `status=active`. Default response view is `compact`.

Compact response projection occurs after retrieval/ranking:

- use stored `summary` as `recall_text` when present;
- otherwise use at most 1,200 characters of stored `content`;
- omit full `content` and `summary`;
- include `recall_text_source`, original `content_chars`, and `content_omitted=true`;
- preserve score and relevant metadata.

`view=full` returns the complete canonical normalized search row. Response projection must not change storage, embeddings, filtering, ranking, provenance, or evidence semantics.

## `knowledge_get`

Requires one canonical UUID `id`. Returns the full canonical Knowledge row for that exact ID without performing semantic search. The storage query must combine ID eligibility with the caller's effective authorization scope. Missing and out-of-scope IDs return the same not-found shape so exact fetch cannot be used as a cross-scope existence oracle.

## `knowledge_store`

Requires:

```text
content
domain
topic
entity_type
entity_name
```

Optional metadata follows `KNOWLEDGE_SCHEMA.md`.

Returns one explicit Knowledge Evolution outcome:

```text
insert_new
no_change
evolve
context_split
reject
```

## `knowledge_timeline`

Requires entity identity selectors sufficient to avoid accidental cross-entity history merges. Returns ordered immutable versions plus explicit status/evolution links.

## `memory_search`

Requires:

```text
query
```

Optional inputs:

```text
session_id
channel
role
agent
project
topic
event_time_from
event_time_to
dream_status
view = compact | full
limit
```

All advertised filters must actually be applied. Default response view is `compact` and follows the same projection contract as `knowledge_search`. `view=full` returns the complete canonical normalized Episode row.

## `memory_get`

Requires one canonical UUID `id`. Returns the full canonical Episode row for that exact ID without performing semantic search. Storage-side eligibility must enforce the caller's effective episodic scope before payload return. Missing and out-of-scope IDs return the same not-found shape.

## `memory_store`

Requires:

```text
content
session_id
event_time
```

Optional episodic metadata follows `MEMORY_SCHEMA.md`. New ordinary episodes default to `dream_status=pending`. The server-side Dream scheduler owns discovery of eligible quiet pending sessions and automatic queueing; a normal caller does not need to call `dream_enqueue` after `memory_store`.

## Prediction Learning

### `prediction_record`

Requires:

```text
expected_outcome
confidence
session_id
event_time
```

`confidence` is bounded to 0..1 and is the caller's prior confidence, not truth probability. The record is stored as canonical Episodic evidence before the outcome is known.

### `prediction_resolve`

Requires:

```text
prediction_id
observed_outcome
assessment
event_time
```

Allowed assessments are:

```text
confirmed
partially_confirmed
contradicted
indeterminate
```

Outcome identity context is inherited from the referenced Prediction. Prediction error is derived deterministically and remains learning evidence rather than Knowledge truth.

### `prediction_observe`

Read-only bounded aggregate observation over Prediction/Outcome evidence. May filter by session, agent, project, and topic. It must not mutate Episodic Memory or Knowledge.

### `prediction_pending`

Read-only bounded unresolved Prediction worklist for the same identity filters. `may_be_incomplete=true` means callers must not interpret the returned rows as the complete unresolved population.

See `PREDICTION_LEARNING.md`.

## Calibration

### `calibration_observe`

Read-only analysis over resolved Prediction Learning evidence. Below the configured minimum sample count, assessment must remain `insufficient_evidence`. Calibration labels describe only the selected sample and may not persist self-beliefs, mutate Knowledge/Memory, or change agent strategy.

See `METACOGNITION_CALIBRATION.md`.

## Dreaming

Canonical Dreaming operations:

```text
dream_enqueue
dream_status
dream_reason_claim
dream_reason_submit
dream_reviews
dream_review_resolve
```

### `dream_enqueue`

Explicitly queues a completed session for Dream processing. This is an advanced/manual override or control path; it is not required after ordinary `memory_store`. Pending Episodes are discovered and queued automatically by the server-side Dream scheduler after the configured quiet period. Optional focal topics may narrow intended consolidation scope.

### `dream_status`

Returns Dream queue/run status for a session. Read-only.

### `dream_reason_claim`

Leases the next pending bounded ReasoningTask to an external MCP consumer during the common run-level claim window. Claiming a task grants no Knowledge write authority.

### `dream_reason_submit`

Submits structured claims for the active lease. Task identity, claim token, confidence bounds, and evidence references must validate before acceptance. Fabricated or out-of-scope evidence IDs fail closed.

### `dream_reviews`

Lists unresolved evidence-gated candidates requiring review.

### `dream_review_resolve`

Records an approve/reject decision with reviewer provenance for one existing review candidate.

No Dreaming tool has direct Knowledge write authority. Reasoning results still pass evidence validation, promotion policy, optional review, and Knowledge Evolution before durable Knowledge can change.

Dream evidence selection remains causally bounded and focal-topic scoped. The completed session is primary evidence; historical semantic recall is supplementary. Long transcripts must be reduced to bounded local evidence rather than copied wholesale into reasoning prompts. Explicit project mismatches, future leakage, fabricated evidence, and focal-intent violations must fail closed or be rejected before promotion.

See `DREAMING_SPEC.md`, `REASONER_CONTRACT.md`, and `REASONER_MCP_PROVIDER.md`.

## Compatibility aliases

Legacy aliases may preserve historical response behavior when required for client compatibility. In particular, compatibility recall aliases may continue returning full payloads even though canonical `knowledge_search` and `memory_search` are compact-first.

Known legacy behavior bugs are not part of the canonical contract.

## Error semantics

Malformed inputs return structured validation errors. Provider/storage/embedding failures must remain distinguishable from a true successful no-match result. Authentication and authorization failures fail closed according to `SECURITY.md` and `../MCP_PROVIDER_STANDARD.md`.
