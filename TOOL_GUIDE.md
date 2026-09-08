# CyberBrain Tool Guide

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

The provider fails closed when authentication is required but not configured. An optional server-side `CYBERBRAIN_TRUSTED_AGENT_ID` may bind one trusted agent only after Bearer/X-API-Key verification; caller headers or tool payloads cannot create trusted identity, and this setting does not enable `agent_ready` or `multi_user` deployment modes.

## Canonical tools

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

These are the current canonical CyberBrain tool names exposed by the provider. Gateway-level namespacing, when used, is owned by the integration layer rather than by CyberBrain.

## Agent operating boundary

Normal external agents are memory consumers/producers. Their ordinary CyberBrain workflow is intentionally small:

```text
need context → search → optionally exact get
worth persisting → knowledge_store or memory_store
```

CyberBrain owns what happens after storage: normalization, validation, embedding, Knowledge Evolution, the Episodic pending lifecycle, automatic Dream scheduling/processing, evidence/provenance gates, promotion/review, and Knowledge writeback. Normal Codex/Pi/Claude-style clients should not orchestrate those internal stages.

`dream_enqueue`, Prediction operations, Calibration observation, Dream reason-task operations, and review operations remain available as explicit advanced/control surfaces. Their presence in the MCP catalog does not make them part of the normal agent read/write loop.

M3 Salience, M4 Concept Formation, and M5 Working Memory are internal source-level cognitive mechanisms, not additional public MCP tools. In particular, M5 transient state is not exposed as a caller-managed durable scratchpad; any future runtime integration remains behind the existing authorization boundary.

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

- `knowledge_search` searches canonical knowledge and applies advertised filters. Canonical recall defaults to `view=compact`; use `view=full` only when broad search truly needs complete rows.
- `knowledge_get` fetches one canonical Knowledge record by exact UUID and returns the full stored row only when that ID is eligible under the caller's bound authority scope. It does not perform semantic search.
- `knowledge_store` inserts or evolves canonical knowledge with explicit evolution outcomes.
- `knowledge_timeline` returns version history for one canonical entity identity.

### Memory tools

- `memory_search` searches episodic memory and applies session/channel/role/agent/project/topic filters. Canonical recall defaults to `view=compact`; use `view=full` only when broad search truly needs complete rows.
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

- `prediction_record` stores an explicit expected outcome and prior confidence as canonical Episodic Memory before an action or decision is evaluated. When trusted agent identity is bound, the record is attributed to that agent and a conflicting payload `agent` is rejected.
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

See `specs/METACOGNITION_CALIBRATION.md`.

### Dreaming operations

- `dream_enqueue` explicitly/manual-queues a completed session for the Dream worker. It is an advanced override/control path; ordinary pending Episodes are discovered and queued automatically by the server-side Dream scheduler after the configured quiet period. Optional focal topics may be supplied.
- `dream_status` returns queue status for one session.
- `dream_reason_claim` leases the next pending bounded micro-reasoning task to an external MCP consumer such as a dedicated ChatGPT Reasoner session.
- `dream_reason_submit` submits structured evidence-grounded claims for the active lease; task ID, claim token, confidence, and evidence references are validated before acceptance.
- `dream_reviews` lists unresolved evidence-gated candidates that require human review.
- `dream_review_resolve` approves or rejects one existing review candidate and records reviewer provenance.

Dreaming operations do not expose a direct write path. A candidate can reach Knowledge only through Reasoner provenance validation, the promotion gate, optional review resolution, and Knowledge Evolution writeback.

For current Dream worker routing, CyberBrain prepares the full Dream request and bounded micro-task set first, registers the whole run atomically in the Reason Task inbox, then gives external MCP consumers one common claim/submit window (`CYBERBRAIN_DREAM_MCP_WAIT_SECONDS`, default 30 seconds). MCP-completed tasks are preserved as the winning results. After the common deadline, only unfinished tasks are sent to the configured fallback Reasoner endpoint. The fallback service reads an ordered, provider-neutral route configuration: provider 1 models in declared order, then provider 2 models, and so on. CyberBrain does not hard-code provider names, model names, or an external routing product. Credentials are resolved only from runtime environment variables named by each route's `auth_env`. The MCP wait is run-level, not a serial per-task delay.
