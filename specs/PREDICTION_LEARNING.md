# Prediction / Outcome / Prediction Error Specification v1

> Status: Initial cognitive learning mechanism.
> Scope: Episodic learning evidence only.

## Purpose

This mechanism lets an agent record what it expected before an action or decision, then later
record what actually happened.

CyberBrain stores both records as canonical Episodic Memory and derives a bounded prediction-error
signal without treating either the prediction or the caller's assessment as canonical truth.

This mechanism does not implement metacognition, salience, self-modeling, or automatic strategy
changes. Those are separate roadmap stages.

## Invariants

- Prediction and Outcome are canonical Episode records in cyberbrain_episodic.
- No third cognitive or learning collection is introduced.
- A Prediction has one immutable Episode ID that is also its prediction_id.
- An Outcome references the Prediction by prediction_id.
- Outcome session/agent/project/topic identity is inherited from the Prediction rather than supplied
  again by the caller.
- Prediction confidence is bounded to 0..1.
- Assessment is explicit and finite; CyberBrain does not ask an LLM to infer it inside the storage
  layer.
- Prediction error is a learning signal, not truth confidence.
- Prediction/Outcome records have no direct Knowledge write authority.
- Dreaming may use these Episodes as evidence through the existing provenance and promotion gates.

## Prediction record

Canonical MCP operation:

    prediction_record

Required input:

    expected_outcome
    confidence
    session_id
    event_time

Optional input:

    action
    rationale
    channel
    agent
    project
    topic
    keywords
    importance

The stored Episode uses:

    source = cognitive_prediction

and contains:

    context.cognition.kind = prediction
    context.cognition.prediction_id = <Episode id>
    context.cognition.expected_outcome = <expected outcome>
    context.cognition.confidence = <0..1>

Optional action/rationale values remain inside the same cognition context.

## Outcome record

Canonical MCP operation:

    prediction_resolve

Required input:

    prediction_id
    observed_outcome
    assessment
    event_time

Allowed assessment values:

    confirmed
    partially_confirmed
    contradicted
    indeterminate

The referenced Episode must be a valid canonical Prediction. Resolving an arbitrary Episode as a
Prediction fails explicitly.

The stored Outcome Episode uses:

    source = cognitive_outcome

and inherits the Prediction's:

    session_id
    channel
    agent
    project
    topic
    keywords
    importance

Its cognition context contains at least:

    kind
    prediction_id
    expected_outcome
    prediction_confidence
    observed_outcome
    assessment
    prediction_error_class
    confidence_weighted_error

## Deterministic prediction-error signal

CyberBrain derives the first version of prediction error as:

    confirmed:
      prediction_error_class = none
      confidence_weighted_error = 0

    partially_confirmed:
      prediction_error_class = partial
      confidence_weighted_error = prediction_confidence * 0.5

    contradicted:
      prediction_error_class = full
      confidence_weighted_error = prediction_confidence

    indeterminate:
      prediction_error_class = indeterminate
      confidence_weighted_error = null

This value is deliberately simple and transparent. It does not measure semantic distance between
the expected and observed outcomes.

A high-confidence contradicted prediction therefore produces a larger calibration signal than a
low-confidence contradicted prediction, but it still does not prove why the prediction failed.

## Observation interface

Canonical read-only MCP operation:

    prediction_observe

Optional filters:

    session_id
    agent
    project
    topic
    limit

The observation summary reports:

    predictions_total
    outcomes_total
    resolved_predictions
    unresolved_predictions
    duplicate_outcomes
    mean_prediction_confidence
    mean_confidence_weighted_error
    assessment_counts
    error_class_counts
    may_be_truncated
    sample_limit
    filters

When more than one Outcome references the same Prediction, observation metrics use the latest Outcome for assessment/error distributions so calibration-like signals are not double-counted. Extra Outcomes are reported separately through duplicate_outcomes.

The summary is descriptive only. It does not classify an agent as overconfident/underconfident and does not write Knowledge.

## Dreaming integration

Prediction and Outcome Episodes already flow through canonical episodic retrieval.

Dreaming evidence preserves context.cognition metadata, allowing later reasoning to distinguish:

- what was expected;
- prior confidence;
- what was observed;
- how the caller assessed the relation;
- the deterministic prediction-error signal.

Dreaming may derive evidence-backed lessons from repeated Prediction/Outcome pairs, but those
lessons still pass the standard evidence, review, provenance, and Knowledge Evolution gates.

## Non-goals

This mechanism does not:

- infer assessment automatically;
- decide whether an agent is generally overconfident;
- assign salience;
- mutate an agent self-model;
- automatically change prompts or strategy;
- delete or rewrite the original Prediction;
- claim that confidence_weighted_error is a neurological prediction-error model.

Those behaviors require separate specifications and evidence before implementation.

## Observation requirement

Before Metacognition / Calibration becomes active development, real usage should establish:

- whether agents reliably record predictions before consequential actions;
- whether assessment categories are expressive enough;
- whether callers overuse indeterminate or partially_confirmed;
- whether the error signal helps Dreaming discover reusable lessons;
- whether duplicate or long-horizon outcomes need stronger lifecycle rules.

Any schema expansion should be driven by those observations rather than added speculatively.
