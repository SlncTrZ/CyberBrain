# Schema V2 Migration Runbook

> Status: Current operational runbook for staging and validating the schema-V2 corpus.
> This runbook does **not** authorize production cutover. Cutover/restart/deployment still requires explicit owner approval.

## Purpose

Migrate the complete CyberBrain Qdrant corpus into validated schema-V2 stage collections without losing point IDs, content, vectors, provenance, or historically ambiguous records.

The migration source is the union of:

```text
cyberbrain_knowledge_v1_stage
cyberbrain_episodic_v1_stage
cyberbrain_knowledge          # raw/current legacy delta source
cyberbrain_episodic           # raw/current legacy delta source
```

Do not copy only the V1 stage. The latest read-only census used to design this migration found 25 raw IDs absent from the V1 stage and 5,083 unique IDs across the four source collections. **5,083 is an observed checkpoint, not a hard-coded invariant**: rerun the source census immediately before staging because the live sources may have changed.

Target stage collections are:

```text
cyberbrain_knowledge_v2_stage
cyberbrain_episodic_v2_stage
```

## Safety invariants

The migration must preserve these rules:

```text
source union == target union
Knowledge target IDs ∩ Episodic target IDs == ∅
point ID preserved
vector preserved
normalized content preserved
schema_version == 2
historical agent strings != authenticated identity
unmappable legacy record != dropped record
quarantine != ordinary recall
self_model_hypothesis != ordinary recall
source change during stage != successful convergence
extra/stale target record != successful convergence
```

Malformed or unmappable legacy records are preserved as `record_class=migration_quarantine`, `ordinary_recall=false`, and `lifecycle_state=suppressed`; never invent missing session/identity metadata merely to make a record parse as canonical Episodic Memory.

## Preconditions

Before staging:

1. Work from a reviewed source commit/working tree with migration tests green.
2. Do not mutate the production collection configuration.
3. Ensure `QDRANT_URL` points to the intended Qdrant endpoint and set `QDRANT_API_KEY` only when required by that endpoint.
4. Confirm all four source collections exist.
5. Confirm there is enough storage for two additional V2 stage collections.
6. Choose a timestamped local report directory. Reports may contain IDs/counts and are operational evidence; do not place secrets in them.
7. If `cyberbrain_knowledge_v2_stage` or `cyberbrain_episodic_v2_stage` already exists from a prior failed/obsolete attempt, do not assume it is safe. Either independently validate it against the current source union or remove/recreate it only with explicit owner approval.

Recommended environment:

```bash
export QDRANT_URL='<reviewed-qdrant-url>'
export QDRANT_API_KEY='...'                  # omit/unset when not required
RUN_DIR="migration_artifacts/$(date +%Y-%m-%d)/v2-stage-$(date +%H%M%S)"
mkdir -p "$RUN_DIR"
```

Never print or commit the API key.

## 1. Source preflight / census

Before writing any target stage, establish the current union counts. The migration tool itself recomputes and verifies source-union coverage; retain a separate read-only census/report when operating against production data.

At minimum record:

```text
knowledge_v1_stage count
episodic_v1_stage count
raw knowledge count
raw episodic count
unique four-source union count
raw IDs absent from primary V1 stage
```

If the observed union differs from the historical 5,083-ID checkpoint, use the newly observed value and investigate the delta; do not force the corpus back to 5,083.

## 2. Stage schema V2

Run the stage tool from the repository root:

```bash
python scripts/stage_v2_migration.py \
  --knowledge-primary cyberbrain_knowledge_v1_stage \
  --episodic-primary cyberbrain_episodic_v1_stage \
  --knowledge-raw cyberbrain_knowledge \
  --episodic-raw cyberbrain_episodic \
  --knowledge-target cyberbrain_knowledge_v2_stage \
  --episodic-target cyberbrain_episodic_v2_stage \
  --max-passes 3 \
  --report "$RUN_DIR/stage-report.json"
```

The stage tool is fail-closed. Success requires all of:

```text
source fingerprint before == source fingerprint after
source fingerprint includes IDs + payloads + vectors
target Knowledge count == expected mapped Knowledge count
target Episodic count == expected mapped Episodic count
source union == target union during mapping
zero Knowledge/Episodic target ID overlap
all staged payloads parse as schema V2
```

If source collections continue changing or target counts do not converge within `--max-passes`, staging exits non-zero. Do not proceed to cutover.

## 3. Independent validation

A successful staging report is necessary but not sufficient. Run the independent validator against the same source and target collections:

```bash
python scripts/validate_v2_migration.py \
  --knowledge-primary cyberbrain_knowledge_v1_stage \
  --episodic-primary cyberbrain_episodic_v1_stage \
  --knowledge-raw cyberbrain_knowledge \
  --episodic-raw cyberbrain_episodic \
  --knowledge-target cyberbrain_knowledge_v2_stage \
  --episodic-target cyberbrain_episodic_v2_stage \
  --report "$RUN_DIR/validation-report.json"
```

