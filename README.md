# CyberBrain

[![CI](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml/badge.svg)](https://github.com/SlncTrZ/CyberBrain/actions/workflows/ci.yml)

CyberBrain is a portable knowledge and memory system for AI agents.

It provides canonical Knowledge, Episodic Memory, retrieval, Knowledge Evolution, and
evidence-grounded Dreaming with traceable reasoning and explicit promotion/review gates.

## Status

Latest tagged release: v0.1.5.

The repository is in use-and-observe mode: changes should be driven by reproducible defects,
operational evidence, security/privacy needs, or portability gaps rather than speculative feature
growth.

GitHub CI validates lint, the full automated test suite, package build, Compose configuration, and
container build on supported changes.

## Core architecture

    AI clients / agents
           ↓
    CyberBrain MCP/API
           ↓
    Knowledge Engine + Memory Engine + Dreaming Engine
           ↓
    Qdrant + Embedding Runtime

CyberBrain intentionally keeps exactly two canonical durable Qdrant collections:

    cyberbrain_knowledge
    cyberbrain_episodic

Dreaming is a process, not a third collection. Queue, audit, and reason-task coordination state are
operational state stored separately from canonical Knowledge and Episodic Memory.

## Learning primitives

Main now includes the first bounded cognitive-learning mechanism: Prediction / Outcome / Prediction Error.

Agents can record an explicit expected outcome and prior confidence before an action, then resolve that prediction with an observed outcome and finite assessment. CyberBrain stores both as canonical Episodic evidence and derives a transparent prediction-error signal. This does not implement metacognition or self-modeling.

See specs/PREDICTION_LEARNING.md.

## Dreaming

Dreaming is evidence-grounded consolidation.

A reasoning result cannot write Knowledge directly. It must pass contract validation, evidence-ID
validation, promotion policy, and review/writeback rules before canonical Knowledge changes.

Dream reasoning is deployment-configurable and provider-neutral:

    MCP reasoner session
           ↓ unfinished tasks only
    LLM provider 1: model 1A → model 1B → ...
           ↓
    LLM provider 2: model 2A → model 2B → ...
           ↓
    ...

CyberBrain does not hard-code a provider, model catalog, commercial routing policy, or external
routing product.

For fallback LLM routing, copy:

    config/dream-routes.example.json

to:

    config/dream-routes.json

Then define providers and models in the exact order they should be attempted. Credentials are
referenced by environment-variable name through auth_env; secret values do not belong in the route
file or Git.

See docs/DREAMING_ROUTING.md.

## Run with Docker Compose

Base stack:

    cp .env.example .env
    # Set CYBERBRAIN_MCP_AUTH_TOKEN in .env.
    docker compose up -d

Dreaming stack:

    cp config/dream-routes.example.json config/dream-routes.json
    # Edit the route file and provide the referenced provider credentials in the runtime environment.
    # Also configure CYBERBRAIN_DREAM_REASONER_BEARER_TOKEN.
    docker compose --profile dreaming up -d

The default Compose stack includes CyberBrain, Qdrant, and the embedding runtime. The dreaming
profile additionally starts the Dream worker, configured LLM route reasoner, and nightly scheduler.

See docs/CURRENT_RUNTIME.md for the source-level runtime contract.

## MCP

CyberBrain exposes authenticated MCP Streamable HTTP at /mcp and provider-local MCP tool names.

MCP_PROVIDER_STANDARD.md is the repository's reference integration standard for gateway-compatible
provider behavior. CyberBrain's domain model does not depend on one specific gateway deployment.

Current tool behavior is documented in TOOL_GUIDE.md and specs/TOOL_CONTRACT.md.

## Documentation

Current guidance:

- PLAN.md — current project operating mode and architectural invariants.
- TOOL_GUIDE.md — current MCP tool behavior.
- docs/CURRENT_RUNTIME.md — deployment-neutral runtime contract.
- docs/DREAMING_ROUTING.md — provider-neutral Dream fallback routing.
- specs/ — canonical data, retrieval, evolution, Dreaming, security, Reasoner, and tool contracts.

Historical evidence:

- docs/history/ — V1 development plan, migration audits, staged migration reports, freeze/release
  snapshots, and earlier runtime evidence.

Historical documents are preserved for provenance and are not current operating instructions.

## Development rule

Keep business logic independent from individual clients, providers, models, and deployment
topologies.

Preferred sequence:

    audit → define boundaries → specify → implement deliberately → test

## License

CyberBrain is licensed under the Mozilla Public License 2.0 (MPL-2.0).
