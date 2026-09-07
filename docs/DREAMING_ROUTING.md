# Dreaming Routing

CyberBrain keeps Dream reasoning provider-neutral.

The routing invariant is:

    MCP reasoner session
           ↓ unfinished tasks only
    configured LLM route 1: model 1A → model 1B → ...
           ↓
    configured LLM route 2: model 2A → model 2B → ...
           ↓
    ...

MCP is handled by the Dream worker before fallback routing. The configured LLM route service only
receives micro-tasks that were not completed through MCP within the common run-level wait window.

## Configure routes

Copy config/dream-routes.example.json to config/dream-routes.json, then replace the placeholder
providers and models with your own deployment choices.

Each route has:

- name: a stable local label for logs and diagnostics.
- base_url: HTTP(S) API root. Do not append /v1; CyberBrain appends the selected protocol path.
- models: ordered model names. Every model in the current route is tried before the next route.
- protocols: ordered compatible request surfaces:
  - responses → /v1/responses
  - chat_completions → /v1/chat/completions
  - messages → /v1/messages
- auth: none, bearer, or api_key.
- auth_env: required for authenticated routes; names the runtime environment variable containing
  the credential.
- timeout_seconds: timeout per protocol attempt.
- max_tokens: output-token budget sent to compatible APIs.
- failure_cooldown_seconds: temporary cooldown for a failed provider/model pair.

## Secrets

Route files must never contain credential values.

For example, auth=bearer with auth_env=MY_PROVIDER_TOKEN means the route service reads
MY_PROVIDER_TOKEN from its runtime environment. The value is not stored in CyberBrain
configuration, prompts, logs, or Git.

With Docker Compose, put runtime-only variables in your local .env file or otherwise inject them
into the dream-route-reasoner container. Do not commit the real .env file.

## Ordering semantics

Ordering is explicit and deterministic.

Given:

    provider-1: model-1A, model-1B
    provider-2: model-2A, model-2B

CyberBrain attempts:

    provider-1/model-1A
    provider-1/model-1B
    provider-2/model-2A
    provider-2/model-2B

A successful result still has to pass the canonical Reasoner contract and evidence-ID validation.
If every configured route fails, the Dream task fails explicitly; CyberBrain does not synthesize a
success result.

## Why routes are explicit

Provider discovery, billing policy, free-model catalogs, gateway topology, and model availability
are deployment concerns. CyberBrain deliberately does not encode them in the domain layer.

This keeps the project portable across users and infrastructures while preserving one stable
Dreaming contract.