Validator success requires:

```text
target union == current four-source union
zero target Knowledge/Episodic overlap
all target payloads parse as canonical V2
vector equality to source
normalized content equality to source
pre-P3 cognitive evidence not retroactively authenticated
migration quarantine hidden from ordinary recall
self-model hypothesis hidden from ordinary recall
all malformed raw Episode deltas represented by quarantine or stricter preservation
```

Any validator failure blocks the migration gate.

## 4. Review migration metadata quality

After independent validation and before canary/cutover, produce a read-only metadata census over the V2 stage. Review at least:

```text
schema_version distribution
Knowledge record_class distribution
identity_trust distribution
lifecycle_state distribution
ordinary_recall true/false counts
migration_quarantine count + reasons
self_model_hypothesis count
project/topic/session completeness where applicable
pre-P3 Prediction/Outcome trust state
```

Do not "clean up" quarantine or legacy-untrusted records by inventing values. Remediation must preserve provenance and be a separate reviewed transform.

## 5. Canary against V2 stage

`config/docker-compose.v2-canary.example.yml` is the tracked deployment-neutral V2-stage canary example. It intentionally requires an explicit image and external network so an old image or private topology cannot be reused silently.

Example:

```bash
export CYBERBRAIN_CANARY_IMAGE='cyberbrain:<reviewed-source-image>'
export CYBERBRAIN_CANARY_NETWORK='<reviewed-external-network>'
export CYBERBRAIN_CANARY_QDRANT_URL='<reviewed-qdrant-url>'
export CYBERBRAIN_CANARY_EMBEDDING_URL='<reviewed-embedding-url>'
export CYBERBRAIN_MCP_AUTH_TOKEN='...'
export CYBERBRAIN_QDRANT_API_KEY='...'
docker compose -f config/docker-compose.v2-canary.example.yml config >/dev/null
docker compose -f config/docker-compose.v2-canary.example.yml up -d cyberbrain-canary
```

The canary publishes only loopback port `8768`, uses a named local data volume, requires an explicit external network name, and reads:

```text
cyberbrain_knowledge_v2_stage
cyberbrain_episodic_v2_stage
```

Canary acceptance should include:

```text
/health
/ready
authenticated MCP help/catalog
compact + exact Knowledge recall
compact + exact Episodic recall
Prediction observe/pending on trusted/untrusted evidence boundaries
ordinary recall excludes quarantine/self_model_hypothesis/suppressed records
no cross-scope widening
no unexpected write during read-only validation
```

Stop the canary after the acceptance window unless owner explicitly requests otherwise.

## 6. Real-corpus cognitive evaluation

Only after V2 stage validation should the current program run:

```text
M6 trusted-evidence census / hypothesis review
M7 full-corpus shadow lifecycle evaluation
integrated M3→M7 assessment
```

M6 may correctly return `insufficient_evidence`; do not lower thresholds. M7 remains shadow-only until false-suppression/reactivation and useful-recall impact are reviewed.

## 7. Production cutover gate

Production cutover is **not** performed by the staging or validation scripts.

Cutover requires explicit owner authorization after:

```text
stage PASS
independent validator PASS
metadata census reviewed
canary PASS
M6/M7 real-corpus evaluation reviewed as required by the active Master Plan
rollback target recorded
production image/source checkpoint recorded
```

Prefer a reversible deployment configuration change that points all CyberBrain components which read/write canonical collections to the V2 stage names. Core API, Dream worker, Dream scheduler, backup jobs, and any other storage consumers must agree on the same collection pair; do not cut over only one process.

## 8. Rollback

Before cutover record the exact prior image and collection configuration.

Rollback means restoring **both** canonical collection settings to the prior pair and restoring the prior reviewed image/config when required. Do not merge V2-stage writes back into legacy collections ad hoc.

After rollback verify:

```text
all CyberBrain services healthy
/ready passes
canonical recall works against prior collections
Dream scheduler/worker point to the same prior Episodic collection
no mixed collection pair remains
```

Stage collections and migration reports should be retained until the acceptance window is closed and the owner authorizes cleanup.

## 9. Evidence to retain

Keep, at minimum:

```text
source census
stage-report.json
validation-report.json
metadata-quality census
canary acceptance report
M6 real-evidence report
M7 shadow report
cutover/rollback record if cutover occurs
```

Deployment-specific evidence belongs in private/operational storage or dated historical documentation as appropriate. Do not put secrets, private hostnames, or credentials into public tracked documentation.

## Stop conditions

Stop and investigate rather than proceeding when any of these occurs:

```text
source fails to stabilize
target counts fail to converge
source/target union mismatch
vector/content mismatch
Knowledge/Episodic ID overlap
schema V2 parse failure
pre-P3 evidence becomes authenticated
quarantine becomes ordinary-recall visible
unexpected large quarantine increase
canary authorization or recall regression
M7 false-suppression evidence exceeds accepted bound
```
