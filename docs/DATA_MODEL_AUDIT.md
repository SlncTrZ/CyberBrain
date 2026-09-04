# CyberBrain Data Model Audit

> Historical document. Historical pre-migration production data audit retained as migration evidence. Do not treat counts or schema defects here as the current CyberBrain V1 runtime state.

> Source: active production Qdrant used by MeiLin
> Audit mode: read-only

## Collections

Production currently uses exactly two collections:

```text
cyberbrain_knowledge
cyberbrain_episodic
```

Both collections use:

```text
vector size: 768
distance: Cosine
```

No explicit Qdrant payload indexes were reported in the collection metadata (`payload_schema` was empty for both collections at audit time).

## Point counts

```text
cyberbrain_knowledge: 4861
cyberbrain_episodic:   151
```

## Knowledge collection schema reality

The collection is heterogeneous.

Observed families across all 4861 points:

```text
base_v1 only:        4534
evolution metadata:   327
```

### Base schema

The dominant historical schema contains at least:

```text
content
domain
project
source
```

Most of these older points do not contain:

```text
status
version
topic
entity_name
entity_type
importance
summary
change_reason
timestamp
```

Observed status distribution:

```text
status missing: 4534
active:          327
```

Observed version distribution:

```text
version missing: 4534
v1:               310
v2:                13
v3:                 1
v4:                 1
v5:                 1
v6:                 1
```

Observed timestamp representation:

```text
missing/null: 4524
ISO/string:     337
```

### Evolution schema

Newer points may contain:

```text
content
domain
project
source
wing
topic
entity_name
entity_type
version
status
timestamp
summary
change_reason
importance
extra_metadata (optional)
```

### Additional historical fields

Some existing knowledge points contain research-oriented metadata such as:

```text
query
queries
search_date
sources
```

CyberBrain migration must preserve unknown/extension metadata rather than destructively dropping it.

## Knowledge Evolution data quality

There are currently multiple groups where more than one point with the same `(topic, entity_name)` is still marked `active`.

Observed:

```text
active duplicate entity groups: 12
maximum active points in one group: 6
```

This is inconsistent with the intended invariant that one canonical active version supersedes previous active versions.

This runtime evidence matches the code-level defect where search results omit Qdrant point IDs needed by the existing soft-delete loop.

CyberBrain must treat current status/version metadata as migration input, not as fully trustworthy canonical truth.

## Episodic collection schema reality

Total points:

```text
151
```

Observed schema families:

```text
evolution-style: 96
other/legacy:    55
```

Status:

```text
active:          96
status missing:  55
```

Version:

```text
v1:              96
version missing: 55
```

Timestamp representation is mixed:

```text
integer: 142
string:    9
```

This must be normalized before Dreaming can perform reliable temporal recall.

## Episodic fields observed

Across the collection, payloads may contain:

```text
content
agent_name
project
session_id
timestamp
channel
date
session_start
message_count
summary
entity_type
entity_name
importance
change_reason
status
version
wing
topic
domain
source
extra_metadata
```

Not all fields exist on all points.

### Current write path

The current `conversation_save` path calls `process_atom()` with:

```text
wing = conversation
topic = chat_history
entity_type = message
entity_name = session_id or generated message ID
```

The processor promotes these fields to top level for episodic payloads:

```text
agent_name
session_id
```

Other supplied conversation attributes such as:

```text
channel
role
extra millisecond timestamp
```

remain nested under `extra_metadata` in the newer write path.

This differs from older episodic records where fields such as `channel` can exist at top level.

## Dreaming implications

Dreaming cannot assume a single timestamp type or a single session schema.

Before temporal recall, CyberBrain needs a normalization layer that can derive a canonical event time from legacy/new payloads, likely using a precedence strategy such as:

```text
canonical timestamp
← normalized ISO timestamp
← millisecond epoch timestamp
← session_start/date fallback
← migration-derived timestamp if evidence exists
```

The exact precedence must be specified and tested against real data before migration.

Dreaming also needs a canonical accessor for:

```text
session_id
channel
role
agent
project
topic/entity
event_time
```

regardless of whether legacy payloads stored those fields top-level or nested.

## Qdrant indexes

At audit time Qdrant reported no explicit payload schema/index declarations for either collection.

CyberBrain should introduce indexes deliberately based on actual query paths, especially likely filters such as:

```text
status
domain
topic
entity_name
session_id
channel
event_time
```

Do not add indexes before measuring/search-contract design; each index should correspond to a real retrieval/filter requirement.

## Migration principle

Do not rewrite all 5012 existing points in-place as the first migration step.

CyberBrain should initially support a compatibility read layer:

```text
legacy payload
   ↓
normalizer
   ↓
canonical CyberBrain model
```

New writes can use the canonical schema immediately.

Historical data can then be backfilled incrementally and reversibly after compatibility behavior is verified.

## Required canonicalization work

Before production cutover define:

- canonical timestamp type
- canonical `source` semantics
- canonical status lifecycle
- canonical entity identity
- canonical session identity
- extension metadata policy
- legacy top-level vs `extra_metadata` merge rules
- one-active-version invariant
- embedding metadata/version fields
- migration marker/schema version

## Audit conclusion

The two-collection design is viable and should be preserved. The primary migration challenge is not the number of collections; it is schema heterogeneity accumulated inside those collections.
