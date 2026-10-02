# CyberBrain Tool Guide

> Contract guide updated: 2026-10-02

CyberBrain exposes an authenticated MCP Streamable HTTP provider at `/mcp`.

Gateway canonical namespace:

```text
cyberbrain.*
```

## Authentication

Primary:

```text
Authorization: Bearer <token>
```

Optional compatibility:

```text
X-API-Key: <token>
```

The provider fails closed when authentication is required but not configured. An optional server-side `CYBERBRAIN_TRUSTED_AGENT_ID` may bind one trusted agent only after Bearer/X-API-Key verification; caller headers or tool payloads cannot create trusted identity, and this setting alone does not enable broader modes. An optional `CYBERBRAIN_PRINCIPAL_REGISTRY_FILE` binds server-owned principal scope and operation grants after credential verification. Broader modes additionally require complete runtime quota limits; caller fields cannot select or widen authority. See `docs/TENANCY_OPERATIONS.md`.

## Canonical tools

```text
help
knowledge_search
knowledge_relations
knowledge_relation_propose
knowledge_relation_review
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

These are the current canonical CyberBrain tool names exposed by the provider. Gateway-level namespacing, when used, is owned by the integration layer rather than by CyberBrain.

## Agent operating boundary

Normal external agents are memory consumers/producers. Their ordinary CyberBrain workflow is intentionally small:

```text
need context → search → optionally exact get
worth persisting → knowledge_store or memory_store
```

CyberBrain owns what happens after storage: normalization, validation, embedding, Knowledge Evolution, the Episodic pending lifecycle, automatic Dream scheduling/processing, evidence/provenance gates, promotion/review, and Knowledge writeback. Normal Codex/Pi/Claude-style clients should not orchestrate those internal stages.

`dream_enqueue`, Prediction operations, Calibration observation, Dream reason-task operations, and review operations remain available as explicit advanced/control surfaces. Their presence in the MCP catalog does not make them part of the normal agent read/write loop.

M3 Salience, M4 Concept Formation, M5 Working Memory, M6 Agent Self-Model, and M7 Memory Lifecycle are active internal server mechanisms, not additional public MCP tools. Normal canonical and legacy recall/store calls pass through the same bounded coordinator after authorization. M5 transient state is not a caller-managed durable scratchpad; M6 persists only accepted/evidence-ready hypotheses outside ordinary recall; M7 changes lifecycle/access metadata only and does not hard-delete. See `specs/COGNITIVE_RUNTIME_PATH.md`.

Prediction Learning is the causal exception to fully post-storage processing: a valid Prediction must exist before its outcome is known. Do not fabricate a Prediction retrospectively from a completed-action summary. A runtime with a genuine pre-action/outcome event seam may bridge those events into Prediction Learning without exposing the subsystem to the acting agent.

## Compatibility aliases

```text
tech_store
tech_find
ai_memory_read
conversation_save
conversation_recall
```

These aliases are retained only for legacy client compatibility. They adapt into the canonical Knowledge/Memory services and do not define a second business-logic or persistence path.

### `help`

Read-only. Returns the running provider contract, software version metadata, contract hash, authentication description, capabilities, and current usage guide. The software/package version derives from the canonical `cyberbrain/_version.py` source; contract/schema versions remain independent.

### Knowledge tools

- `knowledge_search` searches canonical Knowledge and applies advertised filters. The server then runs the active M3→M5→M7 path over a bounded authorized prefetch; optional `context_session_id` / `task_id` improve transient M5 identity without changing data filters. Schema-V2 ordinary recall is constrained to `status=active`, `record_class=knowledge`, and `ordinary_recall=true`, excluding Self-Model hypotheses, migration quarantine, and M7-suppressed rows. Canonical recall defaults to `view=compact`; use `view=full` only when broad search truly needs complete rows.
- `knowledge_get` fetches one canonical Knowledge record by exact UUID and returns the full stored row only when that ID is eligible under the caller's bound authority scope. It does not perform semantic search.
- `knowledge_store` inserts or evolves canonical knowledge with explicit evolution outcomes.
- `knowledge_timeline` returns version history for one canonical entity identity.

### Memory tools

- `memory_search` searches Episodic Memory and applies session/channel/role/agent/project/topic filters. The server then runs the active M3→M5→M7 path over a bounded authorized prefetch; optional `context_session_id` / `task_id` identify transient M5 context only. Schema-V2 ordinary recall additionally requires `ordinary_recall=true`, so M7-suppressed Episodes remain stored but do not appear in normal semantic recall. Canonical recall defaults to `view=compact`; use `view=full` only when broad search truly needs complete rows.
- `memory_get` fetches one canonical Episodic record by exact UUID and returns the full stored row only when that ID is eligible under the caller's bound authority scope. It does not perform semantic search.
- `memory_store` stores one canonical episodic record with required `session_id` and `event_time`. Ordinary Episodes enter `dream_status=pending`; the server-side Dream scheduler later discovers eligible quiet sessions automatically.

### Compact recall

Canonical `knowledge_search` and `memory_search` use compact-first retrieval so broad recall does not automatically return large stored payloads.

- `view=compact` is the default.
- When a stored `summary` exists, compact recall returns it as `recall_text` with `recall_text_source=summary`.
- Without a summary, compact recall returns a bounded content excerpt of at most 1,200 characters with `recall_text_source=content_excerpt`.
- Compact rows report the original `content_chars` and `content_omitted=true`; the full stored `content` and `summary` fields are omitted from that response.
- `view=full` preserves the complete canonical search row for focused follow-up when detail is actually needed.

Search ranking still uses the stored record embedding. Compact recall changes only the MCP response projection; it does not mutate Knowledge, Episodic Memory, vectors, provenance, or Dreaming evidence.

Preferred focused-recall pattern is `*_search` in compact mode → select one returned canonical ID → `knowledge_get` or `memory_get` for that exact record. Exact fetch uses storage-side ID + scope eligibility and returns the same not-found shape when the ID is absent or outside caller scope, avoiding a cross-scope enumeration signal.

### Compatibility aliases

- `tech_store` maps legacy technical notes into canonical Knowledge Evolution writes.
- `tech_find` maps legacy technical recall into canonical Knowledge search.
- `ai_memory_read` performs combined Knowledge + Episodic recall for legacy clients.
- `conversation_save` maps legacy conversation writes into canonical episodic storage.
- `conversation_recall` maps legacy conversation recall into canonical episodic search.

These aliases may be retired after dependent clients have migrated to canonical CyberBrain tools. New integrations should use the canonical tools above. Compatibility recall aliases retain their legacy full-payload behavior; compact-first projection applies only to canonical `knowledge_search` and `memory_search`.

### Prediction learning

- `prediction_record` stores an explicit expected outcome and prior confidence as canonical Episodic Memory before an action or decision is evaluated. Optional `strategy_tags[]` can capture bounded prospective workflow labels for later M6 correlational analysis. When trusted agent identity is bound, the record is attributed to that agent, marked `identity_trust=authenticated`, and a conflicting payload `agent` is rejected.
- `prediction_resolve` stores an observed outcome linked to a prior Prediction and derives a deterministic prediction-error class plus confidence-weighted error signal. Under trusted agent binding, the referenced Prediction must belong to that agent before Outcome persistence.
- `prediction_observe` is read-only and summarizes the current observation sample: prediction/outcome counts, resolved/unresolved predictions, duplicate outcomes, assessment/error distributions, and mean confidence/error signals. Under trusted agent binding, the `agent` filter is forced to the trusted agent and substitution is rejected.
- `prediction_pending` is read-only and lists unresolved Predictions so an agent can return later and close the learning loop with `prediction_resolve`. Results are bounded and include `may_be_incomplete` when the configured scan limit is reached. Under trusted agent binding, the worklist is limited to that agent.
- Prediction/Outcome records remain Episodic evidence. Neither prior confidence nor outcome assessment has direct Knowledge write authority.
- Outcome identity context is inherited from the referenced Prediction so callers cannot silently relabel the learning event.

Prediction operations are an explicit causal-learning surface, not a required ordinary-agent loop. Use them only when a caller/integration can preserve the real pre-outcome ordering. Dreaming can consume the resulting Prediction/Outcome Episodes automatically through the normal episodic pipeline. See `specs/PREDICTION_LEARNING.md` for the full contract.

### Calibration

- `calibration_observe` is read-only and analyzes resolved Prediction Learning evidence. Under trusted agent binding, its sample is forced to the trusted agent.
- It reports sample count, excluded indeterminate outcomes, mean prior confidence, mean empirical score, calibration bias, squared calibration error, bounded/incomplete status, and a sample-level assessment.
- Below `minimum_samples`, assessment is always `insufficient_evidence` even if the numerical bias is large. Reaching the configured minimum makes the sample reviewable; it does not automatically activate any downstream mechanism.
- With enough samples, bias above the configured threshold is labeled `overconfident`, below the negative threshold `underconfident`, otherwise `roughly_calibrated`.
- These labels describe the selected evidence sample only. They are not persisted as agent identity or Knowledge and do not change prompts, strategy, routing, or model behavior.

See `specs/METACOGNITION_CALIBRATION.md`. `prediction_resolve` triggers M6 evaluation for the authenticated trusted principal; readiness remains fail-closed. In the current single-owner deployment, all callers using the shared MCP credential map to `coding-agents`, so their new trusted Prediction/Outcome evidence accumulates in one pool. Active M6/M7 behavior is documented in `specs/AGENT_SELF_MODEL.md`, `specs/MEMORY_LIFECYCLE.md`, and `specs/COGNITIVE_RUNTIME_PATH.md`.

### Dreaming operations

- `dream_enqueue` explicitly/manual-queues a completed session for the Dream worker. It is an advanced override/control path; ordinary pending Episodes are discovered and queued automatically by the server-side Dream scheduler after the configured quiet period. Optional focal topics may be supplied.
- `dream_status` returns queue status for one session.
- `dream_reason_claim` leases the next pending bounded micro-reasoning task to an external MCP consumer such as a dedicated ChatGPT Reasoner session.
- `dream_reason_submit` submits structured evidence-grounded claims for the active lease; task ID, claim token, confidence, and evidence references are validated before acceptance.
- `dream_reviews` lists unresolved evidence-gated candidates that require human review.
- `dream_review_resolve` approves or rejects one existing review candidate and records reviewer provenance.

Dreaming operations do not expose a direct write path. A candidate can reach Knowledge only through Reasoner provenance validation, the promotion gate, optional review resolution, and Knowledge Evolution writeback.

For current Dream worker routing, CyberBrain prepares the full Dream request and bounded micro-task set first, registers the whole run atomically in the Reason Task inbox, then gives external MCP consumers one common claim/submit window (`CYBERBRAIN_DREAM_MCP_WAIT_SECONDS`, default 30 seconds). MCP-completed tasks are preserved as the winning results. After the common deadline, only unfinished tasks are sent to the configured fallback Reasoner endpoint. The fallback service reads an ordered, provider-neutral route configuration: provider 1 models in declared order, then provider 2 models, and so on. CyberBrain does not hard-code provider names, model names, or an external routing product. Credentials are resolved only from runtime environment variables named by each route's `auth_env`. The MCP wait is run-level, not a serial per-task delay.


## Scope and review pagination

All data-bearing MCP tools require a bound caller authority and the corresponding
read/write/review/background operation grant. Canonical search/get/timeline applies
hard effective scope before downstream cognition; durable stores resolve concrete
attribution before embedding/persistence. Compatibility aliases share the same
service enforcement. Caller input cannot assign authenticated/system-derived
identity trust on ordinary writes.

The current single-owner runtime treats unconstrained owner identity dimensions
as optional query selectors; a constrained dimension can only narrow by a true
subset. Scoped callers are denied owner-global Dream and Prediction operations
until durable scope propagation exists. Broader deployment modes remain disabled.

`dream_reviews` accepts optional `cursor` (maximum 1024 characters), alongside
`limit` (1–500). Each returned row includes `review_cursor`; pass the final row's
cursor to obtain the next page. Ordering is creation time, run ID, candidate index.
The endpoint still returns a list, and an exhausted page is empty. Invalid cursors
fail validation. Cursor pagination never resolves or promotes a review.


Source correctness/build acceptance is defined in `docs/SOURCE_ACCEPTANCE.md`. Long-term live effectiveness, evidence maturity and retrieval promotion are evaluated separately under `docs/LIVE_EVALUATION.md`.

### Configured Knowledge ranking

Knowledge search defaults to vector retrieval. A deployment may select foreground literal routing or semantic/BM25 RRF fusion using `CYBERBRAIN_KNOWLEDGE_RETRIEVAL_MODE`; clients use the same tools and arguments. `score` is semantic similarity and may be null for lexical-only results. Optional `_retrieval` metadata distinguishes the method and lexical/fusion scores. Compact recall preserves this metadata. See `specs/RETRIEVAL_POLICY.md` for bounds and failure behavior.

### Explicit typed relation assertions

`knowledge_store.extensions.relations` accepts the strict assertion schema documented in `specs/RELATION_TRAVERSAL.md`. Proposed assertions require readable canonical endpoints and evidence. Accepted/rejected assertions additionally require authenticated `admin_review` and a review note; relation-only changes create a Knowledge version. Relation persistence does not enable traversal in `knowledge_search` yet.

### Typed relation recall and explicit review

Use `knowledge_relations` when you know the seed Knowledge UUIDs and need typed paths,
reverse dependencies or historical anchors. Input is `seed_ids`, optional `policy`
(depth/direction/kinds/as_of/node/edge/path/storage limits), `context_tokens` and
`record_tokens`. The response contains paths, typed proof records, physical read counts,
token estimates and truncation reasons. Default context is 4096 estimated tokens,
256 per record; path metadata and proof text count toward the same budget. An incomplete
proof set is never packed as a complete path. Graph metadata is separate from similarity
and confidence. Ordinary `knowledge_search` continues configured vector/literal/hybrid
ranking; compact results retain a small relation summary rather than full assertions/index.

`knowledge_relation_propose` merges a strict proposed bundle into the active `source_id`.
It requires read/write authority and cannot replace a different existing assertion.
`knowledge_relation_review` accepts/rejects one `relation_id` with a nonblank `note`;
it requires admin_review plus read/write. Both use native Evolution and return the new
version. A concurrent edit or stale source UUID requires reloading the current version;
the API does not silently overwrite it. Evidence existence is not semantic proof.
An LLM may submit proposals, but the service never automatically accepts them.

Operator activation is explicit: `CYBERBRAIN_RELATION_RETRIEVAL_ENABLED=true` for caller
recall and `CYBERBRAIN_DREAM_RELATION_ENABLED=true` for Dream. Defaults are false and
require authenticated transport, verified indexes and complete scoped projections.
Dream expansion uses bucket-end as_of, background authority and separate read/item/token
budgets. It preserves typed path/proof provenance; it does not generate or accept relations.
Preparation, protected backfill and rollback are in `docs/RELATION_ROLLOUT.md`.

## Quick start with JSON examples

These examples show MCP `tools/call` parameters, not complete JSON-RPC envelopes.
Names are provider-local; use the gateway's namespaced equivalent when required.
UUIDs, times and text below are illustrative fixtures, not production evidence.
Replace them with authorized real records and real event times. Read/write/review
grants and deployment feature flags remain mandatory. Examples are not executed by help.

Read the contract:

```json
{"name":"help","arguments":{}}
```

Search compact context (an empty successful result is `[]`, not an error):

```json
{"name":"knowledge_search","arguments":{"query":"deployment rollback","project":"ExampleProject","limit":5,"view":"compact"}}
```

Fetch one selected full record using the UUID returned by search:

```json
{"name":"knowledge_get","arguments":{"id":"00000000-0000-4000-8000-000000000001"}}
```

Persist a verified useful fact using a stable entity identity. Supply a verification
level only when the evidence actually supports it; this example leaves the default:

```json
{"name":"knowledge_store","arguments":{"content":"Illustrative operating rule: retain the previous image before a rollout.","domain":"ops","topic":"deployment","entity_type":"procedure","entity_name":"rollout-backup","project":"ExampleProject"}}
```

Search episodic context:

```json
{"name":"memory_search","arguments":{"query":"rollout outcome","project":"ExampleProject","limit":5}}
```

Persist an observed event. A real caller must supply its actual event time:

```json
{"name":"memory_store","arguments":{"content":"Illustrative event: a rollout check completed.","session_id":"example-session","event_time":"2026-10-02T07:00:00Z","project":"ExampleProject"}}
```

Explore typed relations from a known seed; empty paths are valid if no eligible
accepted assertions exist. Check `truncated` and `truncation_reasons` before
treating the returned paths as complete:

```json
{"name":"knowledge_relations","arguments":{"seed_ids":["00000000-0000-4000-8000-000000000001"],"context_tokens":4096,"record_tokens":256}}
```

Review an existing proposal only after checking its evidence. Replace both the source
UUID with the current active version and the relation ID with the proposed assertion ID:

```json
{"name":"knowledge_relation_review","arguments":{"source_id":"00000000-0000-4000-8000-000000000001","relation_id":"0000000000000000000000000000000000000000000000000000000000000000","status":"rejected","note":"Illustrative review: supplied evidence does not establish this relationship."}}
```

Read one page of pending Dream reviews without approving or promoting anything:

```json
{"name":"dream_reviews","arguments":{"limit":10}}
```

For proposals, follow the generated `RelationBundle`, `RelationAssertion` and
referenced definitions below; relation IDs and canonical endpoint identity must
satisfy domain validation. For Dream submission, use only the task and lease returned
by `dream_reason_claim`; never invent credentials or evidence references.

### Responses and recovery

Tool responses carry text content containing JSON, except `help`, which returns
the readable contract. Search/timeline/review lists, exact records, evolution results,
Prediction reports and relation path envelopes have different shapes; a wrapper must
not assume every successful response is a list. Store/evolution results include
`outcome`, `record` and `previous_id`; inspect the outcome before claiming that a
new active version was created.

A missing or out-of-scope exact fetch uses this shape:

```json
{"error":{"type":"not_found","message":"Knowledge record not found","retryable":false}}
```

| Condition | Layer / signal | Correct action |
| --- | --- | --- |
| Missing or invalid authentication | HTTP authentication rejection, normally 401 | Repair the authorized connection; do not place credentials in prompts or stored records. |
| Bad type, unknown field, invalid UUID, enum or bounds | MCP/schema rejection or `validation_error` | Correct the request using the generated schema; do not retry unchanged. |
| Missing or out-of-scope record | `not_found` | Check the selected ID and authorized scope; the response intentionally does not reveal foreign records. |
| Concurrent Knowledge/relation edit | `conflict` | Reload the active source version and re-evaluate before submitting again. |
| Disabled feature, missing service or denied bound authority | `configuration_error` | Check deployment flags and granted operations; a caller payload cannot grant access. |
| Secret-bearing content | `sensitive_data` | Remove sensitive content; never bypass scanning or persist credentials. |
| Storage, embedding or provider outage | `unavailable`, `retryable=true` | Use bounded retry; for writes, check whether persistence occurred before resubmitting. |
| Unexpected provider failure | `internal_error` | Preserve a safe error summary for investigation; do not treat it as an empty match. |
| Gateway cannot reach provider | Gateway `provider_unavailable` | A bounded read-only retry may recover; repeated failures require connection/health investigation. |

Provider domain errors use `{"error":{"type":...,"message":...,"retryable":...}}`.
Transport/SDK/gateway errors may use a different envelope. Relation budget exhaustion
is reported as truncation, not as proof that no relationship exists.

### Omitted values and deployment state

The generated tables show only defaults explicitly declared in the advertised
schema. Current dispatch defaults include canonical search `limit=5`,
`view=compact`, `dream_reviews.limit=100`, and
`dream_reason_claim.lease_seconds=300`. Other omitted values may be resolved by
domain services or deployment configuration; do not interpret an absent schema
default as zero, null or permission to choose arbitrary values.

Tool availability in the provider catalog does not prove that a feature is enabled
or that the gateway/client has refreshed its catalog. This contract describes
supported behavior, not current collection counts, learned conclusions or live
effectiveness. Use runtime checks for those questions.
