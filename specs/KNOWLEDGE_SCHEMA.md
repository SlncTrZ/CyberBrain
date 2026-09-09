# Knowledge Schema v2

> Canonical source contract. `schema_version=2` is the current Knowledge payload contract; software/package versioning remains independent.

## Required fields

```text
id
schema_version
record_type
record_class
content
domain
topic
entity_type
entity_name
version
status
verification
origin
content_hash
identity_trust
lifecycle_state
ordinary_recall
retention_score
retention_directive
access_count
lifecycle_reason_codes
context
extensions
created_at
updated_at
```

## Optional fields

```text
summary
tenant
user
agent
project
session_id
tags
keywords
supersedes_id
superseded_by_id
change_reason
importance
confidence
provenance_type
source
evidence_ids
dream_run_id
negative_knowledge
embedding_version
last_accessed_at
lifecycle_updated_at
```

## Canonical enums

### record_type

```text
knowledge
```

### record_class

```text
knowledge
self_model_hypothesis
migration_quarantine
```

`record_class=knowledge` is the only class eligible for ordinary Knowledge recall.

`record_class=self_model_hypothesis` stores explicitly reviewed M6 Self-Model hypotheses inside the existing Knowledge collection. It is not canonical world truth and defaults to `ordinary_recall=false`.

`record_class=migration_quarantine` preserves legacy records that cannot be mapped safely into canonical Knowledge/Episodic semantics without fabricating metadata. Quarantine records are provenance-preserving, suppressed from ordinary recall, and must not be treated as validated Knowledge.

### status

```text
active
superseded
deprecated
rejected
```

Knowledge truth/evolution status is independent from lifecycle availability. `status` must not be reused as a forgetting/suppression control.

### verification

```text
user_confirmed
observed
tested
derived
research
unverified
```

### origin

```text
manual
agent
ingestion
dream
migration
cognition
```

### identity_trust

```text
unspecified
legacy_untrusted
authenticated
system_derived
```

`identity_trust` describes the trust level of stored identity attribution; it does not grant authorization.

- `unspecified` — no trustworthy identity provenance is available;
- `legacy_untrusted` — an identity-like field existed historically but predates or bypasses the trusted runtime identity boundary;
- `authenticated` — attribution was bound from a verified runtime authentication boundary;
- `system_derived` — identity was deterministically inherited/derived by trusted CyberBrain logic from already trusted evidence.

Migration must never upgrade historical `agent` strings to `authenticated` merely because their value looks plausible.

### lifecycle_state

```text
active
suppressed
```

### retention_directive

```text
default
keep
```

## Schema and identity rules

- `id` is immutable.
- Current canonical `schema_version` is `2`.
- `record_type` must be `knowledge`.
- `record_class` controls semantic class, not Qdrant collection placement; all classes remain in the canonical Knowledge collection.
- `version` starts at `1` and increments only for the same logical entity identity.
- `status=active` must be unique for a canonical entity identity unless the schema explicitly models context-dependent variants.
- `content_hash` is SHA-256 over normalized content and is used for exact duplicate/idempotency checks.
- `confidence`, when present, is a float in `[0,1]` and never replaces `verification`.
- `evidence_ids` references canonical source record IDs supporting the record.
- `negative_knowledge=true` preserves a failed/rejected approach to reduce repetition.
- `supersedes_id` and `superseded_by_id` form explicit Knowledge Evolution links.
- Unknown provider/domain-specific metadata belongs under `extensions` or `context`, not arbitrary new top-level fields.
- `tenant`, `user`, `agent`, `project`, and `session_id` must not be fabricated during migration. Missing historical identity remains `None`.

## Ordinary recall boundary

Normal caller-visible Knowledge search is limited to records satisfying at least:

```text
status = active
record_class = knowledge
ordinary_recall = true
```

Lifecycle suppression, Self-Model persistence, and migration quarantine therefore do not pollute ordinary Knowledge recall.

Exact/history/administrative paths may inspect records outside ordinary recall when independently authorized. `ordinary_recall=false` is not deletion.

## Lifecycle metadata

M7 uses metadata separate from Knowledge truth/evolution:

```text
lifecycle_state
ordinary_recall
retention_score
retention_directive
access_count
last_accessed_at
lifecycle_updated_at
lifecycle_reason_codes
```

Rules:

- `retention_score` is bounded to `[0,1]` and is an explainable lifecycle signal, not truth confidence.
- `access_count` is non-negative.
- `lifecycle_reason_codes` are unique content-free reason codes.
- suppression is reversible and normally sets `lifecycle_state=suppressed` plus `ordinary_recall=false`.
- reactivation restores `lifecycle_state=active` plus `ordinary_recall=true` when policy permits.
- M7 does not hard-delete canonical content as its normal forgetting mechanism.
- `retention_directive=keep` protects a record from ordinary lifecycle suppression and can reactivate a suppressed record.
- Lifecycle decisions do not rewrite `content`, `content_hash`, provenance, evidence links, verification, or Knowledge Evolution status.

See `MEMORY_LIFECYCLE.md`.

## Self-Model records

Reviewed M6 hypotheses are stored through existing Knowledge Evolution with:

```text
record_class = self_model_hypothesis
domain = cognition
topic = agent_self_model
entity_type = self_model_hypothesis
identity_trust = system_derived
origin = cognition
verification = derived
ordinary_recall = false
retention_directive = keep
```

The detailed hypothesis evidence/review contract lives in `AGENT_SELF_MODEL.md`. A persisted Self-Model hypothesis remains revisable evidence-backed cognition, not durable identity truth.

## Migration quarantine

A legacy record that cannot be mapped without inventing required canonical metadata is preserved rather than dropped. Quarantine defaults to:

```text
record_class = migration_quarantine
status = deprecated
lifecycle_state = suppressed
ordinary_recall = false
retention_score = 0
origin = migration
verification = unverified
```

Its original non-content metadata is retained under migration provenance extensions where safe. The original point ID, normalized content, and vector are preserved by the V2 migration tooling.

## Entity identity

The exact entity identity algorithm is defined in `EVOLUTION_SPEC.md`, but canonical identity is derived from normalized:

```text
domain + topic + entity_type + entity_name + relevant context scope
```

Context must be included when otherwise-identical entities are legitimately different, for example Windows versus Linux behavior.

## Timestamps

`created_at`, `updated_at`, `last_accessed_at`, and `lifecycle_updated_at` use timezone-aware UTC RFC3339 values when present.

Example:

```text
2026-09-04T15:20:31.123Z
```

## Example

```yaml
id: 7ed8c4ce-2dd4-4ed2-8e96-54bd5319fd99
schema_version: 2
record_type: knowledge
record_class: knowledge
content: CyberBrain providers use authenticated MCP Streamable HTTP at /mcp.
summary: Authenticated MCP provider transport standard.
domain: ops
topic: mcp_provider_standard
entity_type: decision
entity_name: cyberbrain_mcp_transport
tenant: null
user: null
agent: null
project: CyberBrain
session_id: null
identity_trust: unspecified
version: 1
status: active
verification: user_confirmed
confidence: 1.0
provenance_type: user_confirmed
source: design_session
origin: manual
negative_knowledge: false
content_hash: <sha256>
embedding_version: nomic-embed-text@v1
lifecycle_state: active
ordinary_recall: true
retention_score: 1.0
retention_directive: default
access_count: 0
last_accessed_at: null
lifecycle_updated_at: null
lifecycle_reason_codes: []
context: {}
extensions: {}
created_at: 2026-09-04T15:20:31.123Z
updated_at: 2026-09-04T15:20:31.123Z
```
