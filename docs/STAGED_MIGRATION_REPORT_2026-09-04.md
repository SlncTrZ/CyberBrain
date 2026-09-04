# CyberBrain V1 Staged Migration Report — 2026-09-04

> Historical document. Historical staged-migration report retained for provenance. The final V1 runtime is now using the validated staged collections during the rollback window.

This report covers a staged migration only. No legacy production collection was modified or cut over.

## Source boundary

Source migration data came from Qdrant snapshots created at approximately 03:54 UTC on 2026-09-04:

- `cyberbrain_knowledge`: 4,863 points, 768-d Cosine vectors.
- `cyberbrain_episodic`: 151 points, 768-d Cosine vectors.

The snapshots were restored to snapshot-consistent clone collections before migration. Migration did not scan the changing live collections.

Snapshot artifacts and SHA-256 files are stored under:

`migration_artifacts/2026-09-04/`

## Stage collections

- `cyberbrain_knowledge_v1_stage`
- `cyberbrain_episodic_v1_stage`

Original point IDs and original vectors were preserved. No re-embedding occurred.

## Knowledge migration

Source: 4,863 points.

Stage: 4,853 points.

Disposition:

- 4,524 legacy source chunks → canonical V1 Knowledge with `status=deprecated`, `origin=migration`, unique legacy identity, and preserved source metadata.
- 329 identity-ready evolution-era records → canonical V1 Knowledge.
- 12 duplicate-active identity groups were repaired structurally using explicit version then timestamp ordering.
- Resulting status counts:
  - 313 active
  - 16 superseded
  - 4,524 deprecated
- 0 duplicate-active groups remain.
- 0 broken supersession links.

Ten session-oriented records found in the legacy Knowledge collection were not forced into Knowledge. All ten had deterministic Episode core fields and were cross-migrated into the Episodic stage instead.

## Episodic migration

Legacy Episodic source: 151 points.

Directly migrated from Episodic source: 146 points.

Cross-migrated from misfiled Knowledge: 10 points.

Current Episodic stage total after cross-collection repair: 156 points; after approved synthetic-session orphan preservation: 161 points.

All migrated historical Episodes have `dream_status=skipped` so migration does not implicitly schedule historical Dreaming.

## Synthetic-session orphan repair

Five legacy Episodic points had content, timestamp, agent, and chat-history/message metadata, but their historical `session_id` value was empty and no recoverable session identifier existed elsewhere in the payload.

Approved preservation policy:

- create one explicit migration-only synthetic session ID per orphan: `legacy-orphan:<point-id>`;
- preserve the original point ID and vector;
- set `context.legacy_session_missing=true`;
- record `extensions.migration.synthetic_session_id=true` and the session-ID scheme;
- set `dream_status=skipped` so historical orphan messages do not implicitly schedule Dreaming.

All five orphan messages were migrated under this policy. No unresolved source rows remain.

## Validation results

Final staged manifest:

- Initial snapshot boundary: 5,014 source rows / 5,014 written rows.
- Final maintenance-freeze delta: +1 Knowledge row.
- Final frozen manifest: 5,015 source rows / 5,015 written rows.
- 0 unresolved rows

Runtime validation:

- 0 vector mismatches
- 0 unexpected target points
- 0 missing expected target points
- 0 content-hash mismatches
- 0 broken Knowledge supersession links
- 0 duplicate-active Knowledge groups
- maximum active records per canonical identity: 1
- 0 Episodic missing-core records in the current stage

Pydantic canonical schema validation:

- Initial stage: 4,853 / 4,853 Knowledge records valid.
- Final frozen stage after delta: 4,854 / 4,854 Knowledge records valid
- 161 / 161 Episode records valid
- 0 validation errors

## Stage backups

Snapshots were created for both stage collections after validation and copied to `migration_artifacts/2026-09-04/` with SHA-256 checksum files. A final snapshot pair was created again after the synthetic-session orphan repair.

## Cutover status

The CyberBrain provider is running against the validated V1 stage collections during the acceptance/rollback window. The legacy source collections remain unchanged and available for rollback. External gateway behavior is owned and validated separately from CyberBrain.
