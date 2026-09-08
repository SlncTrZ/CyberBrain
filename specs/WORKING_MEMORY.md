# Working Memory / Active Context Specification v1

## Purpose

Working Memory (M5) maintains a bounded, transient active set for one current task.

It exists to preserve task continuity without repeatedly re-retrieving or re-injecting the same context and without turning transient task state into durable memory.

Working Memory is **not** canonical Knowledge, Episodic Memory, Dreaming, Concept Formation, Salience, or a replacement for the caller authorization boundary.

## Ownership boundary

M5 owns:

```text
exact transient working-set identity
bounded active items
explicit task relevance
Salience-informed ordering after relevance
within-set duplicate suppression
token/item budgeting
TTL and closeout
unchanged-context emission suppression
transient revision tracking
```

M5 does not own:

```text
truth
retrieval authorization
caller identity
Knowledge persistence
Episode persistence
Dream scheduling
Concept promotion
Salience semantics
long-term retention / forgetting
```

The required ordering is:

```text
authentication / trusted authority
→ hard candidate visibility / scope eligibility
→ task relevance
→ Salience
→ duplicate suppression
→ Token Governor budget
→ transient Working Memory active set
```

No Working Memory step may broaden the upstream authorization result.

## Exact working-set identity

Every active set is identified by the exact tuple:

```text
scope_marker
session_id
task_id
```

All three components are required and non-empty.

Candidates must carry the exact same identity as the target working set. A candidate from another scope, session, or task fails closed rather than being silently ignored or merged.

The in-memory service provides no cross-task enumeration API.

## Item classes

M5 V1 supports the bounded item classes required by the Level-8 program:

```text
goal
subgoal
assumption
hypothesis
evidence
concept_reference
blocker
open_question
recent_decision
selected_memory_reference
```

`concept_reference` and `selected_memory_reference` require explicit reference IDs.

A Concept reference is only a reference. M5 does not copy the full historical Concept evidence set into active context automatically and does not reinterpret a Concept candidate as truth.

## Task relevance

Task relevance is an explicit bounded input:

```text
score ∈ [0, 1]
reason_codes[]
```

M5 V1 does not infer task relevance by performing a new unrestricted search or by treating Salience as relevance.

Task relevance is a selection signal, not an authorization signal and not a truth score.

The default minimum task-relevance threshold is:

```text
0.20
```

Candidates below the threshold are excluded before Salience assessment or token budgeting.

## Salience relationship

After relevance filtering, M5 consumes the existing `SalienceAdvisor` for already-authorized, same-scope candidates.

Ordering is lexicographic:

```text
higher task relevance
→ higher Salience
→ stable original candidate order
```

This preserves the architectural separation:

```text
task relevance != Salience
Salience != authorization
Salience != truth
```

M5 does not modify Salience scores or reason semantics.

## Duplicate suppression

Duplicate suppression happens before token budgeting.

Stable duplicate identity preference:

```text
explicit reference ID
→ source record ID
→ normalized text fingerprint
```

When duplicate candidates compete, the candidate that already ranked higher by task relevance and Salience is retained.

Candidate IDs themselves must still be unique within one activation request.

## Token and resource budget

M5 and the Agent Adapter share the same deterministic core token-estimation/clipping primitive; `TokenGovernor` delegates to it rather than owning M5 budgeting semantics.

Default Working Memory policy:

```text
max candidates        64
max active items      12
max active tokens   1200
max tokens/item      240
TTL                 3600 seconds
```

All limits are hard ceilings.

Selection order is deterministic and budget enforcement occurs before state activation.

A candidate may be clipped to the per-item/remaining token budget. M5 does not perform an LLM summary merely to force an item under budget.

## Transient lifecycle

`WorkingMemoryService` is process-memory operational state only.

Operations:

```text
activate(identity, candidates, now)
get(identity, now)
emit(identity, ledger, now)
close(identity, now)
purge_expired(now)
```

Activation replaces the current active set for the exact task identity and increments a transient revision.

