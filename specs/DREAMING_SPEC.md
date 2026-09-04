# Dreaming Specification v1

> Status: Implemented in CyberBrain V1. This specification describes the canonical Dreaming behavior; runtime tuning may evolve from production evidence without weakening the invariants below.

## Invariants

- Dreaming is session-driven, not strictly calendar-driven.
- It reads evidence from `cyberbrain_episodic` and relevant historical knowledge.
- It deliberately recalls across time ranges from older to newer evidence to reduce recency bias.
- It may associate related topics with bounded depth.
- It distinguishes failed attempts, final decisions, contradictions, evolution, and context-dependent conclusions.
- It preserves useful negative knowledge rather than blindly deleting failed approaches.
- It seeks the smallest canonical knowledge set that preserves the durable lesson.
- It never invents facts; canonical writes require evidence.
- Dreaming does not require a third Qdrant collection.

## Pipeline

```text
completed session
  → focal topic extraction
  → temporal recall
  → bounded associative recall
  → canonical evidence normalization
  → deterministic evolution grouping
  → section-specific evidence selection
  → multipass Reasoner orchestration
      ├── current-state micro tasks
      ├── superseded/removed micro tasks
      ├── durable-lesson micro tasks
      └── caveat micro tasks
  → provenance validation
  → assembled DreamReasoningResult
  → evidence/confidence gate
  → Knowledge Evolution / no-write
```

## Default multipass orchestration

The default Dreaming Reasoner strategy is multipass. A single large prompt over raw evidence is not the canonical path.

CyberBrain deterministically organizes evidence before interpretation:

```text
normalize
→ group by canonical identity
→ order by explicit links/version/time
→ flag anomalies
→ attach lexical relation hints
→ select bounded evidence per reasoning section
```

The deterministic layer may organize, sort, label hints, and detect anomalies. It MUST NOT decide which claim is true, which version is canonical, or which lesson should be persisted.

The Reasoner boundary is split into two levels:

```text
DreamReasoner
   ↓
MultipassDreamReasoner
   ↓
MicroReasoner.reason_task(task)
```

`MicroReasoner` implementations may be MCP-backed, local, remote, rules-based, human-backed, or custom. They receive small `ReasoningTask` objects rather than the entire raw history.

Canonical initial task kinds:

```text
current_state
superseded_or_removed
durable_lesson
caveat
```

Every micro-result must cite evidence IDs from the task it received. CyberBrain rejects fabricated IDs, mismatched task IDs, empty claims, invalid confidence values, and advice/recommendation output.

The assembled `DreamReasoningResult` therefore remains provenance-linked to immutable historical Qdrant point IDs. Dreaming output is a proposal backed by evidence, never unquestioned final truth.

## Evidence and promotion gate

Every candidate passes a CyberBrain-owned gate after reasoning. The gate produces one of:

```text
promote
review
reject
```

The gate considers at least:

```text
reasoner_confidence
evidence_strength
promotion_confidence
classification
evidence provenance
```

Reasoner confidence never grants write authority by itself. Unknown evidence IDs are rejected. Contradiction and context-dependent conclusions require review in V1. Weakly supported conclusions are reviewed or rejected according to policy.

`promote` means the candidate is eligible for the later Knowledge Evolution step. It does not itself mutate Qdrant.

## DreamRun audit

Each evaluated Dreaming run has an audit record containing:

```text
dream_run_id
session_id
request_id
input_evidence_ids
candidate snapshots
gate decisions
reasoner_confidence
evidence_strength
promotion_confidence
reasons
status/timestamps
```

The initial V1 audit store is SQLite. Historical evidence IDs and candidate decision records are retained so a promoted knowledge record can always be traced back to the exact evidence and promotion decision that produced it.

## Open Reasoner boundary

Dreaming core MUST NOT know:

- model name
- model vendor
- whether reasoning runs locally or remotely
- whether the implementation is an LLM
- whether transport is MCP, HTTP, subprocess, human review, rules, or another mechanism

The core communicates only through a stable Reasoner contract:

```text
DreamReasoningRequest
        ↓
DreamReasoner.reason(request)
        ↓
DreamReasoningResult
```

MCP is the preferred first-class transport adapter and is expected to handle most practical deployments, but MCP MUST remain outside the Dreaming domain core.

Reference layering:

```text
Dreaming Engine
   ↓
DreamReasoner protocol
   ├── MCPReasoner
   ├── DirectReasoner
   ├── HumanReviewReasoner
   ├── RulesReasoner
   └── custom adapter

MCPReasoner
   ↓
ReasonerTransport / MCP client
   ↓
any MCP reasoning provider
```

A Reasoner returns structured candidates and evidence references; it never receives authority to write Knowledge directly. All returned output must pass CyberBrain validation/evidence gates before any mutation.

## Observed production constraints from Phase 0

Dreaming must account for heterogeneous legacy/new episodic payloads:

- timestamps currently exist as both integer epoch values and strings
- session/channel metadata may be top-level on older points but nested under `extra_metadata` on newer points
- some episodic points have no version/status metadata
- the current recall tool does not correctly apply the advertised `channel` filter

Therefore Dreaming must consume a canonical normalization layer rather than reading raw Qdrant payloads directly.

Temporal recall must use a canonical event-time accessor whose migration precedence is explicitly specified and tested against real production payloads before Dreaming writes anything.

The current production Knowledge Evolution path also permits multiple active versions for some entities. Dreaming must treat `status=active` as evidence to inspect, not unquestioned canonical truth, until reconciliation rules are implemented.

Detailed thresholds and evidence/task budgets are runtime policy and may be tuned from production evidence. Dreaming writes are enabled only through the implemented provenance validation, promotion/review gate, DreamRun audit, and Knowledge Evolution writeback path.
