# CyberBrain Current Runtime — 2026-09-04

## Ownership boundary

This document describes CyberBrain only. SlncTrZ-MCP owns gateway routing, canonical `<provider>.<tool>` names, gateway policy, provider lifecycle, and catalog composition. CyberBrain exposes provider-local MCP tool names. Gateway incompatibilities are reported at the boundary; they are not repaired from this project.

## Production compatibility runtime

The compatibility endpoint currently runs the CyberBrain V1 provider in the existing `meilin-mcp` service slot so existing URL/port wiring can remain unchanged during the acceptance window.

```text
external/client
    ↓
compatibility endpoint :8767 /mcp
    ↓
CyberBrain V1 provider
    ├── Knowledge Engine
    ├── Episodic Memory Engine
    ├── Dreaming operations
    ├── Qdrant
    └── Ollama embedding runtime

CyberBrain Dream worker
    ↓
MCP Reasoner boundary
    ├── preferred operating policy: primary MCP Reasoner for most Dreaming work
    └── deployed local CPU fallback provider: qwen3-vl:2b-thinking
```

Temporary MeiLin aliases are adapters into canonical CyberBrain services; they are not a second persistence implementation.

## Active V1 collections

During the rollback/acceptance window CyberBrain uses:

- `cyberbrain_knowledge_v1_stage`
- `cyberbrain_episodic_v1_stage`

Final frozen migration state:

- Knowledge stage: 4,854 records.
- Episodic stage: 161 records.
- Final source manifest: 5,015 / 5,015 rows preserved.
- Duplicate-active canonical identities: 0.
- Vector mismatches: 0.
- Pydantic validation errors: 0.

Original legacy collections remain intact for rollback and forensic comparison. Staged names are deployment artifacts, not extra CyberBrain domain concepts.

## Search compatibility baseline

```text
CYBERBRAIN_KNOWLEDGE_SEARCH_SCORE_THRESHOLD=0.55
CYBERBRAIN_MEMORY_SEARCH_SCORE_THRESHOLD=0.55
```

Similarity remains retrieval relevance, not truth confidence.

Docker API and Dream worker share `/data/knowledge_evolution.lock` through `CYBERBRAIN_KNOWLEDGE_EVOLUTION_LOCK_FILE`, providing single-host cross-process serialization for Knowledge Evolution. Pending evolutions are reconciled on startup.

## MCP surface

Canonical V1 tools: `help`, `knowledge_search`, `knowledge_store`, `knowledge_timeline`, `memory_search`, `memory_store`, `dream_enqueue`, `dream_status`, `dream_reviews`, `dream_review_resolve`.

Temporary compatibility aliases: `tech_store`, `tech_find`, `ai_memory_read`, `conversation_save`, `conversation_recall`.

Provider-local names remain unnamespaced. Canonical gateway names are gateway-owned.

## Dreaming

```text
completed session
→ queue
→ evidence retrieval
→ multipass Reasoner
→ evidence gate
→ DreamRun audit
→ promote/review/reject
→ Knowledge Evolution writeback
```

Historical migrated Episodes are `dream_status=skipped` so migration does not retroactively queue the old corpus.


## Runtime readiness

`/health` reports process liveness. `/ready` performs dependency-aware readiness checks against both canonical Qdrant collections and the embedding runtime. Docker health checks use `/ready` so a dead Qdrant/embedding dependency cannot be reported as a healthy CyberBrain provider.

## Dream worker state

Dream jobs are claimed atomically in SQLite so multiple workers cannot process the same pending job concurrently. Queue state owns intermediate processing/retry state. Canonical Episodes transition to `processed` with `dream_run_id` and `dreamed_at` after a successful run, or to `failed` when the job fails.

Dreaming is background work. The agreed operating policy is MCP-first Reasoning for the large majority of Dreaming work, with the local CPU Reasoner reserved as fallback. The current deployment includes the local `qwen3-vl:2b-thinking` MCP Reasoner service and Dream worker; primary/fallback routing remains an operational routing concern rather than a V1 domain requirement. Local fallback may take several minutes for a full multipass run without blocking foreground Knowledge/Memory use.

## Rollback

CyberBrain rollback artifacts are under `migration_artifacts/2026-09-04/`, including source snapshots, final frozen source snapshots, migration manifest/checksum, validation reports, and final V1 stage snapshots. Do not delete or rewrite legacy source collections during the acceptance window.
