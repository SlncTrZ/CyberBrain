# CyberBrain — Development Plan

> Status: Historical development plan. CyberBrain V1 is complete and in production use-and-observe mode.
> Project root: `<project-root>`

## 1. Vision

CyberBrain is a portable knowledge + memory infrastructure for AI agents. It is not tied to the MeiLin persona.

MeiLin remains an agent/client that uses CyberBrain. CyberBrain owns the durable memory substrate, retrieval, consolidation, evolution, and governance.

Core principle:

> CyberBrain should not merely store memories. It should continuously consolidate experience into smaller, more durable, evidence-backed knowledge.

---

## 2. System Boundary

Target architecture:

```text
ChatGPT ─┐
Claude  ─┤
MeiLin  ─┼──> CyberBrain MCP/API
Pi      ─┤            │
Agents  ─┘            ▼
                  Knowledge Engine
                  Memory Engine
                  Dreaming Engine
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
           Qdrant            Embedding Runtime
                              Ollama / model
```

CyberBrain is a distributable stack, not one monolithic container.

Initial services:

```text
cyberbrain-api
qdrant
embedding-runtime
```

---

## 3. Data Model — Keep Two Collections

CyberBrain V1 keeps exactly two Qdrant collections:

```text
cyberbrain_knowledge
cyberbrain_episodic
```

Do not create a third `dreams` collection.

Dreaming is a process that reads episodic + historical knowledge and produces consolidated/evolved knowledge.

### 3.1 Knowledge

Durable, reusable conclusions, lessons, configs, research, code knowledge, and decisions.

### 3.2 Episodic

Session traces, conversations, decisions-in-progress, attempts, failures, tool interactions, and short-lived context.

### 3.3 Working state

Transient Dreaming jobs, queues, session state, and processing metadata should live outside Qdrant, initially in SQLite unless a stronger need appears.

---

## 4. First-Class Subsystems

CyberBrain V1 has four primary subsystems:

```text
1. Knowledge Engine
2. Memory Engine
3. Dreaming Engine
4. Interface Layer (MCP/API)
```

Storage and embedding are infrastructure adapters, not business-domain ownership boundaries.

---

# Phase 0 — Audit Existing MeiLin Runtime

## Goal

Extract generic CyberBrain behavior from the currently active MeiLin deployment without changing production.

Active runtime source to audit:

```text
<legacy-deployment-root>/meilin-mcp
```

Audit:

- `meilin_mcp.py`
- `streamable_http_server.py`
- `meilin_knowledge/*`
- Dockerfile
- requirements
- current 8 MCP tools
- Qdrant payload schemas
- collection indexes
- embedding configuration
- Knowledge Evolution logic
- garbage filtering
- versioning / supersession
- episodic storage
- authentication and runtime configuration

Classify code into:

- generic CyberBrain logic
- MeiLin-specific logic
- legacy logic
- duplicated logic

Deliverables:

```text
docs/CURRENT_ARCHITECTURE.md
docs/DATA_MODEL_AUDIT.md
docs/MIGRATION_PLAN.md
```

No production mutation in Phase 0.

---

# Phase 1 — CyberBrain Specification

## Goal

Define contracts before implementation.

```text
specs/
├── KNOWLEDGE_SCHEMA.md
├── MEMORY_SCHEMA.md
├── DREAMING_SPEC.md
├── TOOL_CONTRACT.md
├── EVOLUTION_SPEC.md
├── RETRIEVAL_POLICY.md
├── INGESTION_POLICY.md
├── SECURITY.md
└── VERSIONING.md
```

### Knowledge metadata baseline

Candidate canonical metadata:

```text
id
domain / wing
topic
entity_type
entity_name
content
summary
source
provenance
importance
confidence
version
status
created_at
updated_at
change_reason
embedding_provider
embedding_model
embedding_dimension
schema_version
```

Not every field must be supplied by the caller; CyberBrain may derive safe fields internally.

---

# Phase 2 — Repository Architecture

