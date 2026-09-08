# CyberBrain Current Runtime

> Status: Current source-level runtime contract.
> Deployment-specific hostnames, ports, provider catalogs, credentials, and topology belong outside
> this repository.

## Runtime boundary

CyberBrain owns its provider-local MCP/API surface, domain logic, Dreaming orchestration, storage
adapters, and runtime validation. External gateways or reverse proxies own their own routing,
namespacing, lifecycle, and policy.

## Base stack

The default Docker Compose stack contains:

- cyberbrain — API/MCP provider;
- qdrant — canonical Knowledge and Episodic storage;
- embedding — embedding runtime;
- embedding-init — initializes the configured embedding model.

The provider exposes:

- HTTP health/readiness endpoints;
- MCP Streamable HTTP at /mcp;
- provider-local tool names.

Network-visible MCP access is authenticated when authentication is enabled.

## Unwired source foundations

The current source tree also contains `cyberbrain.agent_adapter`, `cyberbrain.retrieval`, and `cyberbrain.tenancy` foundation packages. They are not yet connected to the runtime paths described in this document. In particular, the current provider does not yet expose canonical exact get-by-ID tools, does not yet replace vector search with the Wave 1 hybrid engine, and does not yet enforce the new tenancy scope model in MCP/API/storage paths.

Those capabilities become part of this runtime contract only after explicit Wave 2 integration, end-to-end authorization/regression testing, tool/spec updates where required, and a later release/deployment decision.

## Canonical data

CyberBrain uses exactly two durable Qdrant collections:

- cyberbrain_knowledge
- cyberbrain_episodic

Dreaming does not create a third durable collection.

Operational Dream state is stored separately in SQLite files, including:

- Dream queue state;
- Dream audit/provenance state;
- Dream reason-task inbox state.

Knowledge Evolution may use a shared filesystem lock for single-host cross-process serialization.

## Recall response boundary

Canonical `knowledge_search` and `memory_search` use compact-first MCP response projection. Retrieval and ranking still operate on the canonical stored record; only the returned payload is reduced for broad recall.

- `view=compact` is the default.
- Existing `summary` becomes `recall_text` when present.
- Without a summary, `recall_text` is a bounded content excerpt of at most 1,200 characters.
- Compact rows expose `recall_text_source`, original `content_chars`, and `content_omitted=true` while omitting full `content` and `summary`.
- `view=full` preserves the complete canonical search row for focused follow-up.

This boundary does not mutate Knowledge, Episodic Memory, embeddings, ranking, provenance, or Dreaming evidence. Compatibility aliases retain their legacy response behavior.

## Cognitive learning

The first cognitive-learning mechanism stores Prediction and Outcome records inside `cyberbrain_episodic`; it does not create another durable collection.

The provider exposes `prediction_record`, `prediction_resolve`, read-only `prediction_observe`, and read-only `prediction_pending`. Prediction/Outcome metadata is stored under `context.cognition`, and Dreaming can consume it through the existing episodic evidence path. Observation and pending summaries are bounded reads and do not mutate Episodic Memory or Knowledge.

Prediction Learning remains in active observation. The runtime also exposes read-only `calibration_observe` for sample-level confidence calibration analysis. Initial end-to-end MCP gateway validation has exercised record, pending/observation, resolve, and calibration paths successfully. This validation does not replace continued observation or the minimum-evidence gates.

## Dreaming profile

The optional Docker Compose dreaming profile adds:

- dream-route-reasoner — provider-neutral fallback LLM route service;
- dream-worker — Dream orchestration and writeback worker;
- dream-scheduler — deterministic nightly enqueue scheduler.

The Dream worker prepares the whole bounded reasoning run first, registers it atomically, and gives
external MCP consumers one common run-level claim/submit window.

Only unfinished tasks continue to the configured fallback Reasoner endpoint.

Fallback routing is fully deployment-configured:

    provider 1: model 1A → model 1B → ...
    provider 2: model 2A → model 2B → ...
    ...

CyberBrain does not hard-code provider names, model catalogs, commercial policy, or an external
routing product. See docs/DREAMING_ROUTING.md.

Dreaming V1 historical replay has passed its acceptance gate. Long session and historical records
are reduced to bounded focal evidence, temporal recall remains anchored to the session end, and
Dream outputs remain subject to the existing review/promotion boundary. Further bulk replay,
re-dream semantics, candidate compression, and richer observability are deferred improvements rather
than V1 acceptance requirements.

## Configuration

The current runtime is configured through environment variables consumed by Pydantic Settings and
through explicit route JSON for Dream fallback providers.

Core environment variables use the CYBERBRAIN_ prefix.

The Dream fallback route service reads either:

- CYBERBRAIN_DREAM_LLM_ROUTES_FILE, or
- CYBERBRAIN_DREAM_LLM_ROUTES_JSON.

Route files contain behavior only. Credentials are referenced by environment-variable name and
remain runtime-only.

## Health and readiness

/health is process liveness.

/ready checks required runtime dependencies and must fail when canonical storage or embedding
dependencies are unavailable.

Dream worker and route-service health checks are process/service checks appropriate to their roles.

## Ownership of tuning

Search thresholds, Dream budgets, scheduler timing, provider/model order, protocol order, timeouts,
and retry/cooldown settings are runtime policy.

They may change without altering CyberBrain's canonical Knowledge/Memory/Dreaming contracts.

## Historical runtime evidence

Deployment-specific migration, cutover, acceptance-window, staged-collection, and rollback
snapshots are preserved under docs/history/. They are historical evidence, not current operating
instructions.
