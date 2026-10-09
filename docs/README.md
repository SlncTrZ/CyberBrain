# CyberBrain Documentation

Start with the guide for your task. The README introduces the product; the Tool Guide explains
everyday tool use. Specifications define normative contracts without replacing those guides.

| You need to… | Read |
| --- | --- |
| Check source/release/runtime evidence | [Project Status](PROJECT_STATUS.md) |
| Use the MCP tools | [Tool Guide](../TOOL_GUIDE.md) |
| Run or configure the service | [Current Runtime](CURRENT_RUNTIME.md) |
| Configure principals, quotas, backup | [Tenancy Operations](TENANCY_OPERATIONS.md) |
| Configure Dream fallback routes | [Dreaming Routing](DREAMING_ROUTING.md) |
| Pass the source gate | [Source Acceptance](SOURCE_ACCEPTANCE.md) |
| Evaluate live effectiveness | [Live Evaluation](LIVE_EVALUATION.md) |
| Migrate to schema V2 | [V2 Migration Runbook](V2_MIGRATION_RUNBOOK.md) |
| Enable typed relations | [Relation Rollout](RELATION_ROLLOUT.md) |
| Review priorities | [Plan](../PLAN.md) |
| Understand a normative contract | [specs/](../specs/) via the [Plan roadmap](../PLAN.md#cognitive-roadmap) — e.g. [Memory Lifecycle](../specs/MEMORY_LIFECYCLE.md), [Tool Contract](../specs/TOOL_CONTRACT.md) |
| Understand a past migration or release | [history/](history/README.md) |

Current docs were reconciled against the source on 2026-10-09. Specifications in `specs/`
are normative; this index and the guides explain them without replacing them.

Release notes and historical snapshots retain past behavior. A historical file describes what was
true at its date. Current guides identify production state explicitly; a source implementation
or automated test result alone does not establish deployed-runtime behavior.

When current and historical documents differ, current guidance and canonical specs take precedence.
Source acceptance, deployment acceptance, and longitudinal live evaluation are separate.
See [Source Acceptance](SOURCE_ACCEPTANCE.md) and [Live Evaluation](LIVE_EVALUATION.md).
