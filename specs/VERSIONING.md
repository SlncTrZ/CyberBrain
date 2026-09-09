# CyberBrain Versioning v1

CyberBrain versions three concerns independently:

```text
provider software version
MCP/tool contract version
schema version
```

## Provider software

Use semantic versioning once the first public/stable release exists.

`cyberbrain/_version.py` is the **single software/package version authority**. Do not duplicate the current software version in `pyproject.toml`, provider modules, CI, release workflows, README status text, or deployment scripts.

The Python build reads its dynamic version from that file. `cyberbrain.__version__`, MCP provider help, the bundled Reasoner provider, CI package metadata checks, and the expected Git release tag all derive from the same canonical value.

Current normative documentation must not duplicate a SemVer release literal. Historical release/version references belong under `docs/history/`; test fixtures may use version-shaped sample text only when the exact value is not treated as product state or authority.

## Tool contract

Contract changes are versioned independently from implementation releases.

Breaking MCP schema/semantic changes require an explicit contract-version increment and compatibility decision.

Backward-compatible additions such as a new optional parameter may remain within the same contract version when existing calls retain their meaning. The contract hash still changes and clients/gateways must treat that fingerprint drift as a reason to re-discover/synchronize the provider schema before continuing.

## Data schema

Current canonical Knowledge and Episodic payloads use:

```text
schema_version = 2
```

Historical schema V1 remains a migration/source format, not the current write contract. Schema migration must be explicit, preserve provenance/content/vector identity, fail if the source does not stabilize or staged target counts do not converge, and remain reversible or stage-before-cutover. Unmappable legacy records must be quarantined rather than silently dropped or normalized with fabricated metadata. The current schema-V2 procedure is `docs/V2_MIGRATION_RUNBOOK.md`.

Never infer schema solely from the provider software version.

## Embedding version

Embedding identity is tracked independently, e.g.:

```text
nomic-embed-text@v1
```

A model/dimension change requires an embedding migration plan. Do not mix incompatible vector dimensions in the same collection vector field.

## Help contract fingerprint

`cyberbrain.help` reports the running provider/contract/schema versions and a SHA-256 contract hash so clients/gateways can detect changes.