Target repo structure:

```text
CyberBrain/
├── README.md
├── AGENTS.md
├── LICENSE
├── PLAN.md
├── docker-compose.yml
├── .env.example
│
├── cyberbrain/
│   ├── api/
│   ├── mcp/
│   ├── knowledge/
│   ├── memory/
│   ├── dreaming/
│   ├── embedding/
│   ├── storage/
│   ├── schemas/
│   └── core/
│
├── specs/
├── docs/
├── migrations/
├── scripts/
├── tests/
└── deploy/
```

Rules:

- Qdrant must not leak throughout domain logic.
- Ollama must not be hard-coded as the only embedding provider.
- MCP is an adapter, not the core.
- Domain behavior lives in Knowledge / Memory / Dreaming engines.

---

# Phase 3 — Knowledge Engine

Canonical operations:

```text
knowledge_search
knowledge_store
knowledge_timeline
```

### Store pipeline

```text
input
  ↓
validation
  ↓
secret / garbage filtering
  ↓
entity resolution
  ↓
duplicate detection
  ↓
change detection
  ↓
versioning / supersession
  ↓
embedding
  ↓
storage
```

### Search requirements

- semantic search
- metadata filtering
- score threshold
- domain / wing
- topic
- entity filtering
- status/version filtering
- future-compatible hybrid ranking

Long-term search may evolve into:

```text
vector + lexical/BM25 + metadata ranking
```

without breaking the public tool contract.

---

# Phase 4 — Memory Engine

Canonical internal operations:

```text
memory_search
memory_store
```

Compatibility MCP aliases may initially remain:

```text
conversation_recall
conversation_save
```

A work session is a cognitive boundary, not necessarily a calendar day.

Session metadata should include:

```text
session_id
started_at
ended_at
projects
entities
primary_topics
importance
processed_for_dreaming
```

Possible session end signals:

- explicit session end
- inactivity timeout
- strong project/context shift
- nightly scheduler closing open sessions

---

# Phase 5 — Dreaming Engine

## Goal

Turn raw episodic experience into durable, minimal, evidence-backed knowledge.

Dreaming must perform actual reasoning over past experience, not merely summarize recent text.

Core invariant:

> Dreaming never invents knowledge. It only derives, reconciles, compresses, and evolves knowledge from evidence already present in CyberBrain.

## 5.1 Topic extraction

For each completed work session, derive a small set of focal topics.

Candidate signals:

- keyword frequency
- TF-IDF / lexical prominence
- repeated entities
- project/repo names
- tool-call targets
- high-importance episodic entries
- repeated technical nouns

Example:

```text
CyberBrain  0.91
MeiLin      0.87
MCP         0.55
Qdrant      0.42
```

Then choose only the highest-value focal topics, e.g.:

```text
["CyberBrain", "MeiLin"]
```

Use deterministic extraction first; use an LLM only where judgment is materially useful.

## 5.2 Temporal recall

Dreaming must deliberately query history from far to near to reduce recency bias.

Example time buckets:

```text
> 1 year
6–12 months
3–6 months
1–3 months
2–4 weeks
last week
current session
```

Buckets may adapt to actual data age and volume.

The system should ask, conceptually:

> Have we encountered this problem, decision, or pattern before?

## 5.3 Associative recall

Dreaming may expand from a focal topic into related historical concepts.

Example:

```text
CyberBrain
  → Knowledge Evolution
  → memory consolidation
  → OpenClaw memory
  → Pi memory
```

Limit association depth to prevent uncontrolled wandering.

Initial constraint:

```text
max_association_depth = 2
```

## 5.4 Build a temporary reasoning graph

Before writing conclusions, construct an ephemeral graph of evidence:

```text
Problem A
│
├── Attempt A
│   ├── why it was chosen
│   ├── failure a1
│   └── failure a2
│
├── Attempt A2
│   └── partial result
│
└── Attempt B
    ├── why it replaced A
    └── final outcome
```

