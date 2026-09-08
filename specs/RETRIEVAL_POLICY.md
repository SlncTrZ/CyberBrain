# Retrieval Policy v1

## Goals

Retrieval must return useful, context-aware, semantically relevant records while preserving lifecycle and evidence semantics.

## Search stages

```text
query validation
→ embedding
→ collection selection
→ metadata filtering
→ vector retrieval
→ lifecycle filtering
→ ranking
→ result normalization
→ response projection when exposed through MCP
```

## Collection selection

- Knowledge queries default to `cyberbrain_knowledge`.
- Episodic/session queries default to `cyberbrain_episodic`.
- Cross-brain search must be explicit in the internal API even if a compatibility tool aggregates both.

## Lifecycle filtering

Canonical knowledge search defaults to:

```text
status = active
```

Historical/timeline operations may include superseded/deprecated/rejected records explicitly.

Negative knowledge must be labelled in results and must not be ranked as a positive recommendation without context.

## Metadata filters

V1 supports explicit filters for fields with clear use cases:

Knowledge:

```text
domain
topic
entity_type
entity_name
project
status
verification
origin
negative_knowledge
```

Episodic:

```text
session_id
channel
role
agent
project
topic
event_time range
dream_status
```

## Score handling

The provider must not use a collection-size side effect to globally disable score thresholds.

Thresholds are policy/config values scoped to the retrieval mode.

Search results must expose similarity score when available, but similarity score is not equivalent to truth/confidence.

## Hybrid evolution and current source status

The canonical runtime search path currently remains vector retrieval plus metadata/lifecycle filtering. The public domain contract should allow implementation to evolve toward:

```text
vector + lexical + metadata + deterministic fusion + optional bounded reranking
```

without changing canonical result semantics.

`main` now contains `cyberbrain.retrieval` benchmark/fusion infrastructure with dependency-free BM25 scoring, deterministic reciprocal-rank fusion, strict scope/status/temporal eligibility helpers, and a reproducible real-snapshot benchmark harness. The real-current-baseline gate has been run on 28 reviewed Knowledge cases using live current-vector rankings plus a read-only active/superseded corpus snapshot.

Observed benchmark decision:

- vector baseline: Recall@5 0.964286, MRR@5 0.898810;
- always-on hybrid RRF: Recall@5 1.000000, MRR@5 0.892857, with two rank regressions;
- deterministic literal/fingerprint router (lexical only for strong commit/version/model/port-style lexical signals, vector otherwise): Recall@5 1.000000, MRR@5 0.934524, no observed rank regressions in the reviewed set, and lower mean returned-token estimate than vector.

Therefore always-on hybrid fusion is **not promoted**. The literal/fingerprint route remains **SHADOW ONLY**: live observation has cleared the recurring shadow-scoring performance blocker, but caller-visible promotion still requires a larger reviewed relevance/reliability sample with zero scope leakage and no material reliability regression. The canonical Knowledge/Memory search backend remains vector retrieval.

### Literal/fingerprint shadow contract

Source `main` includes disabled-by-default shadow instrumentation for Knowledge search. Deployments may enable it for observation, but it remains caller-invisible:

```text
literal-heavy query detected
→ canonical vector search completes normally
→ caller-visible vector rows remain unchanged
→ non-blocking shadow worker evaluates BM25
→ numeric metrics + content-free query/record fingerprints only
```

The observer uses a bounded TTL cache of `status=active` Knowledge payloads plus a reusable pre-tokenized BM25 corpus and reapplies the same explicit equality filters before scoring. Missing metadata is ineligible. Non-active status searches are skipped. Cache overflow, storage errors, worker contention, or any other shadow failure must not alter or fail the canonical vector response.

The existing metrics registry records shadow detection/evaluation/failure counts, cache refresh/size, worker-busy skips, top-1 agreement/change counts, overlap@K, vector-top1 lexical rank, compact-token estimates, and shadow/cache timings. Raw query text and stored content are not metrics labels or log fields; logs use a truncated SHA-256 query fingerprint and record IDs only.

Authorization/scope eligibility must be applied before candidate data can become visible to fusion, response projection, or agent context packing. Missing metadata does not satisfy an explicit project/topic/entity/status filter. Ranking metadata must never substitute for hard authorization filters.

Salience is not part of canonical retrieval ranking in the current source contract. Future use must happen only after authorization/data eligibility, through the bounded Salience advisory contract in `SALIENCE.md`; a Salience score can prioritize an already-eligible candidate but cannot create retrieval eligibility or override a hard filter.

## Temporal recall for Dreaming

Dreaming does not issue one undifferentiated semantic query over all history.

It queries normalized time buckets deliberately from older to newer evidence, then merges/reranks while retaining bucket provenance.

## MCP response projection

Canonical storage and internal retrieval retain the complete normalized record. Canonical MCP `knowledge_search` and `memory_search` apply a response projection after ranking so broad recall does not automatically return large payloads.

`view=compact` is the default MCP view:

```text
summary present    -> recall_text = summary
summary absent     -> recall_text = content excerpt, max 1,200 characters
```

Compact rows omit full `content` and `summary`, retain relevant metadata/score, and add:

```text
recall_text
recall_text_source = summary | content_excerpt
content_chars
content_omitted = true
```

`view=full` returns the complete canonical normalized search row and is intended for focused follow-up when full detail is actually required. Projection occurs after retrieval/ranking and therefore must not alter embeddings, similarity score, lifecycle filtering, evidence provenance, or stored records.

Legacy compatibility aliases may retain historical full-payload behavior; they do not define the canonical retrieval contract.

## Failure behavior

Embedding failure must surface explicitly. Do not substitute a zero vector.

Storage/provider failure must return an explicit retrieval error rather than silently returning an empty result set indistinguishable from a true no-match.

## Result model

The canonical normalized retrieval row should include:

```text
id
record_type
content
summary
score
relevant metadata
status/version when knowledge
event_time/session_id when episodic
verification/confidence when available
negative_knowledge flag when applicable
```

MCP compact projection derives from this complete row and must preserve the row identity, score, and relevant metadata while replacing large text fields with the bounded recall fields defined above.
