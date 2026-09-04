# Reasoner MCP Provider Contract v1

## Purpose

This contract defines a generic MCP provider that can satisfy CyberBrain's open `DreamReasoner` boundary.

The provider may use any internal implementation. CyberBrain does not know or care whether that implementation is a local model, cloud API, rules engine, human workflow, agent, ensemble, or something else.

## Provider identity

Recommended provider id:

```text
reasoner
```

Gateway canonical tools:

```text
reasoner.help
reasoner.reason
reasoner.reason_task
```

Alternative provider ids are allowed. CyberBrain treats the configured tool name as runtime configuration.

## Mandatory tools

### `help`

Read-only, zero side effects, compliant with `MCP_PROVIDER_STANDARD.md`.

### `reason`

Read-only with respect to CyberBrain storage. It may perform remote computation, retrieval, or orchestration internally, but it MUST NOT mutate CyberBrain knowledge or episodic memory directly.

`reason` remains available for full-request compatibility.

### `reason_task`

`reason_task` is the preferred tool for canonical multipass Dreaming. It resolves one bounded `ReasoningTask` and returns evidence-grounded claims only. CyberBrain owns task decomposition, result assembly, provenance validation, and all write authority.

Input:

```json
{
  "task_id": "string",
  "request_id": "string",
  "topic": "string",
  "kind": "current_state|superseded_or_removed|durable_lesson|caveat",
  "instruction": "string",
  "evidence": [
    {
      "id": "string",
      "record_type": "knowledge|episode",
      "content": "string",
      "score": 0.0,
      "event_time": "RFC3339 timestamp or null",
      "metadata": {}
    }
  ]
}
```

Output:

```json
{
  "task_id": "string",
  "claims": [
    {
      "claim": "string",
      "evidence_ids": ["string"],
      "confidence": 0.0
    }
  ]
}
```

The provider MUST echo `task_id` exactly and MUST NOT cite evidence IDs outside the supplied task evidence.

## `reason` input

```json
{
  "request_id": "string",
  "session_id": "string",
  "focal_topics": ["string"],
  "session_start": "RFC3339 timestamp",
  "session_end": "RFC3339 timestamp",
  "instructions_version": "1",
  "evidence_by_topic": {
    "topic": [
      {
        "id": "string",
        "record_type": "knowledge|episode",
        "content": "string",
        "score": 0.0,
        "event_time": "RFC3339 timestamp or null",
        "metadata": {}
      }
    ]
  }
}
```

Required top-level fields:

```text
request_id
session_id
focal_topics
session_start
session_end
instructions_version
evidence_by_topic
```

## `reason` output

```json
{
  "request_id": "string",
  "candidates": [
    {
      "entity_name": "string",
      "entity_type": "string",
      "summary": "string",
      "content": "string",
      "evidence_ids": ["string"],
      "confidence": 0.0,
      "classification": "new_knowledge|evolution|context_dependent|contradiction|rejected_approach|insufficient_evidence",
      "negative_knowledge": false,
      "context": {}
    }
  ],
  "notes": ["string"]
}
```

## Validation rules

- `request_id` MUST be echoed exactly for `reason`.
- `task_id` MUST be echoed exactly for `reason_task`.
- Every `evidence_id` MUST refer to an evidence item included in the request.
- `confidence` MUST be in `[0,1]`.
- Unknown classifications MUST be rejected by CyberBrain validation.
- Empty candidate lists are valid.
- The provider MUST NOT fabricate evidence identifiers.
- Provider/model metadata MUST NOT be required by the canonical contract.

## Reasoning instructions

The provider should reason toward durable knowledge, not chronological summaries.

It should identify:

1. recurring problems
2. attempted approaches
3. abandoned/failed approaches and why they failed
4. decisions that supersede earlier decisions
5. contradictions and context-dependent differences
6. durable lessons
7. negative knowledge worth preserving
8. the smallest canonical candidate set that preserves the lesson

## Error semantics

Use structured provider errors consistent with `MCP_PROVIDER_STANDARD.md`.

Malformed input -> `validation_error`.

Backend timeout -> `timeout`.

Backend unavailable -> `provider_unavailable`.

Malformed backend output -> `internal_error` or provider-specific validation error.

A failure MUST NOT be converted into an empty successful candidate set.

## Security

The provider receives evidence content only. Credentials and CyberBrain write authority are never part of the request.

Any sensitive output still passes CyberBrain's own post-reasoning validation before persistence.
