# CyberBrain MCP Tool Contract v1

CyberBrain complies with the repository integration standard in `../MCP_PROVIDER_STANDARD.md`.

## Required tools

```text
help
knowledge_search
knowledge_store
knowledge_timeline
memory_search
memory_store
prediction_record
prediction_resolve
prediction_observe
prediction_pending
calibration_observe
dream_enqueue
dream_status
dream_reviews
dream_review_resolve
```

Gateway canonical namespace:

```text
cyberbrain.help
cyberbrain.knowledge_search
cyberbrain.knowledge_store
cyberbrain.knowledge_timeline
cyberbrain.memory_search
cyberbrain.memory_store
cyberbrain.prediction_record
cyberbrain.prediction_resolve
cyberbrain.prediction_observe
cyberbrain.prediction_pending
cyberbrain.calibration_observe
cyberbrain.dream_enqueue
cyberbrain.dream_status
cyberbrain.dream_reviews
cyberbrain.dream_review_resolve
```

## `help`

Read-only, zero side effects.

Returns current runtime provider contract metadata plus guide content.

## `knowledge_search`

Inputs should support:

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
limit
```

Default lifecycle scope is `status=active`.

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

Returns an explicit evolution outcome:

```text
insert_new
no_change
evolve
context_split
reject
```

## `knowledge_timeline`

Requires entity identity selectors sufficient to avoid accidental cross-entity history merges.

Returns ordered immutable versions plus explicit evolution links/status.

## `memory_search`

Requires:

```text
query
```

Optional filters:

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
limit
```

All advertised filters must actually be applied.

## `memory_store`

Requires:

```text
content
session_id
event_time
```

Optional episodic metadata follows `MEMORY_SCHEMA.md`.

New ordinary episodes default to `dream_status=pending`.

## Prediction learning tools

`prediction_record` requires:

```text
expected_outcome
confidence
session_id
event_time
```

`confidence` is bounded to 0..1 and describes the caller's prior confidence, not truth probability.

`prediction_resolve` requires:

```text
prediction_id
observed_outcome
assessment
event_time
```

Allowed assessment values are `confirmed`, `partially_confirmed`, `contradicted`, and `indeterminate`.

Both write operations store canonical Episodic records. Outcome metadata inherits the referenced Prediction's session/agent/project/topic identity. Prediction error is derived deterministically and remains learning evidence rather than Knowledge truth.

`prediction_observe` is read-only. It may filter by session, agent, project, and topic and returns bounded aggregate observation evidence without mutating Episodic Memory or Knowledge.

`prediction_pending` is read-only. It returns bounded unresolved Prediction records for the same filters so agents can later resolve them. When `may_be_incomplete=true`, callers must not interpret the returned items as the complete unresolved population.

`calibration_observe` is read-only and consumes resolved Prediction Learning evidence. It must return `insufficient_evidence` below its configured minimum sample count and may not persist calibration labels or mutate Knowledge/Memory.

See `PREDICTION_LEARNING.md` and `METACOGNITION_CALIBRATION.md`.

## Dreaming tools

Canonical V1 Dreaming operations are:

```text
dream_enqueue
dream_status
dream_reviews
dream_review_resolve
```

`dream_enqueue` schedules a completed session. `dream_status` exposes queue state. `dream_reviews` lists unresolved evidence-gated candidates, and `dream_review_resolve` records an approve/reject decision with reviewer provenance. No Dreaming tool has direct Knowledge write authority; all writes still pass CyberBrain evidence/promotion policy and Knowledge Evolution.

Dream evidence selection must remain causally bounded and focal-topic scoped. The completed session itself is primary evidence and must be represented directly with original Episode provenance; long transcripts must be reduced to bounded topic-local excerpts rather than copied wholesale into reasoning prompts. Historical semantic recall is supplementary context, not a substitute for the session being dreamed. Runtime recall may apply a configured semantic-score floor, must reject explicit project mismatches when the session has one stable project, and must apply a deterministic topic-relevance guard before evidence reaches reasoning. Structured `Phase N` focal topics may not consolidate evidence from a different phase, and explicit identifiers such as commit hashes must match exactly. Reasoner claims must pass evidence-ID validation before advisory or topic-irrelevant claims can be dropped, so filtering cannot bypass fabricated-evidence fail-closed behavior.

## Legacy aliases

Legacy client tools may be supported temporarily by a compatibility adapter, not by polluting the canonical domain API.

Known legacy behavior bugs are not part of the new canonical contract.
