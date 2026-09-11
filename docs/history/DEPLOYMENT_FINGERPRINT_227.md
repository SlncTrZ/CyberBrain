# CyberBrain Deployment Fingerprint — .227

> Historical operational record (measured snapshot, not current guidance).
> Purpose: make **drift detectable**. The authoritative deployment configuration and
> compose file live on the deployment host and are not tracked in this repository, so
> this file records what was actually measured instead of duplicating a file that would
> silently rot. Re-measure before relying on any value here.

## Scope

CyberBrain services on the Linux/Docker host `192.168.1.227` (`dinhtc@192.168.1.227`).
The host compose file also manages unrelated infrastructure (Qdrant, Ollama, nginx,
n8n, 9router, …); those services are out of scope for this record.

## Measured 2026-09-11 (Asia/Ho_Chi_Minh)

```text
deployment compose sha256      4e2f1ec649f1fa278dcdeccfc4a8765f75b10092f95b02dd5abb9461f16e0200
compose path                   /home/dinhtc/docker-all/docker-compose.yml
application image              cyberbrain:0.2.1
application image id           sha256:e6e03ff84c0b5c070ce6103c2632d2dc33bd88a1708ca5000e04dd5416d4df5b
application image created      2026-09-09T11:14:56+07:00
source authority               cyberbrain/_version.py = 0.2.1
deployed source                cyberbrain/ package byte-identical to repository commit 3e04ee6
                               (121/121 files matched by sha256)
build context                  /home/dinhtc/docker-all/cyberbrain-build
                               (refreshed to the recorded source; the previous stale
                               v0.1.7 copy was renamed aside, not deleted)
```

Containers (all `restart: unless-stopped`, restart count 0):

```text
cyberbrain                        Up, healthy
cyberbrain-dream-worker           Up, healthy
cyberbrain-dream-scheduler        Up
cyberbrain-dream-reasoner-router  Up, healthy
cyberbrain-reasoner               Up, healthy
```

Storage:

```text
live Knowledge collection      cyberbrain_knowledge_v2_stage   points 4937
live Episodic collection       cyberbrain_episodic_v2_stage    points 195
collections present            2
```

Runtime environment invariants (values, not secrets):

```text
CYBERBRAIN_REQUIRE_AUTH=true
CYBERBRAIN_TRUSTED_AGENT_ID=coding-agents
CYBERBRAIN_COGNITION_M3_M7_ENABLED=true
CYBERBRAIN_COGNITION_M6_AUTO_ACCEPT_ENABLED=true
CYBERBRAIN_COGNITION_M7_ACTUATION_ENABLED=true
CYBERBRAIN_EMBEDDING_VERSION=nomic-embed-text@v1
CYBERBRAIN_KNOWLEDGE_SEARCH_SCORE_THRESHOLD=0.55
```

Dependency images:

```text
qdrant    qdrant/qdrant:latest    sha256:057ee3a8da769fe7310dd3537b4dc7583bf87a95ce8ac43c0af5a46bc580d1fc
ollama    ollama/ollama:latest    sha256:b88c73ace3e115f8ec53dc8761ae1c0aabfa675406e3681786b98757ce050f42
```

Provider contract as served:

```text
provider_version          0.2.1
protocol_version          mcp-streamable-http
contract_version          1
schema_version            2
contract_hash             965ce2f9e5039338f57863eab461d0e1b8f1ceec3e3b7e3b65a8c52ea83e9b34
unauthenticated /mcp      rejected (authentication required)
```

## Re-measuring

```bash
ssh dinhtc@192.168.1.227 "sha256sum /home/dinhtc/docker-all/docker-compose.yml"
ssh dinhtc@192.168.1.227 "docker inspect cyberbrain:0.2.1 --format '{{.Id}}'"
ssh dinhtc@192.168.1.227 "docker ps --filter name=cyberbrain --format '{{.Names}}|{{.Image}}|{{.Status}}'"
ssh dinhtc@192.168.1.227 "docker exec cyberbrain sh -c 'env' | grep -E 'CYBERBRAIN_(REQUIRE_AUTH|TRUSTED_AGENT_ID|COGNITION|EMBEDDING_VERSION)' | sort"
```

Deployed-source equality can be re-measured without trusting this record:

```bash
# per-file sha256 of cyberbrain/*.py inside the container
ssh dinhtc@192.168.1.227 "docker exec cyberbrain sh -c 'cd /app && find cyberbrain -name \"*.py\" | sort | xargs sha256sum'"
# compare against the same computation in a clean checkout of the recorded commit
git -c core.autocrlf=false archive <commit> | tar -tzf - > /dev/null   # export, then hash-compare
```

## Drift policy

A mismatch between this record and the host is **information, not a defect to paper
over**. Re-measure, identify which change was intended, and update this record in the
same change that alters the deployment. Never edit this file to match an unexplained
runtime state, and never treat it as the source of truth for the host configuration.