This graph does not need its own permanent Qdrant collection.

## 5.5 Distill outcome, not chronology

Dreaming should compress the journey while preserving the lesson.

Raw sequence:

```text
A
→ failure a1
→ patch
→ failure a2
→ A'
→ failure
→ B
→ success
```

Canonical knowledge should become something like:

```text
Problem:
X

Previously attempted:
A

Why A failed:
a1
a2

Final decision:
B

Why B was selected:
...

Current status:
B is canonical
```

Principle:

> Compress the journey; preserve the lesson.

## 5.6 Preserve negative knowledge

Do not erase failed attempts merely because a better solution exists.

Failed approaches are valuable because they prevent future repetition.

Use lifecycle state such as:

```text
active
superseded
deprecated
rejected
```

Example:

```text
A was attempted and rejected because a1/a2.
B supersedes A.
```

Do not hard-delete history by default.

## 5.7 Contradiction dreaming

Dreaming must detect conflicting conclusions.

Example:

```text
old: use A
new: use B
```

Classify the relationship:

```text
contradiction
evolution
context-dependent
```

If evolution:

```text
A → superseded by B
```

If context-dependent:

```text
A → valid on Windows
B → valid on Linux
```

Keep both when context makes both correct.

## 5.8 Knowledge Evolution integration

Dreaming may produce:

1. new durable knowledge
2. an evolved version of existing knowledge
3. negative knowledge / rejected approaches
4. a contradiction requiring context separation
5. no write when evidence is insufficient

Dreaming should prefer updating/evolving an existing entity rather than blindly adding duplicates.

## 5.9 Confidence and evidence gates

Dreaming must not freely rewrite canonical knowledge.

Candidate initial policy:

```text
high confidence
→ auto-consolidate when evidence requirements pass

medium confidence
→ save as candidate / derived insight or require review

low confidence
→ discard
```

Exact thresholds must be determined experimentally rather than hard-coded prematurely.

High-impact canonical changes should require stronger evidence, for example:

- multiple independent memories
- an explicit user-confirmed decision
- current successful implementation evidence

## 5.10 Dream queue

Use a small relational store for jobs, initially SQLite.

Example fields:

```text
session_id
topics
created_at
status
attempt_count
last_dream_at
result_summary
```

Scheduler behavior:

```text
unfinished sessions
  ↓
group related sessions/topics
  ↓
temporal recall
  ↓
reasoning
  ↓
consolidation
```

Dreaming may run:

- after a session closes
- during configured idle periods
- at night
- manually through a script/tool

It is session-driven, not strictly day-driven.

## 5.11 Dream output minimization

Dreaming prompts/policies must explicitly seek the smallest canonical knowledge set that preserves the lesson.

Do not ask merely:

```text
Summarize this session.
```

Instead reason along the lines of:

```text
1. Identify recurring problems.
2. Identify attempts that were abandoned.
3. Explain why they failed.
4. Identify decisions that superseded earlier decisions.
5. Detect contradictions between old and current knowledge.
6. Extract durable lessons.
7. Preserve failed approaches only when they prevent future repetition.
8. Produce the smallest canonical knowledge set that preserves the lesson.
```

## 5.12 Anti-vector-landfill objective

Without consolidation:

```text
many sessions
→ many chunks
→ semantic sludge
```

With Dreaming:

```text
episodic traces
→ repeated experiences
→ lessons
→ canonical knowledge
```

Episodic data may later receive retention/compaction policies, but durable lessons must survive.

---

# Phase 6 — Embedding Layer

Initial compatibility target:

```text
Ollama
nomic-embed-text
768 dimensions
```

Define an abstraction:

```text
EmbeddingProvider
├── Ollama
├── OpenAI-compatible
├── local inference
└── future providers
```

Persist embedding metadata:

```text
embedding_provider
embedding_model
embedding_dimension
embedding_version
```

This is required for future embedding migrations.

---

# Phase 7 — Storage Layer

V1 remains Qdrant.

