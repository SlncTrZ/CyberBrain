# CyberBrain Schema-V2 Production Cutover — 2026-09-09

> Historical operational record. Current guidance lives in `docs/CURRENT_RUNTIME.md` and `docs/V2_MIGRATION_RUNBOOK.md`.

## Pre-cutover evidence

The complete four-source corpus was migrated with deterministic tooling only: no LLM calls, no re-embedding, and no semantic rewrite. A final write-control window stopped the canonical API, Dream worker, and Dream scheduler writers before the last catch-up and validator pass.

Final frozen pre-cutover snapshot:

```text
source union       5,088
target union       5,088
Knowledge V2       4,905
Episodic V2          183
missing               0
extra                 0
quarantine            1
validator          PASS
```

The single quarantine record was an unmappable legacy Episode with no trustworthy session identity; it remained non-recallable rather than receiving fabricated metadata.

## Cutover

All production storage consumers were switched together from the validated V1 stage pair to the validated V2 pair. A deployment backup was retained as the rollback configuration. The application services were then recreated/restarted against V2.

Post-cutover acceptance:

```text
core health/ready        PASS
Dream worker             healthy
Dream scheduler          running
Reasoner/router           healthy
MCP tools                24
canonical Knowledge read PASS
canonical Episodic read  PASS
legacy read aliases      PASS
startup error scan       clean
```

## Write isolation proof

Two meaningful cutover checkpoints were written after the read gate:

```text
Knowledge ID  9d294dd1-d929-4152-b12d-b034bd730259
Episode ID    5514e8d4-6123-483b-af65-443a84f6083b
```

Direct storage verification confirmed both IDs exist in the V2 collections and are absent from their V1 counterparts. Exact canonical fetch and legacy reads remained functional.

## Behavioral boundary

The data-format cutover does not activate downstream cognition automatically. M6 remains fail-closed because trusted prospective outcome evidence is insufficient. M7 remains shadow-only because a metadata-only full-corpus pass lacks enough historical access/Salience/Concept/relevance evidence for safe lifecycle actuation.
