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

The provider fails closed when authentication is required but not configured.

## Canonical tools

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
dream_enqueue
dream_status
dream_reason_claim
dream_reason_submit
dream_reviews
dream_review_resolve
```

These are the current canonical CyberBrain tool names exposed by the provider. Gateway-level namespacing, when used, is owned by the integration layer rather than by CyberBrain.

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

Read-only. Returns the running provider contract, version metadata, contract hash, authentication description, capabilities, and current usage guide.

### Knowledge tools

- `knowledge_search` searches canonical knowledge and applies advertised filters.
- `knowledge_store` inserts or evolves canonical knowledge with explicit evolution outcomes.
- `knowledge_timeline` returns version history for one canonical entity identity.

### Memory tools

- `memory_search` searches episodic memory and applies session/channel/role/agent/project/topic filters.
- `memory_store` stores one canonical episodic record with required `session_id` and `event_time`.

### Compatibility aliases

- `tech_store` maps legacy technical notes into canonical Knowledge Evolution writes.
- `tech_find` maps legacy technical recall into canonical Knowledge search.
- `ai_memory_read` performs combined Knowledge + Episodic recall for legacy clients.
- `conversation_save` maps legacy conversation writes into canonical episodic storage.
- `conversation_recall` maps legacy conversation recall into canonical episodic search.

These aliases may be retired after dependent clients have migrated to canonical CyberBrain tools. New integrations should use the canonical tools above.

### Prediction learning

- `prediction_record` stores an explicit expected outcome and prior confidence as canonical Episodic Memory before an action or decision is evaluated.
- `prediction_resolve` stores an observed outcome linked to a prior Prediction and derives a deterministic prediction-error class plus confidence-weighted error signal.
- `prediction_observe` is read-only and summarizes the current observation sample: prediction/outcome counts, resolved/unresolved predictions, duplicate outcomes, assessment/error distributions, and mean confidence/error signals.
- Prediction/Outcome records remain Episodic evidence. Neither prior confidence nor outcome assessment has direct Knowledge write authority.
- Outcome identity context is inherited from the referenced Prediction so callers cannot silently relabel the learning event.

See `specs/PREDICTION_LEARNING.md` for the full contract.

### Dreaming operations

- `dream_enqueue` queues a completed session for the Dream worker. Optional focal topics may be supplied.
- `dream_status` returns queue status for one session.
- `dream_reason_claim` leases the next pending bounded micro-reasoning task to an external MCP consumer such as a dedicated ChatGPT Reasoner session.
- `dream_reason_submit` submits structured evidence-grounded claims for the active lease; task ID, claim token, confidence, and evidence references are validated before acceptance.
- `dream_reviews` lists unresolved evidence-gated candidates that require human review.
- `dream_review_resolve` approves or rejects one existing review candidate and records reviewer provenance.

Dreaming operations do not expose a direct write path. A candidate can reach Knowledge only through Reasoner provenance validation, the promotion gate, optional review resolution, and Knowledge Evolution writeback.

For current Dream worker routing, CyberBrain prepares the full Dream request and bounded micro-task set first, registers the whole run atomically in the Reason Task inbox, then gives external MCP consumers one common claim/submit window (`CYBERBRAIN_DREAM_MCP_WAIT_SECONDS`, default 30 seconds). MCP-completed tasks are preserved as the winning results. After the common deadline, only unfinished tasks are sent to the configured fallback Reasoner endpoint. The fallback service reads an ordered, provider-neutral route configuration: provider 1 models in declared order, then provider 2 models, and so on. CyberBrain does not hard-code provider names, model names, or an external routing product. Credentials are resolved only from runtime environment variables named by each route's `auth_env`. The MCP wait is run-level, not a serial per-task delay.
