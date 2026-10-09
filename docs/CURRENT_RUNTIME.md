# CyberBrain Current Runtime

> Status: Current source-level runtime contract.
> Deployment-specific hostnames, ports, provider catalogs, credentials, and topology belong outside
> this repository.

## Runtime boundary

CyberBrain owns its provider-local MCP/API surface, domain logic, post-storage cognition, Dreaming orchestration, storage adapters, and runtime validation. Normal external agents are memory consumers/producers: they recall/get/store through stable interfaces, while CyberBrain owns normalization, evolution, Dream scheduling/processing, promotion, and Knowledge writeback. External gateways or reverse proxies own their own routing, namespacing, lifecycle, and policy.

## Base stack

The default Docker Compose stack contains:

- cyberbrain — API/MCP provider;
- qdrant — canonical Knowledge and Episodic storage;
- embedding — embedding runtime;
- embedding-init — initializes the configured embedding model.

The provider exposes HTTP health/readiness endpoints and MCP Streamable HTTP at /mcp with
provider-local tool names. Network-visible MCP access is authenticated when authentication is enabled.

## Current source integration

Current software and production storage have satisfied the Level-8.0/schema-V2 gates. The normal authenticated MCP recall/store path now actively wires M3–M7 without replacing canonical vector retrieval or widening authorization:

- authenticated requests bind server-owned `CallerAuthority` (`single_owner` default); broader modes require an authenticated principal registry plus every runtime quota limit;
- `knowledge_get` / `memory_get` perform exact full-record fetch with storage-side ID + scope eligibility and indistinguishable absent/out-of-scope behavior;
- M3 Salience scores/reorders the bounded already-authorized vector prefetch;
- M4 Concept Formation accumulates bounded same-scope evidence with deterministic discovery/stability observation and no auto-promotion;
- M5 Working Memory selects exact scope/session/task transient context and remains process-memory only;
- M6 Agent Self-Model runs after trusted outcome resolution and remains fail-closed until readiness passes;
- M7 Memory Lifecycle is active event-by-event with reversible suppression and no full-corpus sweep;
- schema V2 is the production storage format after staged, validated, canary-tested cutover with point ID/vector/content preservation.

Vector is the deliberate default retrieval backend; foreground `literal`/`hybrid` Knowledge modes are explicit deployment opt-ins. Shadow instrumentation is diagnostic only. See [specs/RETRIEVAL_POLICY.md](../specs/RETRIEVAL_POLICY.md) and [specs/COGNITIVE_RUNTIME_PATH.md](../specs/COGNITIVE_RUNTIME_PATH.md).

## Canonical data

CyberBrain uses exactly two durable Qdrant collections:

- cyberbrain_knowledge
- cyberbrain_episodic

Dreaming does not create a third durable collection. Operational Dream state (queue, audit/provenance, reason-task inbox) is stored separately in SQLite files.

Knowledge Evolution may use a shared filesystem lock for single-host cross-process serialization.

Schema V2 adds Knowledge `record_class`, explicit identity provenance, and lifecycle metadata. Ordinary Knowledge recall requires `status=active`, `record_class=knowledge`, and `ordinary_recall=true`; ordinary Episodic recall requires `ordinary_recall=true`. V2 migration remains stage-before-cutover by contract; see [V2 Migration Runbook](V2_MIGRATION_RUNBOOK.md).

## Recall response boundary

Canonical `knowledge_search` and `memory_search` use compact-first MCP response projection. Retrieval and ranking still operate on the canonical stored record; only the returned payload is reduced for broad recall.

- `view=compact` is the default: existing `summary` becomes `recall_text`, otherwise a bounded content excerpt of at most 1,200 characters.
- Compact rows expose `recall_text_source`, original `content_chars`, and `content_omitted=true`.
- `view=full` preserves the complete row; `knowledge_get(id)` / `memory_get(id)` return one selected full record without a second semantic search.

Compatibility aliases retain their legacy response behavior. This boundary mutates nothing stored.

## Post-storage cognition boundary

Ordinary `memory_store` writes create canonical Episodes defaulting to `dream_status=pending`. When the Dreaming profile is active, the server-side scheduler groups pending Episodes by session, waits for the configured quiet period, and queues eligible sessions automatically. A normal external agent does not invoke `dream_enqueue` after storing an Episode; it remains an explicit/manual control surface. Prediction evidence must be captured before the outcome is known and cannot be reconstructed purely post-storage.

## Dreaming profile

The optional Docker Compose dreaming profile adds the provider-neutral fallback LLM route service, the Dream orchestration/worker, and the deterministic pending-session scheduler (nightly by default). The worker prepares the whole bounded run first, registers it atomically, and gives external MCP consumers one common run-level claim/submit window; only unfinished tasks continue to configured fallback routes. See [Dreaming Routing](DREAMING_ROUTING.md).

## Configuration

The runtime is configured through `CYBERBRAIN_`-prefixed environment variables (Pydantic Settings) and explicit route JSON for Dream fallback providers. Route files contain behavior only; credentials are referenced by environment-variable name and remain runtime-only.

Search thresholds, Dream budgets, scheduler timing, provider/model order, timeouts, and retry/cooldown settings are runtime policy. They may change without altering canonical contracts.

## Health and readiness

- /health is process liveness.
- /ready checks required runtime dependencies and must fail when canonical storage or embedding dependencies are unavailable.
- Dream worker and route-service health checks are process/service checks appropriate to their roles.

## Operations maintenance

- `dream_reviews` supports bounded keyset pagination via `review_cursor`.
- `review_backlog` diagnostics open the audit database read-only; they approve, delete, or promote nothing.
- Reason-inbox retirement is explicit owner maintenance, dry-run by default, with replay tombstones.
- Scheduler heartbeat is opt-in; deployment owners must mount the heartbeat path for the healthcheck.

## Historical runtime evidence

Deployment-specific migration, cutover, acceptance-window, staged-collection, and rollback
snapshots are preserved under history/. They are historical evidence, not current operating
instructions.
