# Legacy Migration Audit — 2026-09-04

> Historical document. Historical read-only legacy migration audit retained for provenance. Current V1 state is documented separately.

This audit is read-only. No production Qdrant points were modified.

## Live-state warning

The legacy Qdrant instance is receiving writes while the audit is running. Knowledge count moved from 4,862 to 4,863 during the read-only audit. Therefore, all counts below are snapshot-at-read observations, not a cutover-consistent snapshot.

A real migration must run from a Qdrant snapshot or during a defined maintenance/freeze boundary. Never perform a live scan and then assume the source remained unchanged for cutover.

## Current collections

- `cyberbrain_knowledge`
- `cyberbrain_episodic`

Both collections use the legacy payload shape. At audit time, none of the points had canonical V1 `schema_version` or `record_type` fields.

## Knowledge observations

Observed live count during the latest disposition pass: 4,863 points.

Dry-run dispositions:

- 4,524 `migrate_deprecated_legacy_chunk`
  - Legacy shape is primarily `content + domain + project + source`.
  - Canonical identity is unavailable.
  - Preserve the content as migration-origin `deprecated` knowledge with a unique legacy-chunk identity.
  - These records must not enter default active retrieval.
- 329 `migrate_active`
  - Have `domain + topic + entity_type + entity_name + status` and can be mapped structurally to V1.
- 10 `review_episodic_like_in_knowledge`
  - Carry `session_id` and episodic-like fields while residing in the Knowledge collection.
  - Do not guess whether they are durable Knowledge or Episodes.

Legacy Knowledge top-level shape before mapping:

- 4,524 points: `content, domain, project, source`
- 250 points: evolution-era identity/status payload
- 69 points: web-research evolution payload
- 10 points: session-oriented records in Knowledge
- 8 points: identity/status payload without `wing`
- 1 point: identity/status payload with `extra_metadata`

## Duplicate-active Knowledge

There are 12 duplicate-active canonical identity groups.

All 12 groups have a deterministic structural winner using:

1. highest explicit `version`, then
2. latest parseable `timestamp`.

No top-rank ties were observed in the latest audit.

Migration policy:

- winning record remains `active`;
- older active records become `superseded`;
- preserve their original content and point IDs;
- create canonical supersession links in the staged target;
- never mutate the source collection during planning.

## Episodic observations

Observed count: 151 points.

Dry-run dispositions:

- 146 `migrate_episode`
  - Have content, session ID, and parseable timestamp.
  - Numeric and ISO-like legacy timestamps are both supported by the deterministic mapper.
  - Migrated historical Episodes default to `dream_status=skipped` so migration does not implicitly schedule historical Dreaming.
- 5 `review`
  - Missing `session_id`.
  - Do not synthesize a session ID.

Legacy Episodic shape summary:

- 88 daily-log/chat-history style records
- 54 minimal `agent_name + content + project + session_id + timestamp`
- 8 richer records with domain/topic/entity metadata
- 1 alternate channel/date record

## Canonical preservation policy

The migration mapper is deterministic and read-only. It may normalize, parse timestamps, preserve metadata, classify migration disposition, and plan duplicate-active repair. It may not infer semantic identity from content.

For legacy source chunks without canonical identity:

```text
status      = deprecated
origin      = migration
entity_type = legacy_chunk
topic       = legacy_source_chunk
entity_name = legacy:<original-point-id>
```

This preserves the historical corpus without polluting default active canonical retrieval.

## Preconditions before any production mutation

1. Create and verify Qdrant snapshots for both legacy collections.
2. Freeze or explicitly define the source write boundary.
3. Re-run the audit against the frozen snapshot.
4. Produce a complete migration manifest containing source point ID → target point ID/disposition.
5. Stage into new target collections; do not overwrite the legacy collections.
6. Validate counts, checksums, active uniqueness, vector dimensions, search behavior, and Episode timestamps.
7. Run application-level read comparisons.
8. Only then perform client cutover.
9. Keep legacy collections available for rollback until the acceptance window closes.
