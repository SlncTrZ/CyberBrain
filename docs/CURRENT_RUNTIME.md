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

The provider exposes:

- HTTP health/readiness endpoints;
- MCP Streamable HTTP at /mcp;
- provider-local tool names.

Network-visible MCP access is authenticated when authentication is enabled.

## Current source integration

Current software and production storage have satisfied the Level-8.0/schema-V2 gates. The normal authenticated MCP recall/store path now actively wires M3–M7 without replacing canonical vector retrieval or widening authorization:

- authenticated MCP requests are bound to explicit `CallerAuthority` in `single_owner` mode. When `CYBERBRAIN_TRUSTED_AGENT_ID` is configured, successful Bearer/X-API-Key authentication also binds `TrustedIdentityEvidence` for that server-configured agent; caller headers/tool arguments cannot create or substitute trusted identity. `agent_ready` and `multi_user` remain fail-closed until broader P3 isolation/persistence requirements are complete;
- canonical `knowledge_get` and `memory_get` perform exact full-record fetch with storage-side ID + scope eligibility;
- `cyberbrain.agent_adapter.MCPAgentClient` bridges the transport-neutral Agent Adapter contract to the canonical MCP Streamable HTTP tools;
- M3 Salience actively scores/reorders the bounded already-authorized vector prefetch;
- M4 Concept Formation actively accumulates bounded same-scope recall/store evidence and runs deterministic discovery/stability observation; it still does not auto-promote candidates to canonical truth.
- M5 Working Memory actively selects exact scope/session/task transient context after relevance + M3 scoring, reserves bounded M4/M6 advisory capacity, and remains process-memory only;
- M6 Agent Self-Model runs after trusted outcome resolution. It remains fail-closed until trusted sample/diversity readiness passes; current policy then automatically applies the accepted review transition and persists only outside ordinary recall;
- M7 Memory Lifecycle is active event-by-event: selected/exact-fetched records record access and may reactivate, while non-selected authorized prefetch candidates may be reversibly suppressed. There is no automatic full-corpus suppression sweep;
- canonical schema V2 is the current production storage format. The full four-source corpus was staged, independently validated, canary-tested, and cut over with point ID/vector/content preservation and one fail-closed quarantined legacy Episode.

The current vector search path is still the canonical retrieval backend. A reviewed 28-case real-current-baseline benchmark rejected always-on global hybrid fusion because the Recall@5 gain came with a small MRR loss and rank regressions. Source includes disabled-by-default shadow instrumentation for the better-performing deterministic literal/fingerprint route. When enabled in `single_owner` mode, literal-heavy Knowledge queries submit a non-blocking BM25 observation over a bounded TTL cache of active Knowledge, with the same explicit equality filters reapplied before lexical scoring. The reusable pre-tokenized BM25 corpus avoids rebuilding document statistics on every shadow query; live observation has cleared the earlier recurring scoring-cost blocker. The caller still receives the unchanged vector result, and lexical promotion remains gated on larger relevance/reliability evidence. The Agent Adapter remains optional foreground convenience for compact context use rather than an owner of background cognition; broader tenancy enforcement over all existing search/write paths remains pending. Release and deployment state remain separate from this source-level contract.

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

Current source canonical payload schema is V2. Knowledge V2 adds `record_class`, explicit identity provenance, and lifecycle metadata; Episodic V2 adds explicit identity provenance, lifecycle metadata, and `updated_at`. Ordinary Knowledge recall requires `status=active`, `record_class=knowledge`, and `ordinary_recall=true`; ordinary Episodic recall requires `ordinary_recall=true`. M6 persisted hypotheses and migration quarantine are therefore excluded from ordinary Knowledge recall, while M7-suppressed records remain stored but hidden from normal semantic recall.

