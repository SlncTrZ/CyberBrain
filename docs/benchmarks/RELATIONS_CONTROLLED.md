# Controlled relation retrieval benchmark

Measured 2026-10-01 on isolated Qdrant 1.19.0, 1006 comparison points, 10 measured iterations after one warm-up. Inputs are known seed IDs; baselines receive the same seed text. All modes use K=8, a 4096-token context budget and 256-token record text budget. Runtime-default pooled HTTP transport is used.

| Case | Vector Recall@8 / P95 ms | Hybrid Recall@8 / P95 ms | Relations Recall@8 / P95 ms | Relation reads / context tokens |
| --- | --- | --- | --- | --- |
| Current outgoing | 0 / 102.368 | 0 / 494.178 | 1 / 257.986 | 7 / 765 |
| Current reverse | 0.5 / 123.909 | 0.5 / 609.658 | 1 / 225.133 | 7 / 764 |
| Direct outgoing | 0 / 115.590 | 0 / 635.135 | 1 / 176.198 | 5 / 394 |
| Lexical control | 0 / 111.748 | 1 / 556.191 | 1 / 168.929 | 5 / 394 |
| Historical outgoing | Unsupported | Unsupported | 1 / 227.692 | 7 / 1307 |

Relation path precision and recall are 1 in every curated case; no off-gold records were returned. The report's contamination metric means returned records outside the gold set, not a tenant leakage rate. Conservative depth truncation is reported even when the finite gold paths are all found. Historical ordinary search is unsupported and excluded rather than scored zero.

Fanout 1, 8 and 64 returns all reviewed paths with five physical storage reads; fanout 64 uses 15330 tokens under a separate 16384-token stress budget. Fanout 256 exceeds the bounded candidate phase: three reads, zero arbitrary partial paths and explicit candidate_capacity truncation.

These deterministic synthetic 3D distances and labels test structural retrieval, version/time handling and bounded execution. They do not estimate trained embedding accuracy, query-to-seed resolution, semantic entailment, external competitor quality or production usefulness. A seed graph favors structural retrieval by construction. Longitudinal live evidence remains outside source acceptance.

Reproduce with scripts/benchmark_relations.py against a new empty loopback Qdrant. Machine-readable results, exact fixture and source tree hashes: [RELATIONS_CONTROLLED_2026-10-01.json](RELATIONS_CONTROLLED_2026-10-01.json).
