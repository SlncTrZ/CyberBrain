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

The default runtime search path remains vector retrieval plus metadata/lifecycle filtering. Foreground Knowledge retrieval additionally supports opt-in literal routing and hybrid fusion. The public domain contract should allow implementation to evolve toward:

```text
vector + lexical + metadata + deterministic fusion + optional bounded reranking
```

without changing canonical result semantics.

`main` now contains `cyberbrain.retrieval` benchmark/fusion infrastructure with dependency-free BM25 scoring, deterministic reciprocal-rank fusion, strict scope/status/temporal eligibility helpers, and a reproducible real-snapshot benchmark harness. The real-current-baseline gate has been run on 28 reviewed Knowledge cases using live current-vector rankings plus a read-only active/superseded corpus snapshot.

Observed benchmark decision:

- vector baseline: Recall@5 0.964286, MRR@5 0.898810;
- always-on hybrid RRF: Recall@5 1.000000, MRR@5 0.892857, with two rank regressions;
- deterministic literal/fingerprint router (lexical only for strong commit/version/model/port-style lexical signals, vector otherwise): Recall@5 1.000000, MRR@5 0.934524, no observed rank regressions in the reviewed set, and lower mean returned-token estimate than vector.

Therefore always-on hybrid fusion is **not promoted**. The literal/fingerprint route remains **SHADOW ONLY**: live observation has cleared the recurring shadow-scoring performance blocker, but caller-visible promotion still requires a larger reviewed relevance/reliability sample with zero scope leakage and no material reliability regression. The default Knowledge/Memory search backend remains vector retrieval. Source now supports explicit foreground Knowledge modes for controlled evaluation; this does not promote always-on fusion as the production default.

### Foreground Knowledge modes

`CYBERBRAIN_KNOWLEDGE_RETRIEVAL_MODE` selects:
- `vector` (default): existing semantic results and thresholds.
- `literal`: deterministic fingerprint queries use positive-overlap BM25 candidates first, then semantic candidates to fill remaining slots; ordinary queries retain the vector path.
- `hybrid`: semantic candidates and positive-overlap BM25 candidates are fused using existing deterministic reciprocal-rank fusion.

These modes are wired into canonical `knowledge_search` and aliases that invoke the same service. `memory_search`, conversation routing, exact reads, timelines and Dream evidence retrieval keep their existing semantics. Caller arguments cannot change the configured mode.

Both channels use the identical storage-side status, ordinary-recall, record-class, explicit selector and principal scope filters. The lexical corpus is fresh per query and contains only storage-admitted records; no shared cross-principal corpus/cache contributes document statistics. Selected IDs are fetched again through the same filter before response projection, so superseded/deleted/out-of-scope records cannot reenter from the earlier scan.

`CYBERBRAIN_KNOWLEDGE_RETRIEVAL_MAX_RECORDS` defaults to 10000, valid range 1–50000. A scoped corpus exceeding the bound produces an explicit storage error, never a silently truncated BM25 ranking. Candidate multiplier defaults to 3, range 1–10; candidate expansion caps at 500 unless the internal requested recall budget already exceeds 500. This bounded scan implementation incurs tokenization and storage reads per lexical request; it is not a sparse-index scalability claim.

`score` remains the semantic similarity score when present and is null for lexical-only rows. `_retrieval.method`, `_retrieval.ranking_score` and `_retrieval.lexical_score` expose the configured route, RRF score (hybrid only), and BM25 score respectively. BM25/RRF scores are not confidence, truth, or cosine similarity. Embedding/search/scan failures surface explicitly. Compact projection preserves these fields.

Source correctness can be verified in controlled tests immediately. Selecting a new production default still requires a larger reviewed relevance/reliability benchmark; longitudinal learning evidence remains a separate evaluation.

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

The same rule applies when retrieval output later feeds M5 Working Memory: task relevance, Salience, duplicate suppression, and token packing operate only on candidates already admitted by hard authorization/data eligibility. Working Memory does not make retrieval broader and is not part of the caller-visible search contract; any runtime integration remains separately gated.

During the schema-V1 → schema-V2 migration window, ordinary recall remains backward-compatible with canonical V1 stage rows that legitimately lack V2-only `record_class` / `ordinary_recall` fields. Missing fields may satisfy the legacy compatibility branch, but explicit V2 values remain authoritative: non-`knowledge` Knowledge classes and `ordinary_recall=false` are excluded. This compatibility rule allows the current software release to run safely before and after staged corpus migration without changing tool semantics.

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
