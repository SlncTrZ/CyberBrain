# MeiLin → CyberBrain Migration Plan

> Historical document. Historical migration plan retained for provenance. The staged migration and CyberBrain V1 cutover described here have already been completed; future-tense steps are not current operating instructions.

> Status: Phase 0 draft based on active runtime/data audit
> Principle: no big-bang rewrite, no destructive in-place migration first

## 1. Objectives

Migrate the generic CyberBrain capability out of the active MeiLin MCP deployment while preserving:

- current two-collection production data
- SlncTrZ-MCP compatibility
- Streamable HTTP `/mcp`
- authenticated provider access
- existing tool semantics where compatibility matters
- rollback at every production cutover step

At the end:

```text
MeiLin = persona/client/orchestration
CyberBrain = shared knowledge + memory infrastructure
```

## 2. Migration constraints discovered

### Heterogeneous production payloads

`cyberbrain_knowledge` contains a large historical base schema plus a smaller evolution schema.

`cyberbrain_episodic` also mixes legacy and newer payload shapes and timestamp types.

CyberBrain must normalize reads before any large-scale backfill.

### Knowledge Evolution is not reliable enough to copy directly

Current code intends to deprecate previous active versions but does not preserve point IDs from search results. Production contains multiple active versions for some entity groups.

CyberBrain must establish and test the one-active-version invariant before enabling canonical evolution writes.

### Tool schemas and behavior have mismatches

Known mismatches include:

- `tech_find.wing` advertised but ignored
- `conversation_recall.channel` advertised but ignored
- timeline `source_file` filter does not match current `source` payload field
- conversation channel/role may be nested and unavailable through normalized search output

Compatibility behavior must be explicit rather than accidentally inherited.

### Current embedding failures silently become zero vectors

CyberBrain must not migrate this behavior as-is.

### Authentication should be tightened

Preserve Bearer/API-key mechanics, but production policy should fail closed when required authentication is not configured.

## 3. Migration strategy

```text
read compatibility first
→ canonical model
→ tested new writes
→ shadow comparison
→ gateway cutover
→ incremental backfill
→ retire MeiLin-owned server
```

## 4. Stage A — Freeze canonical contracts

Before implementation finalize:

```text
specs/KNOWLEDGE_SCHEMA.md
specs/MEMORY_SCHEMA.md
specs/EVOLUTION_SPEC.md
specs/RETRIEVAL_POLICY.md
specs/TOOL_CONTRACT.md
specs/SECURITY.md
specs/DREAMING_SPEC.md
```

The spec must define how historical payloads map into the canonical model.

## 5. Stage B — Build compatibility readers

Implement Qdrant repositories that return a canonical model while preserving raw/extension metadata.

Example:

```text
Qdrant legacy/new payload
        ↓
PayloadNormalizer
        ↓
CanonicalKnowledge / CanonicalEpisode
```

Initial migration should not require rewriting production records.

### Required normalization

- missing status → legacy-active/compatible interpretation defined by spec
- missing version → canonical legacy version semantics
- mixed timestamp forms → canonical event time
- top-level/nested conversation metadata → unified accessors
- `source_file` legacy alias → canonical `source`
- unknown metadata → preserved extension payload

## 6. Stage C — Build storage and embedding adapters

Interfaces:

```text
KnowledgeRepository
MemoryRepository
EmbeddingProvider
```

Initial adapters:

```text
QdrantRepository
OllamaEmbeddingProvider
```

Do not expose Qdrant/Ollama details throughout domain logic.

Embedding failures for durable writes must return explicit errors; do not write zero-vector substitutes.

## 7. Stage D — Rebuild Knowledge Evolution correctly

Define entity identity and version state before implementing writes.

Required invariant after a successful evolution transaction:

```text
one canonical active version per entity identity
```

Preserve historical/rejected/superseded versions.

The write path must know concrete Qdrant point IDs or use appropriate payload-filter update APIs with tested semantics.

Tests must cover:

- first insert
- same entity new version
- concurrent/equivalent updates
- failure before new write
- failure after new write but before supersession
- rollback/idempotency strategy
- existing duplicate-active repair policy

Do not auto-repair current production duplicates until the migration policy is approved.

## 8. Stage E — Implement CyberBrain provider shell

Use the shared `MCP_PROVIDER_STANDARD.md`.

Required:

```text
/mcp
Bearer auth
optional X-API-Key compatibility
cyberbrain.help
contract fingerprint/version
healthcheck
bounded timeouts
```

CyberBrain provider should initially point at the same compatible data services only in controlled staging/shadow mode.

## 9. Stage F — Tool contract migration

