# Bounded reasoning contract

## Boundary

`BoundedReasoningEngine` is a deterministic library over caller-supplied typed relation snapshots.
Callers supply authorized edges; endpoint identity includes scope and semantic context. Derived
assertions remain proposed, carry original premise provenance, and require explicit review.
The engine neither reads storage nor grants canonical write authority.

## Contradictions

Polarity mismatch, structural contradiction and direct causal-cycle checks exclude rejected edges.
Both premises must have an overlapping validity interval; an end equal to the other start is
disjoint. Conflicts across different scoped endpoint identities are not merged.

`detect_contradictions` returns bounded findings only. An empty findings list is not a proof of
global consistency. Counterfactual evaluation exposes completeness explicitly and cannot conclude
consistent when its comparison or inference budget is exhausted.

## Inference

`max_depth` accepts 0 through 5 and counts original dependency edges along a path.
Depth 0 disables inference; symmetric contradiction requires depth 1 and a verified reverse-target
record anchor; dependency inference requires depth 2 or more. Paths cannot revisit an endpoint.

Each dependency conclusion retains all original premise IDs, the typed union of evidence, the
intersection of every premise's validity interval, and the final target's verified record ID.
Disjoint intervals produce no conclusion. More than 32 evidence references cannot be represented
by the relation schema: refuse the conclusion and mark sandbox evaluation incomplete rather than
truncate proof. Comparisons and total derived assertions obey the configured budgets at every hop.

## Counterfactual sandbox

The sandbox compares hypothetical edges against base edges and against one another, then derives
bounded conclusions in the combined snapshot. It makes no storage mutation. Returned inferences
are marked as counterfactual sandbox output, including conclusions already derivable from base
edges; the result is not a delta-only causal effect estimate.

`is_incomplete=true` always implies `is_consistent=false`. No automatic promotion, executive
scheduler or live reasoning hook is implied by this library contract.
