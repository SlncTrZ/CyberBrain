# CyberBrain Agent Working Harness

## Working rules

1. Read existing code, specs, and runtime evidence before writing.
2. Reuse proven CyberBrain or legacy-compatible logic before introducing new abstractions.
3. Make surgical changes; do not refactor unrelated code.
4. Treat `PLAN.md`, current `docs/`, `specs/`, and `MCP_PROVIDER_STANDARD.md` as current constraints. Files under `docs/history/` are non-normative evidence unless a current document explicitly references them.
5. Keep CyberBrain independent from any single persona or client.
6. Preserve only compatibility behavior that is explicitly part of the current tool/runtime contract; do not let legacy client behavior become a second business-logic path.
7. CyberBrain V1 uses exactly two Qdrant collections: `cyberbrain_knowledge` and `cyberbrain_episodic`.
8. Dreaming is a first-class evidence-backed consolidation process, not a free-form generative summarizer.
9. Dreaming must not invent facts; canonical evolution requires evidence.
10. Preserve useful negative knowledge and failed approaches when they prevent repeated mistakes.
11. Keep storage and embedding behind explicit adapters; domain logic must not be coupled throughout the codebase to Qdrant or Ollama.
12. MCP providers must comply with `MCP_PROVIDER_STANDARD.md`, including authenticated Streamable HTTP and mandatory `.help`.
13. Never commit secrets, credentials, tokens, private keys, or real deployment secrets.
14. Fail closed on unknown schema, incompatible embeddings, invalid auth, or insufficient evidence.
15. Tests must verify intent and migration safety, not only implementation details.
16. Checkpoint after each implementation slice: changed / verified / remaining.
17. `cyberbrain/_version.py` is the only current software/package version authority. Do not copy the current version into `pyproject.toml`, provider modules, CI/release scripts, current-status docs, or deployment scripts; derive it instead.
18. Working Memory is transient task state only: do not add a third canonical collection, automatic Episode/Knowledge persistence, or public state-management surface without a separately justified contract and authorization gate.
19. Agent Self-Model work fails safely on insufficient evidence. Persistent/scoped self-model influence requires repeated prospective outcome evidence plus trusted agent identity/P3 isolation; never lower that bar by reconstructing retrospective confidence or treating one success/failure as identity truth.
20. Schema-V2 corpus migration must follow `docs/V2_MIGRATION_RUNBOOK.md`: stage-before-cutover, full four-source union, vector/content/ID preservation, exact target-count convergence, independent validation, quarantine instead of fabrication, and explicit owner authorization before cutover.

## Implementation sequence

```text
audit → define boundaries → specify → implement deliberately → test
```

Do not copy a client-specific or deployment-specific implementation wholesale into CyberBrain as a shortcut.

## License

New CyberBrain source files should carry an SPDX identifier appropriate to their file format:

```text
SPDX-License-Identifier: MPL-2.0
```
