# Episodic Memory Schema v1

## Required fields

```text
id
schema_version
record_type
content
session_id
event_time
content_hash
created_at
```

## Optional fields

```text
summary
channel
role
agent
project
topic
keywords
importance
source
dream_status
dream_run_id
dreamed_at
embedding_version
context
extensions
```

## Canonical enums

### record_type

```text
episode
```

### role

```text
user
assistant
system
tool
summary
other
```

### dream_status

```text
pending
processing
processed
skipped
failed
```

## Rules

- `id` is immutable.
- `schema_version` starts at `1`.
- `event_time` is the canonical temporal ordering field and uses UTC RFC3339.
- `session_id` is mandatory for all new writes.
- `content_hash` is SHA-256 over normalized content and supports idempotency/exact duplicate detection.
- `channel`, `role`, `agent`, and `project` remain first-class because they are likely retrieval/session filters.
- Unknown source-specific fields belong under `extensions` or `context`.
- Dreaming consumes canonical episodic records and never reads raw provider-specific payload shapes directly.

## Session model

A session is a cognitive work boundary rather than a calendar-day boundary.

Session termination can be explicit or inferred by higher-level orchestration from inactivity/context changes. The episode schema itself stores only the session identity and event time.

## Dream processing

New episodes default to:

```text
dream_status = pending
```

A Dreaming job should mark session-level processing atomically through the Dreaming state store rather than repeatedly mutating every episode during intermediate reasoning. Per-episode `dream_status` exists for observability/recovery but must not become the only job queue.

## Timestamp normalization

New writes always use UTC RFC3339.

Legacy integer/string timestamps are migration concerns handled by a compatibility normalizer, not by weakening the v1 canonical schema.

## Example

```yaml
id: eaf13f05-f235-4f0c-b93f-00f5a8ab91f2
schema_version: 1
record_type: episode
content: Decided to extract CyberBrain from MeiLin as shared infrastructure.
session_id: session-20260904-cyberbrain
event_time: 2026-09-04T15:25:00.000Z
channel: chatgpt
role: summary
agent: chatgpt
project: CyberBrain
topic: architecture
keywords:
  - CyberBrain
  - MeiLin
importance: high
source: conversation
dream_status: pending
content_hash: <sha256>
embedding_version: nomic-embed-text@v1
created_at: 2026-09-04T15:25:00.000Z
```