State expiry is explicit and deterministic from `updated_at + ttl_seconds`.

`close()` removes the active set and returns only non-content closeout metadata. It does not write an Episode or Knowledge record.

Durable lessons remain owned by ordinary memory storage, Dreaming, promotion/review, and Knowledge Evolution.

## Emission ledger

For an ongoing consumer context, `WorkingMemoryEmissionLedger` tracks the last emitted content fingerprint per candidate ID.

Unchanged items are not re-emitted on every task step. If the content fingerprint changes, the item is emitted again.

The ledger itself is exact-task scoped and fails closed on identity mismatch.

A consumer that lost or compacted its model context must start a fresh emission ledger; M5 does not assume that an old external prompt context still exists forever.

## Metrics

M5 metrics contain counts/token totals only and no content-bearing labels.

Current counters/timings include activation, selected items/tokens, reads/misses, emissions, repeated-injection suppression, expiry, and closeout.

## Controlled multi-step benchmark

The source benchmark is:

```text
benchmarks/working_memory/fixtures.json
benchmarks/working_memory/benchmark.py
```

It contains four reviewed deterministic development-task scenarios and sixteen task steps.

The benchmark compares a stronger stateless per-step baseline against M5 transient active context.

The quality metric is explicitly a proxy:

```text
required_context_coverage_proxy
```

It measures whether the context items required by each fixture step are available. It is **not** an LLM quality score or production task-success claim.

Accepted source evidence:

```text
                                  baseline     M5
required context coverage          67.35%    100.00%
recall calls                           16          4
memory/context tokens                1045        458
repeated context injections            32          0
stale-context contaminations            8          0
exact fetch count                      12          4
cross-task leakage                      —          0
```

The controlled benchmark changes no runtime behavior.

M5 source acceptance requires:

```text
M5 coverage >= baseline
M5 coverage >= 95%
M5 tokens <= baseline
M5 recall calls <= baseline
M5 repeated injection = 0
M5 stale contamination = 0
M5 cross-task leakage = 0
M5 exact fetches <= baseline
```

These thresholds validate the source mechanism only. Production activation requires its own authorization/integration and live evidence.

## Storage and runtime model

M5 adds:

```text
NO third Qdrant collection
NO graph database
NO durable Working Memory store
NO automatic Episode write on closeout
NO automatic Knowledge write
NO public Working Memory MCP tool
NO caller-visible retrieval reranking
```

The source mechanism is internal and transport-neutral. It is not wired into the current production MCP request path while broader shared read-path authorization remains incomplete.

An optional Agent Adapter integration may consume M5 later, but the Adapter must remain a convenience layer rather than the owner of Working Memory state or cognitive policy.

## Security and tenancy boundary

M5 accepts only candidate objects that already passed upstream authority and scope eligibility.

The exact `scope_marker/session_id/task_id` boundary prevents accidental local cross-task mixing, but it is not a substitute for trusted runtime identity or full P3 enforcement.

Therefore source-level M5 completion does not enable multi-user operation and does not authorize broader candidate visibility.

## Non-goals

M5 V1 does not add:

- autonomous goal generation;
- hidden planning authority;
- unrestricted semantic retrieval;
- durable scratchpad persistence;
- agent self-model claims;
- memory decay/forgetting;
- free-form context summarization;
- cross-task working-set merging;
- public MCP state-management tools.

## Completion boundary

M5 is source-level complete when:

- exact task/session/scope identity is enforced;
- all planned active item classes exist;
- task relevance remains separate from Salience;
- duplicate suppression precedes token packing;
- item/candidate/token ceilings are hard;
- TTL and closeout are explicit;
- unchanged context can be emitted as a delta without repeated injection;
- cross-task/session/scope access fails closed;
- the controlled multi-step benchmark improves context continuity at controlled token/retrieval cost;
- stale-context contamination and cross-task leakage are zero in the accepted fixture;
- no durable storage or public runtime authority is added;
- full regression, lint, and integrity gates pass.
