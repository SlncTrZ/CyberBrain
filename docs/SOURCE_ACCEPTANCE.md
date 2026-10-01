# Source acceptance

Source acceptance evaluates implemented contracts and reproducible engineering behavior. It is independent of deployment age, production outcome counts, and long-term usefulness.

| Gate | Required source evidence |
| --- | --- |
| Canonical correctness | Knowledge/Episode schema, evolution, provenance, versioning, and migration safety tests |
| Foreground isolation | Operation grants, concrete attribution, scoped search/timeline/exact get, indistinguishable absent/foreign IDs |
| Cognitive integration | Bounded authorized M3–M7 path, transient context separation, prospective M6 readiness, reversible M7 |
| Durable background isolation | Identity-partitioned queue; restored worker scope; scoped evidence, session updates, audit, review and reason leases |
| Principal boundary | Server-owned registry, credential verification, operation grants, SDK session ownership |
| Resource safety | Atomic persisted tenant/user quotas, deferred background work, SDK body/session bounds, bounded numeric telemetry |
| Operations | Stable review pagination, read-only diagnostics, explicit retirement/tombstones, scheduler heartbeat, redacted transport errors |
| Recovery and packaging | SQLite backup/restore including reason inbox and quotas; wheel/sdist privacy; clean Docker build; Compose validation |
| Typed relations | Scoped endpoint/proof validation, reviewed assertions, version/time paths, whole-path budgets, real backfill/vector preservation and isolated restore/reapply |
| Documentation | Current source contract and upgrade path agree with code; live evaluation kept separately |

Run the default tests and lint/diff checks, build wheel and sdist, inspect distribution manifests, and build the Docker image. Real-storage isolation has an optional test in `tests/tenancy/test_qdrant_isolation.py`: it requires an explicitly supplied new empty loopback Qdrant endpoint, checks that the instance is empty before writing, and creates only the two canonical collections. It must never target an existing deployment.

Use an isolated QA image/container or disposable environment for packaging and protocol checks. No source test needs production credentials, canonical corpus mutation, manual production review resolution, or retrospective Prediction fabrication.

A source pass permits engineering review; publishing, production rollout, and broader-mode configuration remain explicit deployment decisions. Production smoke/rollback acceptance is recorded separately from longitudinal effectiveness. See [tenancy operations](TENANCY_OPERATIONS.md) and [live evaluation](LIVE_EVALUATION.md).
