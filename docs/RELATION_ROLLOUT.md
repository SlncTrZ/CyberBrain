# Typed relation rollout

Source acceptance, deployment availability and longitudinal learning evidence are separate.
The controlled source benchmark is in `benchmarks/RELATIONS_CONTROLLED.md`.

## Preparation

1. Run the full source suite and the optional gate on a new empty loopback Qdrant.
   The gate checks caller/proposal/review, scoped paths, backfill preservation and real snapshot
   restore/reapply. The benchmark driver refuses an existing/non-loopback instance.
2. Build and retain an immutable source-commit image; retain the previous image and safe image/flag
   rollback settings. Preserve existing authentication, identity, collections, embedding and
   dependency services. The software version comes from cyberbrain/_version.py.
3. Run `scripts/relations_rollout.py census` with the deployment-managed settings.
   The operator CLI supports single_owner only. It scans at most 50000 canonical records /
   64 MiB payload, validates parent/assertion schemas and rejects namespace collisions.
   It reports only counts and a scoped canonical source hash.
4. Quiesce every canonical writer, including API, worker and scheduler. Finish active work
   gracefully; do not take an uncoordinated data checkpoint while writers are running.
5. Capture `checkpoint --checkpoint /protected/path --writers-quiesced`.
   The destination must not exist. Both existing collections are snapshotted; checksums and a
   matching before/after census are verified. Files use restrictive operator permissions.
   Existing operational SQLite backups/health checks remain part of the deployment procedure.

## Application

Run `apply --checkpoint /protected/path --expected-source-hash HASH --writers-quiesced`.
The checkpoint must match collection names, manifest hash, file checksums, authority scope and
current canonical source. The entire census is validated before writes. Missing projections
are derived in-place; existing matching projections are retained. ID, vector, content, timestamps,
other fields/extensions and collection counts remain unchanged. Exactly two collections remain.

Application is not an atomic multi-point transaction. An interrupted projection-only application
can retry with the same checkpoint: source hashes intentionally exclude the disposable index.
A canonical write, collision, invalid schema or changed checkpoint requires stopping and
investigating; do not bypass the gate or infer/fabricate missing facts.

Payload indexes are explicitly prepared and verified. Normal application startup never performs
backfill or index creation. Any missing scoped projection prevents recall rather than hiding
relations silently.

## Canary and activation

Run the operator `canary --seed-id UUID` using an existing eligible record. Output contains only
numeric budget/path counts and truncation metadata. A zero-path corpus demonstrates availability,
not factual relationship quality; controlled positive fixtures are required independently.

Caller flag: `CYBERBRAIN_RELATION_RETRIEVAL_ENABLED=true`.
Dream flag: `CYBERBRAIN_DREAM_RELATION_ENABLED=true`.
Both default false, require auth, and fail startup when required indexes are absent.
Dream uses bucket-end as_of and background authority. No relation generation/acceptance is
automatic. Ordinary Knowledge ranking retains its configured vector/literal/hybrid mode.

Check health/readiness, unauthenticated rejection, authenticated help/catalog, all existing tools,
new tool schemas, actual source/image Fingerprinting and fresh worker/scheduler health. Check
numeric corpus counts/namespace coverage; keep content and credentials out of operational reports.
A stale known seed ID or changed target version must not silently redirect a path.

## Rollback

First disable both relation flags and restore the prior image/configuration. This retains new
canonical work and harmless derived projections. Retain the image/flag rollback definition.

A full snapshot restore is appropriate only during the protected quiesced window, before new
canonical work resumes, with verified backups and explicit operational authority. A later restore
can erase subsequent work and must not be used as an automatic feature rollback. The real isolated
gate exercises snapshot restore/reapply; it does not manufacture production rollback evidence.

Record deployment measurements in docs/history/DEPLOYMENT_FINGERPRINT_227.md.
Day-30/day-60 usefulness belongs in the live evaluation record and never lowers source acceptance.
