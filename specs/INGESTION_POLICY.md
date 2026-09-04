# Ingestion Policy v1

## Pipeline

```text
validate input
→ reject secrets/garbage
→ normalize content
→ compute content_hash
→ resolve canonical metadata/entity identity
→ exact duplicate check
→ semantic/evolution check when applicable
→ generate embedding
→ persist
→ verify write result
```

## Required behavior

- New writes must conform to canonical v1 schemas.
- Exact duplicate/idempotent retries should return the existing canonical result where safe rather than create duplicate points.
- Durable writes must not proceed when embedding generation fails.
- Unknown extension metadata must be placed under `extensions`/`context` rather than silently promoted to top-level schema.
- `source` describes provenance, not arbitrary file metadata.
- User-confirmed/manual writes may bypass Dreaming evidence thresholds but never bypass schema/security validation.

## Garbage rejection

Reject content that is empty, whitespace-only, credential-like, or structurally invalid.

Low-value content should be filtered by deterministic rules where possible. Do not rely solely on an LLM classifier to decide persistence.

## Content normalization

For hashing/idempotency, normalize line endings and outer whitespace while preserving meaningful internal content.

Do not lowercase or aggressively rewrite stored content merely to compute a hash.

## Knowledge writes

Knowledge ingestion must resolve entity identity before evolution decisions.

A write may produce `insert_new`, `no_change`, `evolve`, `context_split`, or `reject` as defined by `EVOLUTION_SPEC.md`.

## Episodic writes

New episodes require `session_id` and canonical UTC `event_time`.

Episodes default to `dream_status=pending` unless explicitly written as already-consolidated/system-generated records under a trusted internal path.

## Verification

After storage mutation, verify the provider/storage operation completed successfully before reporting success to the caller.