Canonical target tools:

```text
cyberbrain.help
cyberbrain.knowledge_search
cyberbrain.knowledge_store
cyberbrain.knowledge_timeline
cyberbrain.memory_search
cyberbrain.memory_store
```

Legacy aliases may temporarily map:

```text
tech_find
tech_store
ai_memory_read
conversation_recall
conversation_save
```

Alias behavior must be tested against current clients.

Do not perpetuate known contract bugs merely for compatibility; if a parameter was advertised but ignored, document and deliberately fix it in the canonical CyberBrain tool.

## 10. Stage G — Shadow read comparison

Before writes/cutover, run representative search/recall queries against:

```text
current MeiLin
vs
CyberBrain compatibility reader
```

Compare:

- top results
- score/ranking changes
- metadata normalization
- legacy point visibility
- episodic recall
- latency
- no-result behavior

Differences must be explained rather than blindly forced to match bugs.

## 11. Stage H — Controlled write validation

Use isolated test entities/session IDs or a staging collection copy/snapshot if available.

Validate:

- canonical payload
- embedding dimensions/model metadata
- search visibility
- version progression
- supersession
- timeline
- episodic timestamps/session metadata
- secret rejection

Production MeiLin remains unchanged during this stage.

## 12. Stage I — Dreaming dry-run

Dreaming starts as read-only/dry-run.

Pipeline:

```text
session/topic selection
→ normalized temporal recall
→ candidate reasoning/consolidation
→ proposed mutations
→ no write
```

Measure whether candidates correctly preserve:

- final decisions
- failed approaches and reasons
- contradictions
- context-dependent alternatives
- historical evidence

Only after quality/evidence policy is validated may Dreaming write canonical evolution.

## 13. Stage J — Gateway cutover

Register CyberBrain as a provider in SlncTrZ-MCP without immediately deleting MeiLin.

Preferred sequence:

```text
MeiLin provider active
+ CyberBrain provider staging
→ verify provider catalog/auth/help
→ client tests
→ switch intended consumers to cyberbrain.*
→ retain MeiLin rollback window
```

Do not mutate gateway owner-managed provider configuration silently; use the approved owner workflow.

## 14. Stage K — Incremental data backfill

After canonical compatibility is stable, optionally backfill historical data in bounded batches.

Backfill should add normalized metadata/schema markers without destroying unknown fields.

Requirements:

- snapshot/backup first
- idempotent batch markers
- resumable progress
- before/after counts
- validation sampling
- rollback or reconstructability

A compatibility read layer can remain indefinitely if rewriting old records provides little value.

## 15. Stage L — Duplicate-active reconciliation

Current production has duplicate-active evolution groups.

Do not resolve these using version number alone.

Reconciliation should inspect:

- timestamps
- content relationship
- explicit change reasons
- user-confirmed decisions
- actual implementation/deployment evidence

Possible outcomes:

```text
newest supersedes old
context-dependent split
multiple legacy records merged into one canonical entry
manual review required
```

This is a natural early use case for evidence-gated Dreaming, but initial remediation should be dry-run/manual-reviewed.

## 16. Stage M — MeiLin decoupling

Once CyberBrain is production-stable:

- MeiLin no longer owns the KB runtime
- MeiLin consumes CyberBrain tools
- MeiLin-specific persona/agent behavior stays outside CyberBrain core
- legacy MeiLin MCP server can be retired after the rollback window

## 17. Rollback strategy

At all times preserve:

- Qdrant snapshot/backup
- current MeiLin image/source
- current provider configuration
- old client aliases during transition

Gateway cutover must be reversible without rewriting data.

## 18. Migration acceptance criteria

Migration is ready for production cutover when:

- two current collections are readable through canonical normalizers
- representative legacy/new payloads map correctly
- embedding failures cannot silently corrupt new writes
- Knowledge Evolution one-active-version invariant is tested
- timeline/filter semantics are consistent with canonical schema
- conversation channel/session/time metadata is queryable correctly
- CyberBrain `/mcp` auth passes provider-standard tests
- `cyberbrain.help` reflects runtime contract
- shadow search/recall differences are understood
- Dreaming remains dry-run until evidence policy is approved
- backup/restore path is proven
- rollback is documented and tested

## 19. Immediate implementation order

```text
1. finalize canonical schemas
2. implement payload normalizers
3. implement Qdrant/embedding adapters
4. implement corrected Knowledge Evolution
5. implement CyberBrain MCP/provider shell + help
6. implement search/memory canonical tools
7. shadow compare
8. Dreaming dry-run prototype
9. controlled cutover
10. optional backfill/reconciliation
```