Define repository abstractions:

```text
KnowledgeRepository
MemoryRepository
```

Business logic should not call Qdrant directly throughout the codebase.

Retain compatibility with the existing two production collections where possible.

---

# Phase 8 — CyberBrain MCP/API

CyberBrain must comply with the shared SlncTrZ-MCP provider standard defined by `MCP_PROVIDER_STANDARD.md` in the SlncTrZ-MCP repository. CyberBrain is the first reference implementation of that standard, but the standard itself is owned by the gateway ecosystem rather than by this project.

Required provider properties include:

- MCP Streamable HTTP transport at `/mcp`
- authenticated access using `Authorization: Bearer <token>` as the primary convention
- optional `X-API-Key` compatibility when appropriate
- no credentials in URLs, query parameters, prompts, logs, or tool results
- canonical gateway namespace `<provider>.<tool>`
- mandatory self-describing `<provider>.help` tool
- explicit provider/tool contract versioning
- stable error semantics and fail-closed authentication behavior
- provider-owned business logic; gateway-owned routing, namespace, policy, and provider lifecycle

Long-term canonical namespace:

```text
cyberbrain.help
cyberbrain.knowledge_search
cyberbrain.knowledge_store
cyberbrain.knowledge_timeline
cyberbrain.memory_search
cyberbrain.memory_store
```

Potential Dreaming interface later:

```text
cyberbrain.dream
cyberbrain.dream_status
```

Do not expose these until the Dreaming contract is stable.

Compatibility aliases may keep the existing MeiLin tools temporarily.

---

# Phase 9 — Self-Describing Help Contract

CyberBrain must be self-documenting and implement the mandatory `.help` contract from the shared MCP provider standard.

`cyberbrain.help` should return a live contract, not hard-coded documentation.

Suggested response metadata:

```text
provider_name
provider_version
protocol_version
contract_version
schema_version
contract_hash
updated_at
authentication
capabilities
content
```

Documentation should be mounted/read at runtime, read-only, so updates do not require rebuilding the image.

---

# Phase 10 — Docker Distribution

CyberBrain is a Compose stack, not an all-in-one image.

```text
services:
  cyberbrain:
  qdrant:
  embedding:
```

Future profiles may include:

```text
default
gpu
external-qdrant
external-embedding
```

Goal:

```text
docker compose up -d
```

should be sufficient to launch a new instance from a clean host once configuration and data are provided.

Data must remain outside images.

---

# Phase 11 — Configuration

Use explicit config files for behavioral policy:

```text
config/
├── cyberbrain.yaml
├── retrieval.yaml
├── ingestion.yaml
├── dreaming.yaml
└── security.yaml
```

Use environment variables for:

- credentials
- deployment overrides
- host/port
- infrastructure-specific values

Do not encode the entire behavior model in environment variables.

---

# Phase 12 — Security & Governance

Mandatory rules:

### Secret rejection

Never persist passwords, API keys, bearer tokens, private keys, credentials, or session secrets.

### Provenance

Durable knowledge should be traceable to evidence/source whenever possible.

### Confidence classification

Possible states:

```text
verified
derived
user_confirmed
research
unverified
```

### Lifecycle

Prefer soft state transitions:

```text
active
superseded
deprecated
rejected
deleted
```

No hard-delete by default.

---

# Phase 13 — Observability

Minimum metrics:

```text
search latency
embedding latency
Qdrant latency
search hit rate
no-result rate
write count
duplicate rejection
version evolution
dream runs
dream duration
dream candidate count
dream write count
contradiction count
embedding failures
```

Never log raw secrets or sensitive content.

---

# Phase 14 — Backup, Restore, Migration

CyberBrain portability requires:

```text
backup
restore
export
import
schema migration
embedding migration
```

Docker volumes alone are not a backup strategy.

Recovery procedures must be documented and tested.

---

# Phase 15 — MeiLin Migration

After CyberBrain stabilizes:

