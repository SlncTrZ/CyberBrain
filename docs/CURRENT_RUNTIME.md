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
