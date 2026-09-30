# CyberBrain Deployment Fingerprint — .227

> Historical operational record: measured deployment snapshot, not source guidance.
> Earlier measurements are retained below; re-measure before relying on this record.

## Measured 2026-09-30 17:04 ICT

| Field | Measured value |
| --- | --- |
| Source commit | 1f15ee6fc08d6243ba1cddb3d380a9e9a45f10ad |
| Image tag | cyberbrain:git-1f15ee6fc08d |
| Image ID | sha256:c8aa573ce1fd54bd3e0ceee2392eebfae9ac280abe2dc624f737b27bc45f1da5 |
| Deployment Compose SHA256 | 58d97c7bcdca0b83bc11bd7c033c1f5dce253f5bbc0258dda3ac4f39d1e0b54f |
| Package version derived from source authority | 0.2.1 |
| Python source equality | 127/127 files in each of five containers |
| API / worker / scheduler / router / reasoner | All healthy |
| Health / readiness | HTTP 200 / 200 |
| Unauthenticated MCP | HTTP 401 |
| Gateway authenticated help | PASS after read-only retry |
| Provider contract hash | 7d7e80e04eed4e5e8512ea8ffdc0afde8db763dd6cad7afa364c8a32884b38fd |
| Knowledge / Episodic points | 5311 / 1110 |
| Canonical collections present | Exactly two, existing V2 stage-named collections |
| Queue after operational schema upgrade | 443 processed, 2 failed historical jobs |
| Scheduler heartbeat | Fresh waiting; completed-run evidence not yet present |

The rollout used the already validated image with an immutable source-commit tag. It changed
only five CyberBrain services and added the scheduler heartbeat healthcheck. Existing auth,
trusted identity, default mode, cognition flags, collection names and dependency services were
preserved. No broader-mode configuration, review resolution or semantic migration occurred.
Before quiesced upgrade, both Qdrant collections and all three existing operational SQLite
files were backed up with verified checksums. Previous image and Compose were retained;
production rollback was not executed or drilled.

The live evaluation window starts with this actual rollout. Day-30/day-60 observations are
separate from source acceptance and do not become proof merely because calendar time elapsed.
Read-only smoke checks establish deployment availability, not long-term learning usefulness.

---

## Earlier deployment measurement

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
