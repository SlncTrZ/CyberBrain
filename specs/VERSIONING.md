# CyberBrain Versioning v1

CyberBrain versions three concerns independently:

```text
provider software version
MCP/tool contract version
schema version
```

## Provider software

Use semantic versioning once the first public/stable release exists.

Initial development starts at:

```text
0.1.0
```

## Tool contract

Contract changes are versioned independently from implementation releases.

Breaking MCP schema/semantic changes require an explicit contract-version increment and compatibility decision.

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
