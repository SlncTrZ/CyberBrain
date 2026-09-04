# Knowledge Evolution Specification v1

## Purpose

Knowledge Evolution maintains durable conclusions over time without erasing historical evidence.

Core invariant:

> For a given canonical entity identity and context scope, at most one version is `active` after a successful evolution operation.

## Entity identity

Canonical identity is computed from normalized:

```text
domain
topic
entity_type
entity_name
context scope
```

The context scope contains only identity-relevant dimensions such as OS, environment, deployment target, or hardware variant.

Do not include volatile metadata such as timestamps, confidence, or source in entity identity.

## Evolution outcomes

A store request can result in:

```text
insert_new
no_change
evolve
context_split
reject
```

### insert_new

No equivalent canonical entity exists.

### no_change

Exact or semantically equivalent content already exists and no durable metadata change requires a new version.

### evolve

A new conclusion supersedes the active version for the same identity/context.

### context_split

Old and new conclusions are both valid under different context scopes.

### reject

Input fails validation, evidence, security, or consistency requirements.

## Version semantics

- First canonical version is `1`.
- Evolution increments version monotonically for the same entity identity/context.
- Version numbers are not globally unique.
- Historical versions remain addressable by immutable ID.

## Lifecycle

Allowed status:

```text
active
superseded
deprecated
rejected
```

Evolution from A to B:

```text
A.status = superseded
A.superseded_by_id = B.id
B.status = active
B.supersedes_id = A.id
```

## Negative knowledge

A failed approach may be preserved as:

```text
status = rejected
negative_knowledge = true
```

Negative knowledge is not a recommendation. Retrieval/ranking must preserve this semantic distinction.

## Duplicate detection

Exact duplicate detection uses `content_hash` first.

Semantic similarity may propose equivalence but must not alone silently overwrite canonical knowledge.

## Evidence rules

Manual/user-confirmed writes may establish canonical knowledge directly when authorized.

Derived/Dreaming writes must include evidence IDs and pass Dreaming evidence policy.

High-impact evolution should require stronger evidence than ordinary ingestion.

## Transactional behavior

A successful evolution must not leave two active versions due to partial failure.

The storage adapter must implement one of these tested strategies:

1. transactional/atomic update where supported; or
2. idempotent two-phase mutation with explicit recovery state.

Do not copy the current MeiLin pattern of inserting and then best-effort deprecating without a recoverable consistency mechanism.

## Concurrency

Concurrent evolution of the same entity must be serialized or conflict-detected.

The V1 implementation should use an application-level entity lock or compare-and-set strategy before introducing distributed complexity.

## Contradiction classification

When old and new conclusions differ, classify:

```text
evolution
context_dependent
true_contradiction
insufficient_evidence
```

Only `evolution` supersedes automatically.

`context_dependent` creates/maintains separate scoped canonical records.

`true_contradiction` requires evidence resolution or review.

## Repair of legacy duplicate-active records

Legacy duplicates are migration input and must not be auto-fixed by the normal V1 write path.

They require a separate reconciliation workflow with dry-run output and audit evidence.
