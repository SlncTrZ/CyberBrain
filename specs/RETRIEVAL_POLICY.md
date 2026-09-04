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

## Hybrid future compatibility

The public domain contract should allow implementation to evolve from pure vector retrieval to:

```text
vector + lexical + metadata + reranking
```

without changing canonical result semantics.

## Temporal recall for Dreaming

Dreaming does not issue one undifferentiated semantic query over all history.

It queries normalized time buckets deliberately from older to newer evidence, then merges/reranks while retaining bucket provenance.

## Failure behavior

Embedding failure must surface explicitly. Do not substitute a zero vector.

Storage/provider failure must return an explicit retrieval error rather than silently returning an empty result set indistinguishable from a true no-match.

## Result model

Canonical retrieval results should include:

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
