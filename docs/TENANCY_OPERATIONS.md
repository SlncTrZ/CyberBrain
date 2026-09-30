# Tenancy and operations

The default mode remains `single_owner`. Existing shared Bearer/X-API-Key configuration and optional server-configured trusted agent continue to work. Broader modes are explicit opt-in configurations; nothing in a source test changes an existing deployment.

## Principal configuration

Set `CYBERBRAIN_PRINCIPAL_REGISTRY_FILE` to a server-owned JSON file following `config/principals.example.json`. Each principal has a unique identifier, a `credential_env` reference, normalized scope and explicit operation grants. The file contains no credential values. Provision those environment variables independently; credentials stay out of canonical payloads, snapshots, logs and distributions.

When a registry is configured it is the only MCP credential authority; the legacy shared token does not provide an unscoped fallback. The SDK receives the verified principal identity so a different principal cannot reuse its MCP session. Caller headers/payloads cannot select identity, operation grants or authenticated provenance.

`agent_ready` requires exactly one configured agent. `multi_user` requires exactly one tenant and user. Configure one agent as well when using trusted Prediction/M6 behavior. Every present write-attribution dimension must become a singleton. Optional contextual project/session fields remain inside the required principal boundary; a constrained selector may only narrow its grant.

Broader modes require all of:

| Setting | Meaning |
| --- | --- |
| `CYBERBRAIN_QUOTA_REQUESTS_PER_MINUTE` | Foreground tool admission |
| `CYBERBRAIN_QUOTA_WRITES_PER_MINUTE` | Canonical write operation admission |
| `CYBERBRAIN_QUOTA_RECALL_LIMIT` | Maximum requested recall size |
| `CYBERBRAIN_QUOTA_DREAM_ENQUEUES_PER_HOUR` | Explicit Dream enqueue admission |
| `CYBERBRAIN_QUOTA_BACKGROUND_RUNS_PER_HOUR` | Internal Dream run / external reason-lease work admission |

Quotas use `CYBERBRAIN_QUOTA_DB` (default `/data/quotas.sqlite`). Tenant budgets aggregate agents/users; user budgets are partitioned by tenant. Reservations use one SQLite transaction, survive process restarts, and do not partially consume another resource on rejection. No new Qdrant collection is used. Over-budget worker jobs return to pending until the next window without consuming retries or changing evidence.

`CYBERBRAIN_MCP_MAX_SESSIONS` defaults to 256 and `CYBERBRAIN_MCP_MAX_REQUEST_BYTES` to 2097152. The supported MCP SDK owns admission, idle-session cleanup, credential/session matching and body bounds. Numeric telemetry is bounded in memory; scoped metrics report the authorized tenant/user partition only and require review/admin authority.

Compose source loads optional local environment configuration and mounts the server-owned configuration directory read-only. Real configuration and credentials remain deployment-owned.

## Durable Dream scope and upgrade

The queue upgrade replaces session-only uniqueness with session plus normalized identity scope. It preserves old IDs, statuses, attempts, timestamps and errors transactionally. Audit and reason inbox gain credential-free authority snapshots. Existing rows are not retroactively given authenticated ownership.

Worker evidence recall, session loads/status updates, reasoning tasks, audits, reviews and writeback retain the job boundary. A candidate with mixed tenant/user/agent/project evidence is blocked before canonical persistence. Manual review approval requires review and canonical write grants.

Before switching deployment mode, quiesce old workers and finish or explicitly reconcile owner jobs. A broader-mode worker never claims legacy owner jobs or another mode's jobs. The scheduler skips rows lacking required principal dimensions rather than fabricating ownership. Do not interpret a renamed agent string or a migrated historical record as trusted identity.

Schema changes require an offline coordinated backup first. Binary rollback after queue schema upgrade requires restoring the matching old operational database bundle; do not run an older queue implementation against the upgraded composite-key schema.

## Backup and maintenance

Quiesce writers for a coherent deployment backup/restore. The backup CLI includes existing Dream queue, audit, reason inbox and quota SQLite files as well as the two Qdrant collection snapshots. Manifest checksums protect restore. Reason tombstones and consumed quota reservations must survive recovery; restoring only canonical collections is not a complete operational recovery.

Back up principal configuration separately without credential values. Re-provision runtime credentials through the deployment's secret mechanism. Restore/publish/rollout actions require explicit operational authorization.

Review listings use stable keyset cursors. Diagnostics open existing audit data read-only and distinguish repeated content from exact repeated content/evidence. Task retirement remains explicit, dry-run by default, requires independently proven finalized IDs, rejects active leases/recent state, preserves audit/canonical records and leaves replay tombstones. No automatic retirement or VACUUM is enabled.

Compose source enables the scheduler heartbeat writer and its healthcheck. A fresh waiting heartbeat establishes scheduler liveness; `has_completed_run` separately reports whether a successful run has happened. Changing live healthchecks or applying retention is a rollout/maintenance action, not a source-test side effect.

Source correctness is assessed under [SOURCE_ACCEPTANCE.md](SOURCE_ACCEPTANCE.md). Long-term effects are assessed under [LIVE_EVALUATION.md](LIVE_EVALUATION.md).
