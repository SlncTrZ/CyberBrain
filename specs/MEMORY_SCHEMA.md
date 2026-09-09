# Episodic Memory Schema v2

> Canonical source contract. `schema_version=2` is the current Episodic payload contract; software/package versioning remains independent.

## Required fields

```text
id
schema_version
record_type
content
session_id
event_time
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
channel
role
tenant
user
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
last_accessed_at
lifecycle_updated_at
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

### identity_trust

```text
unspecified
legacy_untrusted
authenticated
system_derived
```

Identity trust records provenance of attribution; it is not an authorization grant.

- legacy `agent` values that predate the trusted runtime identity seam remain `legacy_untrusted`;
- authenticated Prediction events created under the trusted runtime identity boundary may be marked `authenticated`;
- Outcome identity is inherited from its referenced Prediction and preserves the Prediction's `identity_trust`;
- migration must never relabel historical identity as authenticated merely because the stored string matches a current agent name.

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

## Rules

- `id` is immutable.
- Current canonical `schema_version` is `2`.
- `record_type` must be `episode`.
- `event_time` is the canonical temporal ordering field and uses timezone-aware UTC RFC3339.
- `session_id` is mandatory and non-empty for canonical Episode writes.
- `created_at` and `updated_at` are timezone-aware; V2 adds explicit `updated_at` to the Episode contract.
- `content_hash` is SHA-256 over normalized content and supports idempotency/exact duplicate detection.
- `tenant`, `user`, `agent`, `project`, and `topic` are first-class scope/identity metadata where available.
- missing historical tenant/user/agent/project/session information must not be fabricated during migration.
- unknown source-specific fields belong under `extensions` or `context`.
- Dreaming consumes canonical Episodic records and never reads raw provider-specific payload shapes directly.

## Ordinary recall boundary

Normal Episodic search includes only:

```text
ordinary_recall = true
```

M7 soft suppression can therefore remove stale/low-value Episodes from ordinary semantic recall without deleting their canonical content or provenance.

Exact/history/administrative paths may inspect suppressed records when separately authorized. `ordinary_recall=false` is not deletion and is reversible.

## Lifecycle metadata

M7 uses:

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

- lifecycle state is independent from `dream_status`;
- `retention_score` is bounded to `[0,1]` and is not truth confidence;
- `access_count` is non-negative;
- suppression is metadata-only and reversible;
- reactivation may restore ordinary recall when later relevance/evidence warrants it;
- lifecycle writes do not alter `content`, `content_hash`, session/event identity, Dream provenance, or cognition evidence.

See `MEMORY_LIFECYCLE.md`.

## Cognitive learning context

Prediction-learning events remain canonical Episodes and use `context.cognition` rather than another durable collection or top-level record type.

Reserved shape:

```text
context.cognition.kind = prediction | outcome
```

Prediction records use their immutable Episode ID as `context.cognition.prediction_id`. Outcome records reference that ID and preserve expected outcome, prior confidence, observed outcome, assessment, and deterministic prediction-error signals.

Prospective Prediction metadata may also contain bounded `strategy_tags[]` inside `context.cognition`. These tags are explicit strategy/workflow labels supplied at prediction time; they are not reconstructed from post-outcome prose. M6 may use them only as correlational evidence for workflow/strategy hypotheses.

The cognition context is evidence metadata. It does not change `record_type=episode` and grants no direct Knowledge write authority.

When trusted runtime identity is bound:

```text
prediction_record
→ agent forced to trusted agent
→ identity_trust = authenticated

prediction_resolve
→ referenced Prediction agent must match trusted agent
→ Outcome inherits agent/project/topic/session + identity_trust
```

See `PREDICTION_LEARNING.md` and `AGENT_SELF_MODEL.md`.

## Session model

A session is a cognitive work boundary rather than a calendar-day boundary.

Session termination can be explicit or inferred by higher-level orchestration from inactivity/context changes. The Episode schema itself stores session identity and event time.

## Dream processing

New ordinary episodes default to:

```text
dream_status = pending
```

A Dreaming job should mark session-level processing atomically through the Dreaming state store rather than repeatedly mutating every Episode during intermediate reasoning. Per-Episode `dream_status` exists for observability/recovery but must not become the only job queue.

Lifecycle suppression is separate from Dream processing. A processed Episode may remain active, while a stale processed Episode may later be suppressed from ordinary recall without changing its Dream status.

## Migration normalization

Legacy integer/string timestamps and incomplete payloads are migration concerns handled by compatibility normalizers.

Schema V2 migration follows these rules:

- prefer already-canonical V1 stage records when available;
- merge raw collection deltas so no source point ID is silently lost;
- preserve source point ID, normalized content, and vector;
- mark historical identity attribution `legacy_untrusted` when applicable;
- never fabricate missing tenant/user/agent/session metadata;
- a raw record that cannot satisfy canonical Episode requirements safely is preserved as `record_class=migration_quarantine` in the Knowledge collection rather than dropped or converted using invented values.

## Example

```yaml
id: eaf13f05-f235-4f0c-b93f-00f5a8ab91f2
schema_version: 2
record_type: episode
content: Decided to use CyberBrain as shared memory infrastructure for multiple AI clients.
session_id: session-20260904-cyberbrain
event_time: 2026-09-04T15:25:00.000Z
channel: chatgpt
role: summary
tenant: null
user: null
agent: chatgpt
project: CyberBrain
topic: architecture
identity_trust: legacy_untrusted
keywords:
  - CyberBrain
  - shared-memory
importance: high
source: conversation
dream_status: pending
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
created_at: 2026-09-04T15:25:00.000Z
updated_at: 2026-09-04T15:25:00.000Z
```
