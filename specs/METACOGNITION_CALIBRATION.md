# Metacognition / Calibration Specification v1

> Status: Initial read-only cognitive mechanism.
> Dependency: Prediction / Outcome / Prediction Error.

## Purpose

This mechanism lets CyberBrain analyze whether an agent's prior confidence is systematically higher
or lower than the outcomes represented by resolved Prediction Learning evidence.

It is a read-only analysis layer.

It does not create a self-model, rewrite prompts, change strategy, write Knowledge, or claim that
an agent has a stable psychological trait.

## Evidence source

Calibration consumes resolved Prediction Learning pairs.

For each Prediction, only the latest linked Outcome is used.

Indeterminate Outcomes are excluded from usable calibration samples.

The initial empirical mapping is deliberately explicit:

    confirmed            -> 1.0
    partially_confirmed  -> 0.5
    contradicted         -> 0.0
    indeterminate        -> excluded

This mapping is an engineering convention for the first calibration primitive. It is not a claim
that every real-world outcome has an objectively correct scalar value.

## Canonical operation

Read-only MCP operation:

    calibration_observe

Optional filters:

    session_id
    agent
    project
    topic
    limit
    minimum_samples
    bias_threshold

Default policy:

    limit = 1000
    minimum_samples = 20
    bias_threshold = 0.1

## Report

The report contains:

    usable_samples
    excluded_indeterminate
    minimum_samples
    mean_confidence
    mean_empirical_score
    calibration_bias
    mean_squared_calibration_error
    assessment
    bias_threshold
    may_be_incomplete
    filters

Calibration bias is:

    mean(prediction_confidence - empirical_score)

Interpretation:

    positive bias -> confidence above observed empirical score
    negative bias -> confidence below observed empirical score

The squared calibration error is:

    mean((prediction_confidence - empirical_score)^2)

It measures mismatch magnitude and is not itself a truth score.

## Minimum evidence gate

The mechanism must not classify calibration from too little evidence.

If:

    usable_samples < minimum_samples

then:

    assessment = insufficient_evidence

even when the numerical bias is large.

When enough samples exist:

    bias > bias_threshold
        -> overconfident

    bias < -bias_threshold
        -> underconfident

    otherwise
        -> roughly_calibrated

These labels describe the selected evidence sample only. They are not permanent agent identity
claims.

## Truncation

Prediction Learning reads are bounded.

If the upstream Prediction or Outcome scan reaches the configured limit:

    may_be_incomplete = true

Callers must not treat the report as a complete calibration history in that case.

## Safety and ownership

This mechanism is read-only.

It may not:

- write or evolve canonical Knowledge;
- create or mutate Episodic Memory;
- alter Prediction or Outcome records;
- write a persistent agent self-model;
- change prompts, tools, model/provider routing, or task policy;
- automatically promote a calibration label into a strategy rule.

The distinctions remain:

    confidence != truth
    calibration assessment != identity truth
    repeated error != causal explanation

## Relationship to Dreaming

Dreaming may already consume the underlying Prediction and Outcome Episodes as evidence.

Calibration reports are summaries over that evidence. They should not replace the source Episodes as
provenance for any future learned lesson.

If future Dreaming integration uses calibration summaries, the underlying Prediction/Outcome IDs or
equivalent source evidence must remain traceable.

## Non-goals

This version does not:

- compute per-confidence-bin reliability diagrams;
- infer causal reasons for miscalibration;
- compare models/providers;
- automatically tune confidence values;
- maintain a long-lived self-belief such as "agent X is overconfident";
- implement Salience / Attention.

Those require separate evidence and specifications.

## Observation requirement

Before Salience / Attention becomes active development, observe:

- how quickly samples accumulate by agent/project/topic;
- whether the confirmed/partial/contradicted mapping is useful enough;
- whether minimum_samples=20 is too low or too high;
- whether aggregate bias hides important domain-specific patterns;
- whether may_be_incomplete becomes common at real data volume;
- whether calibration reports correlate with useful Dreaming lessons.

Later changes should be driven by these observations rather than by anthropomorphic assumptions.