V2 migration remains stage-before-cutover by contract. The migration tooling merges canonical V1 stage records with raw legacy deltas, preserves source point IDs/content/vectors, fingerprints IDs + payloads + vectors to detect concurrent source change, requires exact target-count convergence, marks historical identity as untrusted rather than authenticated, and moves unmappable records into non-recallable migration quarantine instead of fabricating canonical metadata. Independent validation rechecks union equality, target overlap, schema parsing, vector/content fidelity, identity trust, and recall isolation. The current production corpus has completed this procedure and now uses the validated V2 stage pair. `docs/V2_MIGRATION_RUNBOOK.md` remains the canonical procedure for future migrations, catch-up, validation, and rollback.

The current provider retains migration compatibility for rollback and mixed historical fixtures: ordinary Knowledge/Memory recall can still accept canonical V1 rows whose V2-only recall fields are absent, while explicit V2 non-recallable/class-isolation metadata remains authoritative. The production corpus itself is now V2. The MCP tool contract remains backward-compatible and provider help advertises the canonical schema version independently.

## Recall response boundary

Canonical `knowledge_search` and `memory_search` use compact-first MCP response projection. Retrieval and ranking still operate on the canonical stored record; only the returned payload is reduced for broad recall.

- `view=compact` is the default.
- Existing `summary` becomes `recall_text` when present.
- Without a summary, `recall_text` is a bounded content excerpt of at most 1,200 characters.
- Compact rows expose `recall_text_source`, original `content_chars`, and `content_omitted=true` while omitting full `content` and `summary`.
- `view=full` preserves the complete canonical search row for focused follow-up.

This boundary does not mutate Knowledge, Episodic Memory, embeddings, ranking, provenance, or Dreaming evidence. For focused follow-up, `knowledge_get(id)` and `memory_get(id)` return one selected full record without a second semantic search; ID and effective scope are combined at the storage query before payload return. Compatibility aliases retain their legacy response behavior.

## Post-storage cognition boundary

Ordinary `memory_store` writes create canonical Episodes that default to `dream_status=pending`. When the Dreaming profile is active, the server-side scheduler scans pending Episodes, groups them by session, waits for the configured quiet period, and queues eligible sessions automatically. The Dream worker then performs bounded evidence retrieval/reasoning, provenance validation, promotion/review gates, and Knowledge Evolution writeback. A normal external agent does not need to invoke `dream_enqueue` after storing an Episode.

`dream_enqueue` remains an explicit/manual control surface for forcing or narrowing a completed-session Dream run. Prediction Learning remains causally separate: valid prediction evidence must be captured before the outcome is known, so it cannot be reconstructed truthfully as a purely post-storage step.

## Cognitive learning

The first cognitive-learning mechanism stores Prediction and Outcome records inside `cyberbrain_episodic`; it does not create another durable collection.

The provider exposes `prediction_record`, `prediction_resolve`, read-only `prediction_observe`, and read-only `prediction_pending`. Prediction/Outcome metadata is stored under `context.cognition`, and Dreaming can consume it through the existing episodic evidence path. Observation and pending summaries are bounded reads and do not mutate Episodic Memory or Knowledge.

Prediction Learning remains in active observation. The runtime also exposes read-only `calibration_observe` for sample-level confidence calibration analysis. Initial end-to-end MCP gateway validation has exercised record, pending/observation, resolve, and calibration paths successfully. This validation does not replace continued observation or the minimum-evidence gates.

Current runtime actively uses the completed M3 Salience primitives. `SalienceScorer` consumes explicit bounded signals; `salience-policy-v1` prioritizes prediction error, contradiction, and consequence above novelty/recency; `SalienceAdvisor` rejects cross-scope candidate sets; and `SalienceShadowObserver` records metrics without mutating candidate order. These remain internal cognitive primitives rather than new MCP tools. They run only after existing authorization and canonical search eligibility.

Current runtime actively uses the completed M4 Concept Formation primitives as bounded discovery/registry state. The E1 census is read-only and explicitly excludes or requires review for low-quality historical evidence. `ConceptDiscoveryEngine` forms deterministic same-scope candidates only after recurrence and abstraction-breadth gates; `ConceptShadowRegistry` observes identity/support stability in memory; Salience may reprioritize candidates without changing their identity; and `ConceptPromotionGate` can only reject or request review. There is no graph database, third collection, LLM concept synthesizer, or automatic Knowledge write path.

