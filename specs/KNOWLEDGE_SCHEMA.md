# Knowledge Schema v1

## Required fields

```text
id
schema_version
record_type
content
domain
topic
entity_type
entity_name
version
status
created_at
updated_at
content_hash
```

## Optional fields

```text
summary
project
tags
keywords
supersedes_id
superseded_by_id
change_reason
importance
verification
confidence
provenance_type
source
evidence_ids
origin
dream_run_id
negative_knowledge
embedding_version
context
extensions
```

## Canonical enums

### record_type

```text
knowledge
```

### status

```text
active
superseded
deprecated
rejected
```

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
```

## Rules

- `id` is immutable.
- `schema_version` starts at `1`.
- `record_type` must be `knowledge`.
- `version` starts at `1` and increments only for the same logical entity identity.
- `status=active` must be unique for a canonical entity identity unless the schema explicitly marks variants as context-dependent.
- `content_hash` is SHA-256 over normalized content and is used for exact duplicate/idempotency checks.
- `confidence`, when present, is a float in `[0,1]` and never replaces `verification`.
- `evidence_ids` references source episode/knowledge IDs supporting the record.
- `negative_knowledge=true` marks a failed/rejected approach preserved to prevent repetition.
- `supersedes_id` and `superseded_by_id` form explicit evolution links.
- Unknown provider/domain-specific metadata must be placed under `extensions` or `context`, not added arbitrarily as new top-level fields.

## Entity identity

The exact entity identity algorithm is defined in `EVOLUTION_SPEC.md`, but v1 identity is derived from normalized:

```text
domain + topic + entity_type + entity_name + relevant context scope
```

Context must be included when two otherwise-identical entities are legitimately different, e.g. Windows vs Linux behavior.

## Timestamps

`created_at` and `updated_at` use UTC RFC3339 strings.

Example:

```text
2026-09-04T15:20:31.123Z
```

## Example

```yaml
id: 7ed8c4ce-2dd4-4ed2-8e96-54bd5319fd99
schema_version: 1
record_type: knowledge
content: CyberBrain providers use authenticated MCP Streamable HTTP at /mcp.
summary: Authenticated MCP provider transport standard.
domain: ops
topic: mcp_provider_standard
entity_type: decision
entity_name: cyberbrain_mcp_transport
project: CyberBrain
version: 1
status: active
importance: high
verification: user_confirmed
confidence: 1.0
provenance_type: user_confirmed
source: design_session
evidence_ids: []
origin: manual
negative_knowledge: false
content_hash: <sha256>
embedding_version: nomic-embed-text@v1
created_at: 2026-09-04T15:20:31.123Z
updated_at: 2026-09-04T15:20:31.123Z
```
