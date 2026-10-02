# CyberBrain Deployment Fingerprint — .227

> Historical operational record: measured deployment snapshot, not source guidance.
> Earlier measurements are retained below; re-measure before relying on this record.

## Measured 2026-10-02 — runtime-derived help reference

| Field | Measured value |
| --- | --- |
| Deployed source commit | 9313893582e25347d2b30d52fc7cfd2d4d500256 |
| Image tag | cyberbrain:git-9313893582e2 |
| Image ID | sha256:1b61c84659bce1d4d028ca248eb1082c8b165f465da973aa21c876c873d25a87 |
| Deployment completed (UTC) | 2026-10-02T08:01:50.859332+00:00 |
| Deployment Compose SHA256 | 9dd447e9d8a4ad8a4bb48aafbc5a318d88ad9a3980e0c73fcaab65112659e696 |
| Source equality | 140/140 Python files and TOOL_GUIDE.md SHA256 match in each of five containers |
| API / worker / scheduler / router / reasoner | All healthy; restart count 0 at rollout acceptance |
| Health / readiness / unauthenticated MCP | HTTP 200 / 200 / 401 |
| Authenticated provider catalog | 27 tools; all names retained |
| Direct authenticated help | PASS; 47976 UTF-8 bytes, runtime parameter tables, examples and recovery guide |
| Provider contract hash | b49ee7905d9d7ffc66a2aca0d0573252adf44aa0b57220c186a652a2fa4b6b1b |
| Gateway authenticated help | PASS, untruncated; same contract hash |
| Gateway configured / ready providers | 1 / 1 after graceful process recovery |
| Gateway manifest catalog | Existing 24 tools retained; three relation names remain outside this manifest |
| Production environment and mounts | Preserved; resolved Compose differs only in five image references |
| Previous rollback image | cyberbrain:git-48429e573009, retained |

Source acceptance and clean-image QA each passed 803 tests with one optional storage gate
skipped. Ruff and diff checks passed. The clean image suite emitted one Starlette test-client
deprecation warning; no test failure. No schema/data migration, relation proposal/review,
credential change, retention sweep or long-term evidence claim is part of this rollout.

The first rollout was reverted by a strict post-rollout preservation check after service
health passed. Final acceptance compares mount contents independently of array order;
the router's two unchanged mounts were returned in a different order. The prior image
remains available. No production snapshot restore was performed.

During provider interruption the gateway advertised zero extension tools despite the
provider being healthy. A graceful restart of the existing gateway process restored one
ready provider and the unchanged 24-tool manifest. Gateway policy, provider configuration
and credentials were not changed. Provider-local authenticated help and subsequent
gateway help both passed. This is recovery evidence, not a proven diagnosis of every
earlier intermittent provider_unavailable response.

The help fingerprint now covers the readable guide and the generated public-schema
reference, rather than the guide file alone. Guide SHA256 and runtime contract hash
therefore intentionally differ. The software/package version authority remains
cyberbrain/_version.py; no release or version bump was performed.

---

## Measured 2026-10-01 18:31 ICT — typed relations slices 5–6

| Field | Measured value |
| --- | --- |
| Implementation commit | bfacb8d6583c91d938aedef8bccb2b1c5bae9b3d |
| Deployed source commit, including catalog guide correction | 48429e5730095a251cbeae04194d0f826b242724 |
| Image tag | cyberbrain:git-48429e573009 |
| Image ID | sha256:21d476d242bec1e46b2be2ecef42bec6ac27833a3d2700d590f2170f2428f0f4 |
| Deployment Compose SHA256 | 92600555dde718ae42bb18869b243d75cd26443051b3ff9880ed42fd9102f694 |
| Package version derived from source authority | 0.2.1 |
| Python source equality / embedded guide equality | 139/139 files and guide SHA256 match in each of five containers |
| API / worker / scheduler / router / reasoner | All healthy, restart count 0 |
| Health / readiness / unauthenticated MCP | HTTP 200 / 200 / 401 |
| Authenticated provider catalog | 27 tools: all 24 existing tools retained, 3 relation tools added |
| Authenticated provider relation canary | 0 paths, 4 physical reads, 83 estimated tokens, no truncation |
| Gateway authenticated help | PASS after read-only provider_unavailable retry |
| Provider contract hash | 0bd0253ce7a5f01b5b5d8c1b421f4c4671d53004da878dcd73c79dcd605bb4fc |
| Caller relation flag / worker Dream relation flag | Enabled / enabled |
| Ordinary Knowledge retrieval mode | vector, preserved |
| Projection census | 5311 canonical Knowledge, 5311 eligible, missing 5311 → 0, assertions 0 |
| Knowledge total / Episodic points | 5312 (including one quarantine) / 1110 |
| Canonical collections present | Exactly two existing V2 stage-named collections |
| Queue snapshot | 495 processed, 2 historical failed jobs |
| Scheduler heartbeat age at measurement | 44.666 seconds; explicit heartbeat check passed |

The rollout changed only the five CyberBrain image references and two relation flags. Authentication,
identity, collection names, embedding settings, ordinary ranking mode and dependency services were
preserved. No assertions were inferred, proposed or accepted in production.

Before projection writes, canonical writers were stopped. Protected verified snapshots cover both
collections and all three existing operational SQLite files. The initial host-side metadata write
was denied by backup-directory permissions; old services resumed safely, metadata was subsequently
written through the operator container, and the unchanged canonical source hash was required
before application. API and worker exited cleanly; the waiting scheduler needed force-stop after
the 45-second timeout. All three SQLite quick checks passed and its post-upgrade heartbeat is fresh.

Canonical source hash before/after projection application:
`2c98a9d23622ffb5dd80450ac2095744d1043f7bd578a5d953370d4e63749d70`.
Independent complete-corpus payload/vector fingerprints, excluding only the disposable projection,
also matched before/after:

- Knowledge: `61b2381a97c370483308219d83c9ecff04e4cc5168e2411108007caf4307953f`.
- Episodic: `c02c3d114976563a47b20627a95b33e1f6568bde69f4aebb9b76dbc29f9e745c`.

The protected checkpoint and previous image are retained. Real isolated Qdrant exercised snapshot
restore/reapply and exact vector/payload preservation; no production snapshot rollback drill is
claimed. Feature rollback restores the prior image/flags while retaining subsequent canonical
work. Snapshot restore after writers resume requires separate authority because it can erase work.

Source acceptance: 799 default tests passed, one optional gate skipped in that run; the expanded
real isolated storage gate separately passed. Ruff/diff checks, wheel/sdist privacy and both
Docker builds passed. The final controlled 10-iteration benchmark matches the deployed Python
source hash; see [controlled benchmark](../benchmarks/RELATIONS_CONTROLLED.md). Synthetic
known-seed path correctness is separate from trained embedding accuracy and external competitors.

Provider-local tools are available and authenticated calls were verified. The current ChatGPT
connector session still advertises its previously discovered tool list; availability of the
three new names through a refreshed gateway/client catalog was not verified in this session.
Existing gateway help continued to work.

Zero production assertions means the canary demonstrates availability, not positive-path quality
or long-term usefulness. Day-30/day-60 evidence remains outside source acceptance.

---

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
