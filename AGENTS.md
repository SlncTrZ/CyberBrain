# CyberBrain Agent Working Harness

## Working rules

1. Read existing code, specs, and runtime evidence before writing.
2. Reuse proven MeiLin/CyberBrain logic before introducing new abstractions.
3. Make surgical changes; do not refactor unrelated code.
4. Treat `PLAN.md` and `MCP_PROVIDER_STANDARD.md` as current architectural constraints unless explicitly superseded.
5. Keep CyberBrain independent from any single persona or client.
6. Preserve backward compatibility with active MeiLin data/contracts during migration unless a breaking change is explicitly approved.
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

## Implementation sequence

```text
audit → define boundaries → specify → extract deliberately → test → migrate
```

Do not copy the existing MeiLin source tree wholesale into CyberBrain as a shortcut.

## License

New CyberBrain source files should carry an SPDX identifier appropriate to their file format:

```text
SPDX-License-Identifier: MPL-2.0
```
