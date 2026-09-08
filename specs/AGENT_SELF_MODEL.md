# CyberBrain Agent Self-Model Specification v1

> Status: M6 readiness contract implemented; hypothesis generation and persistent/influential behavior are not yet authorized.

## Purpose

Agent Self-Model owns revisable, evidence-backed hypotheses about one trusted agent's recurring capabilities, limitations, workflow tendencies, and strategy constraints.

It does **not** own identity truth, authorization, tool policy, routing, prompt mutation, Knowledge truth, or autonomous strategy mutation.

## Safety invariants

```text
self-model hypothesis != identity truth
calibration label != self-model belief
one success/failure != recurring capability/limitation
recorded agent string != trusted runtime identity
working-memory state != self-model evidence
```

Every Self-Model decision is downstream of trusted agent identity and prospective evidence.

## Trusted identity boundary

Current source can bind `TrustedIdentityEvidence` only after MCP Bearer/X-API-Key authentication succeeds and only from a server-configured `CYBERBRAIN_TRUSTED_AGENT_ID`. Caller-supplied identity headers or tool arguments do not create trusted identity.

When trusted agent identity is bound, Prediction Learning MCP operations are constrained to that agent:

- `prediction_record` attributes the Prediction to the trusted agent and rejects a conflicting payload `agent`;
- `prediction_observe`, `prediction_pending`, and `calibration_observe` force the trusted agent filter and reject cross-agent substitution;
- `prediction_resolve` requires the referenced Prediction to belong to the trusted agent before writing an Outcome.

This binding is intentionally separate from broader `CallerAuthority`. `single_owner` remains the only enabled deployment mode. `agent_ready` and `multi_user` remain fail-closed until full P3 read/write/background isolation and persisted identity requirements are complete.

## E2 prospective outcome census

`benchmarks/evidence/outcome_readiness.py` is the read-only E2 evidence census.

Eligible pairs require canonical records with:

```text
source = cognitive_prediction
→ matching canonical prediction_id
→ finite prior confidence in [0,1]
→ outcome source = cognitive_outcome
→ outcome time >= prediction time
→ inherited session / agent / project / topic identity unchanged
→ expected outcome and prior confidence unchanged
```

Malformed, identity-substituted, retrospective, or orphaned records are excluded. Ordinary prose containing words such as "Prediction" or "Outcome" is never reconstructed into causal evidence. Historical prediction backfill candidates remain exactly zero by design.

E2 reports evidence IDs and outcome classes without pre-labeling records as Self-Model support or counterexamples. Support/counterexample semantics exist only relative to a specific hypothesis.

## M6.0 readiness gate

`SelfModelReadinessEvaluator` is deterministic and read-only. Its default conservative entry policy is:

```text
trusted agent identity       required / exact agent match
resolved prospective outcomes >= 20
 distinct sessions             >= 3
 distinct topics               >= 3
 evidence scan                 complete
```

The 20-outcome floor deliberately matches the current first Calibration review checkpoint so M6 does not use a weaker sample floor than the existing metacognition layer. This does not make Calibration an identity system and does not imply that 20 outcomes automatically justify a hypothesis.

Failure of any gate returns:

```text
insufficient_evidence
```

Passing all gates returns only:

```text
ready_read_only
```

`ready_read_only` authorizes evaluation work only. It does not authorize persistence, prompt changes, strategy mutation, routing changes, permission changes, or Knowledge writes.

## Hypothesis contract

A future read-only M6 hypothesis uses `SelfModelHypothesis` and must contain:

- stable hypothesis ID;
- exact trusted agent ID;
- bounded kind: capability, limitation, workflow tendency, strategy constraint, or uncertain capability;
- explicit claim text;
- supporting evidence IDs;
- counterexample evidence IDs;
- confidence in `[0,1]`;
- sample count;
- evidence diversity;
- timezone-aware review time;
- explicit reason codes;
- contract version.

Supporting and counterexample IDs must remain unique and non-overlapping inside one hypothesis. Every claim remains revisable.

## Current authority boundary

Current source contains:

```text
P3.1 trusted authenticated agent context
+ Prediction Learning trusted-agent attribution/isolation
+ E2 prospective outcome census
+ M6 hypothesis/readiness domain contracts
```

Current source does **not** contain:

```text
M6 hypothesis generator
M6 persistence
M6 automatic Working Memory influence
M6 prompt/strategy/tool/routing mutation
agent_ready deployment activation
multi_user deployment activation
full P3 search/write/background isolation
```

The correct current result for an immature or untrusted evidence sample is safe incompleteness, not a lowered gate.
