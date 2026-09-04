# Historical Architecture Audit — Legacy MeiLin Runtime

> Status: Historical Phase 0 evidence snapshot. This file describes the pre-CyberBrain legacy runtime and is retained for migration provenance.
> Current CyberBrain runtime: see `docs/CURRENT_RUNTIME_2026-09-04.md`.
> Historical source audited: `<legacy-deployment-root>/meilin-mcp`
> Historical container slot: `meilin-mcp`
> Compose project audited: `<legacy-deployment-root>/docker-compose.yml`

## Runtime topology

```text
SlncTrZ-MCP
   ↓ streamable-http provider
MeiLin MCP :8767 /mcp
   ↓
AtomicKnowledgeProcessor
   ├── Qdrant :6333
   └── Ollama :11434 / nomic-embed-text
```

The running container is built from:

```text
<legacy-deployment-root>/meilin-mcp
```

It has no source bind mount. Source changes require image rebuild/recreate before runtime behavior changes.

## MCP transport

Current server uses MCP Streamable HTTP through `StreamableHTTPSessionManager` and exposes:

```text
/mcp
```

Supported methods are GET, POST, and DELETE.

Authentication middleware accepts:

```text
Authorization: Bearer <token>
X-API-Key: <token>
```

The expected credential comes from runtime environment `MCP_AUTH_TOKEN`; it is not hard-coded in source.

### Important auth behavior

Current implementation only installs auth middleware when `MCP_AUTH_TOKEN` is non-empty. This means a deployment missing the secret becomes unauthenticated rather than refusing to start or refusing requests.

CyberBrain should preserve the transport/auth mechanism but tighten network deployment behavior to fail closed when authentication is required by policy.

## Current MCP tools — 8

### Legacy compatibility

1. `tech_store`
2. `tech_find`
3. `ai_memory_read`

### Knowledge

4. `knowledge_store`
5. `knowledge_search`
6. `knowledge_timeline`

### Episodic conversation memory

7. `conversation_save`
8. `conversation_recall`

No prompts or MCP resources are exposed by the active server.

## Tool to internal-function map

| Tool | Main internal path | Notes |
| --- | --- | --- |
| `tech_store` | `_classify_subject` → `AtomicKnowledgeProcessor.process_atom` | Legacy auto-classification |
| `tech_find` | `AtomicKnowledgeProcessor.search` | Ignores advertised `wing` argument in current implementation |
| `ai_memory_read` | `search(query)` + `search(query, wing="conversation")` | Merges knowledge + episodic results |
| `knowledge_store` | `process_atom` | Knowledge Evolution path |
| `knowledge_search` | `search` | Searches one/both collections |
| `knowledge_timeline` | `KnowledgeHistoryViewer.get_timeline` | Scroll-based version history |
| `conversation_save` | `process_atom(wing="conversation")` | Stores episodic point |
| `conversation_recall` | `search(wing="conversation")` | Advertised channel filter is not applied |

## Core modules

```text
meilin_mcp.py
streamable_http_server.py
meilin_knowledge/
├── atomic_processor.py
├── config.py
├── garbage_filter.py
└── knowledge_history.py
```

### `atomic_processor.py`

Owns:

- embedding generation
- Qdrant search
- Qdrant upsert
- entity lookup
- version calculation
- attempted soft deletion
- knowledge/episodic payload construction

### `config.py`

Owns:

- Qdrant connection settings
- Ollama connection/model
- 768 embedding dimension
- two collection names
- legacy wing → domain mapping
- search thresholds

### `knowledge_history.py`

Provides scroll-based history reads.

### `garbage_filter.py`

`SmartCleaner` is currently only a stub. There is no functioning garbage collection/compaction engine in the active MeiLin implementation.

## Embedding behavior

Current embedding implementation:

```text
provider: Ollama
model: nomic-embed-text
dimension: 768
input truncation: first 8192 characters
```

If embedding generation fails or returns an unexpected dimension, current code returns a 768-element zero vector rather than failing the write/search.

This is unsafe for CyberBrain because dependency failures can silently create low-quality or meaningless vectors. CyberBrain should fail loud/fail closed for durable writes and explicitly degrade or reject search when embedding generation fails.

## Search behavior

Search uses Qdrant vector search with optional metadata filters.

When no wing is provided it searches both collections and merges by score.

Configured defaults:

```text
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_SCORE_THRESHOLD = 0.7
LOW_POINTS_THRESHOLD = 100
```

The current implementation disables score-threshold filtering for all collections when any collection has fewer than `LOW_POINTS_THRESHOLD` points. This coupling should be reviewed during extraction.

## Knowledge Evolution behavior

Intended flow:

```text
find existing active entity
→ determine next version
→ embed new content
→ upsert new version
→ deprecate previous active versions
```

Current code has a critical defect in the deprecation path:

- `_search_collection()` returns payload fields and score but does not return the Qdrant point ID.
- `process_atom()` later attempts to read `point_id` or `id` from those search results.
- Therefore previously found active points normally cannot be addressed for soft deletion.

Runtime data independently shows multiple active versions for the same `(topic, entity_name)` groups, consistent with failed supersession behavior.

The current `_soft_delete` implementation must also be verified against the Qdrant payload-update API before reuse. CyberBrain should not copy this code without tests.

## Contract mismatches found

### `conversation_recall.channel`

The MCP schema advertises an optional `channel` filter, but `handle_call_tool()` does not pass it into the search path. Current recall therefore ignores the requested channel.

### `tech_find.wing`

The MCP schema advertises optional `wing`, but current implementation calls `processor.search(query, limit=5)` without passing `wing`.

### `knowledge_timeline.source_file`

Current write schema stores the normalized source in payload field:

```text
source
```

`KnowledgeHistoryViewer` filters timeline queries using:

```text
source_file
```

This does not match the new base payload schema.

### Episodic metadata visibility

`conversation_save` places `channel`, `role`, and an extra millisecond timestamp inside `extra_metadata` after `session_id`/`agent_name` are extracted.

`_search_collection()` does not expose `extra_metadata` in its normalized result object.

As a result, `conversation_recall` cannot reliably return/filter the channel/role metadata stored by newer calls.

## CyberBrain extraction boundary

Reusable concepts:

- Streamable HTTP MCP wrapper pattern
- Bearer/API-key auth mechanism
- two-collection model
- embedding adapter concept
- semantic search concept
- entity/version metadata concept
- legacy compatibility mappings where migration needs them

Do not copy unchanged:

- silent zero-vector fallback
- incomplete soft-delete/versioning path
- mixed payload schemas without migration layer
- stub garbage collector
- tool schemas that advertise filters not implemented
- MeiLin/persona-specific names and descriptions

## Phase 0 conclusion

The active MeiLin service is a strong behavioral prototype and a good reference for transport/auth/provider mechanics, but the data/evolution layer requires explicit normalization and tests before becoming CyberBrain core.
