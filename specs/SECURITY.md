# CyberBrain Security Specification v1

## Provider security

CyberBrain follows `MCP_PROVIDER_STANDARD.md`.

Network MCP deployment requires authenticated access.

Primary auth:

```text
Authorization: Bearer <token>
```

Optional compatibility auth:

```text
X-API-Key: <token>
```

Production/network mode must fail closed when required authentication is not configured.

## Secret handling

Never persist or emit:

- passwords
- API keys
- bearer tokens
- private keys
- session secrets
- credential files

Secrets must not appear in:

- Qdrant payloads
- embeddings
- prompts used for Dreaming
- logs
- tool results
- URLs/query strings
- source-controlled config

## Ingestion secret rejection

Durable writes pass a secret-detection gate before embedding or persistence.

Detection should combine deterministic patterns and configurable high-risk field/name rules. LLM judgment must not be the only secret filter.

When a candidate looks sensitive, reject or require explicit safe redaction rather than storing first and cleaning later.

## Authorization boundary

MCP transport authentication answers who may call the provider.

Tool-level authorization/policy may additionally be enforced by SlncTrZ-MCP. CyberBrain must not self-expand gateway authority or bypass gateway policy.

## Logging

Logs may include:

```text
request/tool id
operation class
latency
success/failure
safe error code
```

Logs must redact sensitive arguments and never log auth credentials.

## Error safety

External errors must not include full stack traces, environment dumps, connection secrets, or raw dependency configuration.

Internal diagnostics may preserve stack traces only in protected server logs after redaction.

## Dreaming safety

Dreaming only reasons over data CyberBrain is authorized to read.

Dreaming cannot lower verification/security requirements for its own writes.

Derived output containing suspected secrets is rejected before embedding/persistence.

## Dependency failure

Embedding/storage failure must fail explicitly. CyberBrain must not silently generate zero vectors, discard writes, or report false success.

## Configuration

Behavioral non-secret configuration may live in tracked YAML examples/defaults.

Real credentials remain runtime-only and are never checked into Git.