Current runtime actively uses the completed M5 Working Memory primitives on normal recall. `WorkingMemoryService` maintains process-memory state keyed by exact scope/session/task identity, applies explicit task relevance before Salience, suppresses duplicates before token packing, enforces bounded candidate/item/token/TTL limits, and removes state on closeout or expiry. `WorkingMemoryEmissionLedger` suppresses unchanged reinjection for an ongoing consumer context. M5 does not persist its scratch state, add a third canonical collection, or add a public MCP tool. The official Agent Adapter forwards transient session/task hints, while older clients use deterministic server fallbacks without changing storage filters.

Together, M3 + M4 + M5 satisfy the Level-8.0 **source** gate. The deployed application image also contains M6 Agent Self-Model and M7 Memory Lifecycle plus schema-V2 metadata/migration tooling, and the production corpus now uses the validated V2 collections. M6 extracts trusted prospective Prediction/Outcome evidence, gates generation on at least 20 trusted resolved outcomes / 3 sessions / 3 topics / complete scan, generates deterministic bounded hypotheses, requires explicit review, persists accepted-only hypotheses through Knowledge Evolution outside ordinary recall, and can project accepted hypotheses into Working Memory as bounded advisory context. Current historical evidence remains insufficient for M6 influence, so the active trigger correctly returns `insufficient_evidence` until new trusted outcomes accumulate. M7 now actuates progressively on touched/prefetched events only; the earlier metadata-only full-corpus all-stale observation is explicitly not used as a bulk mutation plan.

## Dreaming profile

The optional Docker Compose dreaming profile adds:

- dream-route-reasoner — provider-neutral fallback LLM route service;
- dream-worker — Dream orchestration and writeback worker;
- dream-scheduler — deterministic server-side pending-session enqueue scheduler (nightly by default).

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

## Software version

`cyberbrain/_version.py` is the single software/package version authority. Hatch build metadata, `cyberbrain.__version__`, bundled provider version reporting, CI metadata checks, and expected release tags derive from that value. Contract versions and schema versions remain independent.

## Configuration

The current runtime is configured through environment variables consumed by Pydantic Settings and
through explicit route JSON for Dream fallback providers.

Core environment variables use the CYBERBRAIN_ prefix. `CYBERBRAIN_TRUSTED_AGENT_ID` is optional and only meaningful when MCP authentication is enabled; it binds a trusted agent context after credential verification but does not enable `agent_ready` or `multi_user` deployment modes.

The Dream fallback route service reads either:

- CYBERBRAIN_DREAM_LLM_ROUTES_FILE, or
- CYBERBRAIN_DREAM_LLM_ROUTES_JSON.

Route files contain behavior only. Credentials are referenced by environment-variable name and
remain runtime-only.

## Retrieval shadow instrumentation

The literal/fingerprint shadow observer is optional observation infrastructure and is disabled by default in source configuration. A deployment may enable it without changing caller-visible retrieval.

```text
CYBERBRAIN_RETRIEVAL_LITERAL_SHADOW_ENABLED=false
CYBERBRAIN_RETRIEVAL_LITERAL_SHADOW_CACHE_TTL_SECONDS=300
CYBERBRAIN_RETRIEVAL_LITERAL_SHADOW_MAX_RECORDS=5000
```

When enabled, only `status=active` Knowledge searches with strong deterministic lexical fingerprints are evaluated. The worker does not replace or rerank the caller-visible vector rows. It records numeric counters/timings in the existing authenticated `/metrics` registry and logs only a truncated SHA-256 query fingerprint plus record IDs/rank overlap, never raw query text or stored content.

The cache is bounded and refreshes through payload-only Qdrant scrolls. If the configured record bound is exceeded, the shadow observation fails closed and the canonical vector request remains unaffected. Non-active status searches are skipped rather than evaluated against an incompatible cache.

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
