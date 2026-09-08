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

## Scheduling ownership

Ordinary Episodic writes enter the Dream lifecycle as `dream_status=pending`. CyberBrain's server-side scheduler discovers pending sessions, waits until the configured quiet period has elapsed, and queues eligible sessions automatically. External agents are not required to call `dream_enqueue` after storing memory.

`dream_enqueue` remains an explicit/manual control path for forcing or narrowing a completed-session Dream run. It does not define the normal lifecycle.

The scheduler and worker are part of CyberBrain's post-storage cognition boundary. Client agents may produce Episodes, but they do not own queueing, reasoning orchestration, evidence gates, promotion, or Knowledge writeback.

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

## Historical migration rationale

Earlier migration audits found heterogeneous imported episodic payloads, including mixed timestamp representations, metadata placement, and incomplete legacy fields. Those observations are historical evidence; they are not claims about the current canonical runtime.

The canonical requirements derived from that evidence remain:

- imported or legacy payloads must pass through normalization before Dreaming consumes them;
- temporal recall must use the canonical event-time accessor rather than raw payload assumptions;
- advertised retrieval filters must be enforced and covered by tests;
- Knowledge status is interpreted through canonical evolution identity/version rules rather than treated as an unverified truth signal;
- migration-specific compatibility must not weaken current provenance or evidence validation.

Historical Phase 0 and migration evidence is preserved under `docs/history/`.

Detailed thresholds and evidence/task budgets are runtime policy and may be tuned from operational evidence. Dreaming writes are enabled only through the implemented provenance validation, promotion/review gate, DreamRun audit, and Knowledge Evolution writeback path.
