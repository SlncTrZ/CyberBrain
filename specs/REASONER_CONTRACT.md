# Dream Reasoner Contract v1

## Purpose

The Reasoner is an open decision/synthesis boundary used by Dreaming.

CyberBrain core must remain agnostic to model, vendor, process location, implementation technique, and transport.

## Request

`DreamReasoningRequest` contains only CyberBrain-domain information:

```text
request_id
session_id
focal_topics
session_start
session_end
evidence_by_topic
instructions_version
```

Each evidence item contains:

```text
id
record_type
content
score
event_time
metadata
```

The request MUST NOT contain credentials or provider-specific connection details.

## Result

`DreamReasoningResult` contains:

```text
request_id
candidates
notes
```

Each candidate contains:

```text
entity_name
entity_type
summary
content
evidence_ids
confidence
classification
negative_knowledge
context
```

## Classifications

Canonical initial classifications:

```text
new_knowledge
evolution
context_dependent
contradiction
rejected_approach
insufficient_evidence
```

## Authority boundary

A Reasoner has no storage authority.

It proposes structured candidates only.

```text
Reasoner result
   ↓
CyberBrain schema validation
   ↓
evidence/reference validation
   ↓
confidence/policy gate
   ↓
Knowledge Evolution or no-write
```

No adapter may bypass this gate.

## MCP-first adapter

MCP is the preferred first-class transport for external Reasoners.

Expected deployment shape:

```text
CyberBrain
   ↓ DreamReasoner protocol
MCPReasoner adapter
   ↓ MCP invocation
Reasoner provider
```

The provider may internally use any implementation, including:

- local LLM
- cloud LLM
- model ensemble
- deterministic rules
- retrieval system
- human approval workflow
- another agent

CyberBrain does not need to know.

## MCP tool contract

A Reasoner MCP provider SHOULD expose a stable tool such as:

```text
reason
```

Gateway namespace examples:

```text
reasoner.reason
research_reasoner.reason
private_reasoner.reason
```

Input and output must map losslessly to `DreamReasoningRequest` and `DreamReasoningResult`.

Provider identity/tool name is runtime configuration and never part of the Dreaming domain model.

## Failure semantics

Reasoner failures are explicit and retryable only when appropriate.

A malformed or schema-invalid result is rejected.

A timeout/provider failure must not produce synthetic candidates or silently mark the Dream job successful.

## Versioning

The Reasoner contract is independently versioned.

Initial contract:

```text
reasoner_contract_version = 1
```

Adapters may support provider-specific protocol versions internally, but they must normalize into the canonical CyberBrain contract.