```text
MeiLin = persona / orchestration / user-facing behavior
CyberBrain = knowledge + memory infrastructure
```

Target relationship:

```text
MeiLin uses CyberBrain.
MeiLin is not CyberBrain.
```

Migration flow:

```text
Current MeiLin MCP
      ↓
audit and extract generic core
      ↓
CyberBrain staging
      ↓
compatibility with existing Qdrant data
      ↓
comparison tests
      ↓
gateway provider cutover
      ↓
MeiLin becomes a client/compatibility layer
```

Rollback must remain possible throughout cutover.

---

# Architecture Principles

1. **Specification > implementation**  
   CyberBrain is not defined by Qdrant.

2. **Data model > vector database**  
   Data and semantics should survive storage-engine changes.

3. **Dreaming is first-class**  
   Consolidation is a core subsystem, not a cron-based summary feature.

4. **Evidence before evolution**  
   Canonical knowledge cannot be rewritten merely because a model generated a plausible thought.

5. **Preserve negative knowledge**  
   Failed approaches matter when they prevent repetition.

6. **Session boundaries > calendar boundaries**  
   Cognitive work units matter more than dates.

7. **Read-before-write**  
   Search and entity resolution should precede writes that may duplicate or supersede knowledge.

8. **Fail closed**  
   Unknown schema, incompatible embedding, insufficient evidence, or invalid metadata must surface clearly.

9. **No vector landfill**  
   Permanent knowledge must be governed and consolidated.

10. **Backward compatibility**  
    Do not break MeiLin production solely for naming or aesthetic refactors.

---

# Milestones

## M0 — Discovery
Audit active MeiLin runtime and data model.

## M1 — Specification
Lock down schema, contracts, governance, and Dreaming rules.

## M2 — CyberBrain Core
Extract Knowledge + Memory engines.

## M3 — Dreaming Prototype
Implement session/topic extraction, temporal recall, reasoning graph, contradiction handling, and dry-run consolidation.

## M4 — Docker Stack
Make CyberBrain + Qdrant + embedding reproducible.

## M5 — MCP/API
Expose stable CyberBrain tools and self-describing help.

## M6 — Compatibility
Run existing MeiLin semantics through CyberBrain.

## M7 — Production Migration
Cut gateway provider over with rollback.

## M8 — Hardening
Backup, migration, observability, security, and Dreaming quality evaluation.

---

# Success Criteria V1

CyberBrain V1 is complete when:

- repository can bootstrap on a clean machine
- `docker compose up -d` launches the stack
- healthchecks are explicit
- two Qdrant collections remain sufficient
- knowledge search/store/timeline work
- episodic memory search/store work
- Dreaming can process completed sessions
- Dreaming recalls history across time ranges
- Dreaming preserves failed approaches as negative knowledge where useful
- Dreaming can distinguish contradiction vs evolution vs context-dependent knowledge
- Dreaming produces minimal canonical knowledge rather than session summaries
- canonical writes are evidence-gated
- mandatory `cyberbrain.help` exists and complies with the shared SlncTrZ-MCP provider standard
- credentials are absent from repo/images
- existing production data can be migrated or attached safely
- embedding configuration is versioned
- backup/restore is tested
- schema migration exists
- Knowledge Evolution is tested
- another agent can use CyberBrain without knowing anything about MeiLin

---

# Post-V1 Operating Mode

CyberBrain V1 is complete. New work is driven by observed production failures or quality evidence rather than architectural completeness.

```text
USE CYBERBRAIN
→ observe real failures/friction
→ record evidence
→ fix or tune only proven problems
```

Current non-blocking backlog includes longer production acceptance, eventual retirement of temporary compatibility aliases, optional collection renaming after the rollback window, and operational tuning of Reasoner routing/evidence budgets from real usage.

Gateway ownership remains a hard boundary: CyberBrain may implement the provider contract and compatibility adapters, but gateway routing, namespace, policy, lifecycle, or adapter defects must be reported to the gateway owner rather than modified from this project workflow.
