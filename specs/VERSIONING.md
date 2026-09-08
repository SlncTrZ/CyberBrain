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

Historical release/version references in documentation or test fixtures are evidence/examples only; they are not version authorities.

## Tool contract

Contract changes are versioned independently from implementation releases.

Breaking MCP schema/semantic changes require an explicit contract-version increment and compatibility decision.

Backward-compatible additions such as a new optional parameter may remain within the same contract version when existing calls retain their meaning. The contract hash still changes and clients/gateways must treat that fingerprint drift as a reason to re-discover/synchronize the provider schema before continuing.

## Data schema

Canonical knowledge and episodic records start with:

```text
schema_version = 1
```

Schema migration must be explicit and reversible where practical.

Never infer schema solely from the provider software version.

## Embedding version

Embedding identity is tracked independently, e.g.:

```text
nomic-embed-text@v1
```

A model/dimension change requires an embedding migration plan. Do not mix incompatible vector dimensions in the same collection vector field.

## Help contract fingerprint

`cyberbrain.help` reports the running provider/contract/schema versions and a SHA-256 contract hash so clients/gateways can detect changes.
