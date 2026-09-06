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

## Current tools

```text
help
knowledge_search
knowledge_store
knowledge_timeline
memory_search
memory_store
dream_enqueue
dream_status
dream_reason_claim
dream_reason_submit
dream_reviews
dream_review_resolve
tech_store
tech_find
ai_memory_read
conversation_save
conversation_recall
```

CyberBrain keeps the original V1 Knowledge/Memory/Dreaming surface and adds two canonical operational tools for an external MCP Dream Reasoner inbox. The final five tools remain temporary MeiLin compatibility aliases used during migration/cutover. Gateway canonical names are owned by the gateway; the provider exposes local MCP tool names.

### `help`

Read-only. Returns the running provider contract, version metadata, contract hash, authentication description, capabilities, and current usage guide.

### Knowledge tools

- `knowledge_search` searches canonical knowledge and applies advertised filters.
- `knowledge_store` inserts or evolves canonical knowledge with explicit evolution outcomes.
- `knowledge_timeline` returns version history for one canonical entity identity.

### Memory tools

- `memory_search` searches episodic memory and applies session/channel/role/agent/project/topic filters.
- `memory_store` stores one canonical episodic record with required `session_id` and `event_time`.

### MeiLin compatibility aliases

- `tech_store` maps legacy technical notes into canonical Knowledge Evolution writes.
- `tech_find` maps legacy technical recall into canonical Knowledge search.
- `ai_memory_read` performs combined Knowledge + Episodic recall for legacy clients.
- `conversation_save` maps legacy conversation writes into canonical episodic storage.
- `conversation_recall` maps legacy conversation recall into canonical episodic search.

These aliases are compatibility adapters only. They do not create a second business-logic path and may be retired after all clients use canonical CyberBrain tools.

### Dreaming operations

- `dream_enqueue` queues a completed session for the Dream worker. Optional focal topics may be supplied.
- `dream_status` returns queue status for one session.
- `dream_reason_claim` leases the next pending bounded micro-reasoning task to an external MCP consumer such as a dedicated ChatGPT Reasoner session.
- `dream_reason_submit` submits structured evidence-grounded claims for the active lease; task ID, claim token, confidence, and evidence references are validated before acceptance.
- `dream_reviews` lists unresolved evidence-gated candidates that require human review.
- `dream_review_resolve` approves or rejects one existing review candidate and records reviewer provenance.

Dreaming operations do not expose a direct write path. A candidate can reach Knowledge only through Reasoner provenance validation, the promotion gate, optional review resolution, and Knowledge Evolution writeback.

For v0.1.3 Dream worker routing, CyberBrain prepares the full Dream request and bounded micro-task set first, registers the whole run atomically in the Reason Task inbox, then gives external MCP consumers one common claim/submit window (`CYBERBRAIN_DREAM_MCP_WAIT_SECONDS`, default 30 seconds). MCP-completed tasks are preserved as the winning results. After the common deadline, only unfinished tasks are sent to the fallback Reasoner endpoint. The fallback router policy is: Gemini models through 9router first (`gem/gemini-pro`, then `gem/gemini-flash`), then dynamically discovered/probed OpenCode free models through 9router, then local Ollama as the final fallback. The MCP wait is run-level, not a serial per-task delay.
