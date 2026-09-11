# CyberBrain Schema-V2 Collection Cleanup — 2026-09-11

> Historical operational record. Non-normative evidence: it documents one executed
> owner-authorized retention decision. Current guidance lives in
> `docs/CURRENT_RUNTIME.md` and `docs/V2_MIGRATION_RUNBOOK.md`.

## Owner decision

On 2026-09-11 the owner declared the post-cutover **acceptance window closed** and
authorized cleanup, explicitly stating that the rollback pair was **not** required.
This is the authorization required by `docs/V2_MIGRATION_RUNBOOK.md` before stage
collections may be removed.

## Pre-cleanup inventory

The store held eight collections: the live V2 pair, the rollback pair, the
pre-migration snapshot pair, and the original canonical pair.

| Collection | Points | Disposition |
| --- | --- | --- |
| `cyberbrain_knowledge_v2_stage` | 4934 | **live — retained** |
| `cyberbrain_episodic_v2_stage` | 195 | **live — retained** |
| `cyberbrain_knowledge_v1_stage` | 4891 | dropped (prior live pair / rollback target) |
| `cyberbrain_episodic_v1_stage` | 171 | dropped (prior live pair / rollback target) |
| `cyberbrain_knowledge` | 4878 | dropped (original canonical pair) |
| `cyberbrain_episodic` | 167 | dropped (original canonical pair) |
| `cyberbrain_knowledge_snapshot_clone` | 4863 | dropped (2026-09-04 pre-migration snapshot) |
| `cyberbrain_episodic_snapshot_clone_20260904` | 151 | dropped (2026-09-04 pre-migration snapshot) |

## Method

1. Read the live pair from the running API container environment and **abort** if it
   was not the expected V2 stage pair.
2. Reject any deletion target equal to the live pair (fail-closed guard).
3. `POST /collections/{collection}/snapshots` for each of the six targets, download
   the snapshot file, record declared size, on-disk bytes, and sha256.
4. Validate one snapshot by re-uploading it into a scratch collection and comparing
   point counts against the source collection.
5. Compress the retained snapshots with `gzip -9` and verify with `gzip -t`.
6. `DELETE /collections/{collection}` and re-verify the store lists only two.
7. Confirm the live pair still serves reads and still accepts writes.

## Evidence

```text
DELETE responses                          HTTP 200 result=true (6/6)
collections after cleanup                 2 (live V2 pair only)
live Knowledge points                     4934 -> 4937 (3 records written during the same session)
live Episodic points                      195 (unchanged)
restore validation                        scratch collection points_count=171 == source 171,
                                          scroll returned a real record with 23 payload keys
snapshot integrity                        gzip -t passed for all retained snapshots
qdrant data directory                     1.5 GiB -> 119 MiB
retained compressed snapshots             155 MiB
```

Snapshot manifest (per-file sha256) and the compressed snapshots are kept on the
deployment host:

```text
/home/dinhtc/docker-all/_retired-collections-20260911/
  MANIFEST.txt
  *.snapshot.gz   (mode 0600)
```

They are intentionally not committed to this repository (binary size). They exist
only as a short-term re-examination aid after an owner-requested removal; delete
them once the owner confirms they are no longer wanted.

## Restore procedure

```bash
cd /home/dinhtc/docker-all/_retired-collections-20260911
gunzip <file>.snapshot.gz
curl -X POST -H "api-key: $QDRANT_API_KEY" \
  -F "snapshot=@<file>.snapshot" \
  "http://localhost:6333/collections/<target-collection>/snapshots/upload?priority=snapshot"
```

Recovery recreates the collection from the snapshot contents; it does not restore
the collection into the live pair automatically. A recovered collection is an
offline artifact until a separate, reviewed decision points a runtime at it.

## Boundary

This cleanup changed no runtime configuration, no code, and no image. The live pair,
its writers, and every CyberBrain service container were left untouched and reported
healthy before and after.
