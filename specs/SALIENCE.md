# Salience / Priority Specification v1

## Purpose

Salience answers one bounded question:

> How worthy of attention is this already-authorized evidence item, given explicit signals?

Salience is advisory. It does not establish truth, authorization, persistence, Knowledge promotion,
retrieval eligibility, Working Memory membership, forgetting, or model strategy.

## Canonical signal vocabulary

The canonical M3 signal names are:

```text
prediction_error
unresolvedness
contradiction
novelty
recurrence
consequence
user_emphasis
recency
```

Every supplied signal must be finite and bounded to `[0.0, 1.0]`. Missing means unknown. Missing
signals are never inferred, imputed, or converted into fabricated evidence by the scorer.

### Signal derivation contract

The scorer consumes already-derived signals. Upstream callers own evidence derivation and must make
that derivation explicit and testable:

- `prediction_error` — deterministic mismatch magnitude from a genuine pre-outcome Prediction and a
  later Outcome; never retrospectively fabricated;
- `unresolvedness` — explicit open-loop/unresolved state, not a prose guess;
- `contradiction` — explicit contradiction/conflict evidence or a reviewed deterministic
  classification, not semantic suspicion;
- `novelty` — measured novelty against a declared comparison set/window;
- `recurrence` — measured recurrence over a declared set/window, preferably distinct occurrences;
- `consequence` — explicit bounded impact/consequence evidence under a declared mapping;
- `user_emphasis` — explicit user-provided priority/emphasis only; agent inference must not masquerade
  as user emphasis;
- `recency` — deterministic bounded value from an explicit reference time/window.

A caller that cannot justify a signal must omit it.

## Generic scoring algorithm

`SalienceScorer` performs a deterministic weighted mean over present signals whose configured weight
is positive:

```text
score = sum(weight_i * signal_i) / sum(weight_i)
```

Only present, positive-weight signals enter the denominator. If no active signal exists, score is
`0.0`.

The generic `SalienceConfig()` remains equal-weight and algorithm-neutral. It is not the reviewed
CyberBrain attention policy.

## Reviewed CyberBrain policy

The source-level reviewed policy is `salience-policy-v1`:

| Signal | Weight |
|---|---:|
| prediction_error | 2.0 |
| unresolvedness | 1.5 |
| contradiction | 2.0 |
| novelty | 0.5 |
| recurrence | 1.0 |
| consequence | 2.0 |
| user_emphasis | 1.5 |
| recency | 0.5 |

Policy rationale:

- prediction error, contradiction, and consequence are material learning/correctness evidence;
- unresolved state and explicit user emphasis deserve elevated attention;
- recurrence is useful corroboration;
- novelty and recency are weak signals and must not dominate material evidence by themselves.

Changing these policy weights requires benchmark evidence and a new policy contract identifier when
semantics materially change. The generic scoring formula does not need to change when policy weights
change.

## Assessment output

`SalienceAssessment` contains:

```text
score
reason_codes
normalized_signals
assessment_version
```

Reason codes are content-free and stable. A reason is emitted only when its corresponding signal is
present, positively weighted, and greater than zero.

The assessment contract identifier is `salience-assessment-v1`.

## Authorization boundary

Authorization is stronger than Salience.

The bounded advisory seam accepts `SalienceCandidate` values only after upstream authorization has
already established candidate visibility. Each candidate includes a content-free `scope_marker`.
All candidates in one advisory call must share exactly one scope marker; cross-scope candidate sets
fail closed before scoring.

Required ordering:

```text
authentication
→ trusted caller authority
→ hard storage/data eligibility
→ candidate construction
→ task relevance where applicable
→ Salience advisory
→ bounded downstream Concept/Working-Memory/Lifecycle use
```

Salience score must never broaden scope or turn an ineligible record into an eligible one.

## Shadow observation

`SalienceShadowObserver` is metrics-only. It:

- receives already-authorized, same-scope candidates;
- computes advisory scores/order;
- records numeric/content-free metrics;
- leaves the caller-owned candidate order untouched;
- has no storage, network, model, Knowledge-write, or retrieval-reranking authority.

The controlled benchmark remains source-level acceptance evidence. In production, Salience is now
wired **after** canonical authorization/search eligibility over a bounded vector prefetch. It may
change the order/selection of those already-visible candidates but cannot create eligibility, widen
scope, or replace the canonical vector retrieval backend.

## Bounded integration seam

`SalienceAdvisor` is the accepted M3 integration point. Concept Formation and Working Memory consume this bounded same-scope advisory seam, and the implemented M7 Memory Lifecycle contract may consume an already-derived bounded Salience score as one retention signal. Lifecycle semantics remain owned by M7; Salience cannot suppress/delete/reactivate a record by itself.

It may provide an advisory priority order over an already-authorized candidate set. Downstream
mechanisms must keep their own decision semantics:

- Concept Formation owns abstraction identity/evidence;
- Working Memory owns task relevance and bounded active-set membership;
- Memory Lifecycle owns reversible retention/suppression/reactivation policy and may use Salience only as one bounded downstream signal. See `MEMORY_LIFECYCLE.md`.

None may reinterpret Salience as truth.

## Benchmark acceptance

The fixed initial benchmark contains:

```text
28 total pairwise cases
24 scored cases
2 intentionally ambiguous cases
2 cross-scope not-comparable cases
```

Trivial baseline best pairwise accuracy is `0.583333`.

The reviewed policy produces:

```text
pairwise accuracy     1.0
Tie accuracy          1.0
boundary safety       1.0
```

The equal-weight generic scorer previously produced `0.791667`, exposing five reviewed disagreements
concentrated around contradiction versus recurrence/recency, novelty versus consequence, and
consequence versus recency. Fixture expectations were not changed to improve the scorer. The reviewed
policy encodes the pre-declared semantic rule that material evidence outranks novelty/recency and
resolves those cases.

This fixture is synthetic-but-realistic acceptance evidence, not production outcome evidence.

## Non-goals

M3 does not add:

- another durable collection;
- a persistent Salience store;
- an MCP Salience tool;
- an LLM classifier;
- retrieval eligibility creation or pre-authorization reranking;
- automatic Knowledge mutation;
- direct Dreaming integration;
- task-context persistence;
- cross-scope comparison;
- autonomous strategy changes.

## M3 completion boundary

M3 source development is complete when:

- deterministic scorer and reviewed policy are implemented;
- canonical signal vocabulary and derivation rules are documented;
- benchmark evidence beats trivial baselines without modifying expected labels to fit the scorer;
- shadow/advisor paths preserve input behavior and fail closed across scope boundaries;
- full regression and lint/integrity gates pass;
- active runtime integration occurs only after existing authorization/search eligibility and preserves scope boundaries.
