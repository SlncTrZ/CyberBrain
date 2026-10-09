# Project Status

Snapshot: 2026-10-09, Asia/Saigon. This is dated evidence, not a live status endpoint.
Use runtime health/readiness probes and the published GitHub release when making operational decisions.

## Source, Release & Runtime Identity

| Layer | Observed state |
| --- | --- |
| Source package | Version authority is `cyberbrain/_version.py`; build metadata, CI, and tags derive from it |
| Working checkout | Docs consolidation (README/PLAN/runtime index); small uncommitted post-release closure edits retained |
| Latest public release | See the repository's GitHub Releases page; do not trust a version literal copied into docs |
| Production corpus | Validated schema-V2 cutover complete; V2 stage tooling remains canonical for future migrations |
| Cognitive path | M3–M7 wired on the normal authenticated recall/store path; M6 fail-closed, M7 event-driven |

Source acceptance, deployment acceptance, and longitudinal live evaluation are separate.
See [Source Acceptance](SOURCE_ACCEPTANCE.md) and [Live Evaluation](LIVE_EVALUATION.md).

## Implemented Source Contract

| Area | Current behavior / boundary |
| --- | --- |
| Authority | `single_owner` default; broader modes require authenticated registry plus complete quotas |
| Recall | Vector default; explicit `literal`/`hybrid` Knowledge opt-ins; compact-first response projection |
| Exact fetch | Scope-safe `knowledge_get` / `memory_get` with indistinguishable absent/out-of-scope behavior |
| Dreaming | Evidence-grounded; MCP-first claim window, then ordered deployer-configured LLM routes |
| Salience (M3) | Active after authorized prefetch; reorders only, never widens eligibility |
| Concepts (M4) | Bounded discovery/stability observation; durable promotion reviewed separately |
| Working Memory (M5) | Transient scope/session/task state; process-memory only, no public tool |
| Self-Model (M6) | Fail-closed until trusted readiness (≥20 resolved outcomes, ≥3 sessions, ≥3 topics, complete scan) |
| Lifecycle (M7) | Reversible event-driven suppression; no bulk sweep, no hard delete |
| Relations | Strict typed assertions with review gates; caller/Dream expansion explicit opt-in |
| Compatibility | Legacy aliases adapt into canonical services; no second business-logic path |

## Remaining Operational Work (F0–F4)

C1–C5 are source-complete. What remains is intentionally operational and evidence-driven:

1. **F0 — Production convergence:** verify the exact deployed source/image fingerprint, provider catalog/contract fingerprint, service health/restarts, backup coverage, and rollback target. A provider version response alone is not an image fingerprint.
2. **F1 — Closed-loop live adoption:** verify supported integrations actually invoke the prospective pre-action/outcome seam. Genuine trusted Prediction/Outcome evidence must grow naturally; the M6 floor above stays in force.
3. **F2 — Dream review debt burn-down:** re-measure backlog size, age, duplicate rate, project distribution, write yield, and block reasons after the review fixes are deployed. Throughput must meet/exceed inflow without mass approval or lowered gates.
4. **F3 — Longitudinal effectiveness:** evaluate M6 calibration/self-model usefulness, M7 false-suppression/reactivation precision, Dream write yield/false promotion, retrieval latency/reliability, typed-relation usefulness, provider reliability, and resource safety on real work. Calendar age alone never passes a gate.
5. **F4 — Product/operations closure:** verify supported clients refresh the current provider catalog, rehearse coordinated backup/restore and rollback, keep documentation/evidence minimal, and close any reproducible deployment or recovery defect.

Global Workspace or additional broad cognitive architecture is not a completion requirement. Add new reasoning architecture only when live evidence identifies a concrete gap that the current Working Memory, typed relations, and bounded reasoning cannot satisfy within acceptable token/latency/complexity budgets.

## Documentation Scope

Current guides are reconciled against the source on 2026-10-09. The [documentation index](README.md)
provides task-oriented navigation; [Source Acceptance](SOURCE_ACCEPTANCE.md) defines the source gate
and [Live Evaluation](LIVE_EVALUATION.md) defines post-deployment review. Historical snapshots in
[history/](history/README.md) retain past behavior and are non-normative.
