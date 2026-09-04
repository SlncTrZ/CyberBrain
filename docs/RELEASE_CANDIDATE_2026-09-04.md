# Historical CyberBrain V1 Release Candidate — 2026-09-04

> Historical document. This records the release-candidate gate before V1 completion. For current runtime state see `CURRENT_RUNTIME_2026-09-04.md` and `V1_FREEZE_2026-09-04.md`.

## Scope

This release candidate covers CyberBrain itself: canonical Knowledge, Episodic Memory, Dreaming, Reasoner integration, MCP/API, backup/restore, migration tooling, and temporary MeiLin compatibility aliases.

Gateway implementation details are outside CyberBrain ownership. If a gateway incompatibility is detected, stop at the boundary and report it rather than modifying gateway source or runtime.

## Verified baseline

- 122 automated tests pass in the final V1 baseline.
- Ruff is clean.
- CyberBrain production compatibility container is healthy.
- MCP Streamable HTTP `/mcp` is authenticated and exposes the live provider contract through `help`.
- Canonical Knowledge and Episodic search work against V1 stage collections.
- Temporary MeiLin compatibility aliases work when called directly against the CyberBrain provider.
- Search score thresholds are runtime-configurable; V1 migration compatibility baseline is 0.55 for Knowledge and Episodic search.
- `TOOL_GUIDE.md` is packaged in the runtime image so `help` works without a bind mount.
- Clean-host Docker integration passes with fresh Qdrant/Ollama volumes, API, Dream worker, and deterministic Reasoner.
- Knowledge Evolution uses a shared POSIX advisory lock in Docker deployments to serialize API/worker writes across processes, in addition to in-process identity locks and pending-evolution recovery.

## Canonical data state

Final frozen migration boundary:

- Knowledge source: 4,864 points.
- Episodic source: 151 points.
- Total frozen source rows: 5,015.

Validated V1 stage:

- `cyberbrain_knowledge_v1_stage`: 4,854 records.
- `cyberbrain_episodic_v1_stage`: 161 records.
- Manifest: 5,015 / 5,015 source rows written.
- Unresolved rows: 0.

The count shift between source collections and target collections is intentional:

- 10 session-oriented records originally misfiled in legacy Knowledge were cross-migrated into Episodic.
- 5 orphan Episodes with missing historical session IDs were preserved with explicit synthetic migration-only session IDs.

## Validation invariants

Final stage validation requires all of the following:

- 0 vector mismatches.
- 0 unexpected target points.
- 0 missing expected target points.
- 0 content-hash mismatches.
- 0 broken Knowledge supersession links.
- 0 duplicate-active canonical identity groups.
- maximum one active Knowledge record per canonical identity/context.
- all Knowledge payloads validate against canonical V1 Pydantic schema.
- all Episode payloads validate against canonical V1 Pydantic schema.

## Dreaming lifecycle

Verified lifecycle:

```text
completed session
→ queue
→ evidence retrieval
→ multipass Reasoner
→ evidence/promotion gate
→ DreamRun audit
→ auto-promote OR manual review
→ Knowledge Evolution writeback
```

Manual review approval is retry-safe. If an approval response is lost after a successful write, retrying the same approval returns the prior write audit and does not create duplicate Knowledge.

Historical migrated Episodes use `dream_status=skipped` so migration does not implicitly schedule Dreaming over the entire historical corpus.

## Backward compatibility

Canonical CyberBrain V1 tools:

- `help`
- `knowledge_search`
- `knowledge_store`
- `knowledge_timeline`
- `memory_search`
- `memory_store`
- `dream_enqueue`
- `dream_status`
- `dream_reviews`
- `dream_review_resolve`

Temporary MeiLin compatibility aliases:

- `tech_store`
- `tech_find`
- `ai_memory_read`
- `conversation_save`
- `conversation_recall`

Compatibility aliases are adapters into canonical CyberBrain services. They must not become a second persistence or business-logic implementation.

## Backup and rollback artifacts

Migration snapshots, manifests, validation reports, and SHA-256 files are stored under:

`migration_artifacts/2026-09-04/`

Important artifact groups:

- initial source snapshots and checksums;
- final frozen source snapshots and checksums;
- staged migration manifest and checksum;
- stage runtime validation reports;
- stage Pydantic validation reports;
- final stage snapshots after delta migration.

Legacy source collections remain available for rollback and forensic comparison.

## CyberBrain-side rollback

If CyberBrain itself fails acceptance:

1. Do not modify or delete legacy source collections.
2. Stop CyberBrain writes.
3. Preserve the current V1 stage snapshot and Dream SQLite files for diagnosis.
4. Point the CyberBrain deployment back to the last verified V1 stage snapshot, or restore that snapshot into fresh target collections.
5. If reverting the external compatibility endpoint is required, perform that deployment operation outside the CyberBrain codebase under the owning system's change-control process.

## V1 freeze

CyberBrain V1 is frozen for daily-use acceptance. See `docs/V1_FREEZE_2026-09-04.md`. New work requires evidence from real usage rather than architecture completeness.

## Historical remaining work at RC time

The following items were open at the release-candidate checkpoint. Numeric metrics, clean-host deployment verification, dependency-aware readiness, cross-process Evolution serialization, atomic Dream queue claiming, Episode Dream lifecycle updates, and additional security/time validation were completed before the final V1 freeze.

Still non-blocking after V1 completion:

- run a longer acceptance window on real production traffic;
- retire temporary MeiLin compatibility aliases after all clients migrate to canonical CyberBrain tools;
- decide final canonical collection names after acceptance; staged names remain deployment artifacts during the rollback window;
- optionally add a portable export/import CLI when a real operational need appears.

## Release gate

CyberBrain V1 should be considered ready for final release only when:

- the provider continues to pass health and MCP acceptance during the acceptance window;
- no schema or active-identity invariant regressions appear;
- backup/restore artifacts remain verifiable;
- Dream writes remain provenance-complete and auditable;
- external gateway/client compatibility issues, if any, are resolved by the owning component without introducing CyberBrain-specific gateway coupling.
