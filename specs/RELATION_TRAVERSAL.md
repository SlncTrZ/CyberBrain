# Typed Relation Traversal

Canonical source contract. Relation assertion models and Knowledge Evolution persistence are implemented. Indexed adjacency, traversal, caller path output, automated proposals/review integration and production activation remain planned.

## Boundaries

Canonical data remains in the two existing Qdrant collections. Structured relation assertions belong under `KnowledgeRecord.extensions.relations`; their schema version is independent of the parent Knowledge schema and software/package version. Only canonical `record_class=knowledge` may own assertions. Existing `knowledge_store` can carry this extension; no new MCP tool or automatic extraction is introduced.

Evidence existence establishes referential validity, not semantic entailment. Similarity, lexical overlap and an LLM output cannot accept a relationship. An explicit authenticated reviewer must assess whether evidence supports the assertion, especially causality.

## Entity identity and Fingerprinting

`EntityRef` consists of exact domain, topic, entity_type, entity_name, finite JSON context and concrete tenant/user/agent/project/session_id scope. Labels must already be trimmed and contain no control characters; identity identifiers must already be normalized by the existing tenancy contract. Case is preserved. No fuzzy entity resolution, alias merge or entity fabrication occurs.

The node key is SHA-256 of deterministic sorted-key JSON; record UUID, content, version and timestamps are excluded. Context is bounded to 16384 UTF-8 bytes. Where existing Evolution context equality would conflate distinct JSON identities, changing a relation-bearing node's context is rejected pending explicit migration.

Endpoints must share the same full partition in this source slice. Cross-project/user/session relation grants are not implemented. Evidence must match tenant/user/agent/project and any concrete source session, plus all bound principal filters; a source without a session may cite authorized historical sessions.

## Assertion schema

`extensions.relations` requires explicit integer `schema_version=1` and an `edges` array. Boolean/string/float version substitutes, unknown versions/fields and malformed assertions fail closed.

| Field | Contract |
| --- | --- |
| relation_id | Deterministic hash of kind and scoped endpoint keys; supplied IDs must match |
| kind | depends_on, part_of, supports, contradicts, causes |
| source | Must equal the owning Knowledge entity identity |
| target | Stable scoped EntityRef |
| target_record_id | Immutable Knowledge version UUID used for admission/provenance |
| evidence | 1–32 typed knowledge/episode UUID references per edge |
| status | proposed (default), accepted or rejected |
| valid_from | Required timezone-aware timestamp, normalized to UTC |
| valid_until | Optional timestamp strictly after valid_from |
| review_note | Required nonblank explanation for accepted/rejected |

A bundle admits at most 64 edges and 128 distinct typed evidence references. Duplicate relationship identities and self relations are rejected. Evidence references and edges are canonicalized so ordering, duplicate evidence and equivalent timezone representations do not create duplicate versions.

depends_on, part_of, supports and causes are directed. contradicts has symmetric identity, while the stored source remains the owning entity. `supersedes` is reserved for native Evolution links and cannot be created as an arbitrary assertion.

Validity intervals are [valid_from, valid_until). These timestamps describe the assertion's supplied validity, not an inferred truth date. A causes edge remains proposed unless an authorized reviewer explicitly accepts the cited causal assertion; no transitive causal conclusion is implied.

## Admission and authority

Knowledge write authority is checked first. All relation assertions also require read authority before endpoint/evidence reads. Accepted/rejected states require bound authenticated `admin_review`; unbound internal calls cannot accept/reject assertions.

Storage applies partition and principal scope before point payloads become visible. Foreign and missing endpoints/evidence produce the same opaque error. Target records must match the supplied stable identity, canonical record type/class and parent schema. Proposed/accepted target anchors must be active and eligible for ordinary recall. Rejected assertions may retain canonical historical target anchors for audit without making them traversal-eligible.

Knowledge evidence must be canonical Knowledge; episode evidence uses the explicitly configured episodic adapter. Unknown parent schema, quarantine/self-model evidence and hidden evidence cannot support proposed/accepted assertions. Rejected assertions may retain authorized historical evidence. Historical/current checks remain distinct when evidence reads are reused within a request.

Both the referenced target UUID and evidence UUIDs are retained. No current-version resolution or atomic multi-record snapshot is claimed in this slice. Later traversal must revalidate each hop at read time and must not transfer the validity of old evidence to a newer target silently.

## Persistence and evolution

The existing process/identity locks, staged predecessor/successor linkage, recovery and immutable version history remain authoritative. Relation-only changes create a new Knowledge version even when content_hash is unchanged. Relation status, evidence, target version anchor and validity changes all count as relation changes.

An identical content plus canonical relation bundle is NO_CHANGE. An omitted bundle preserves an exact content retry. An explicit empty bundle withdraws assertions. Content/forced evolution without a bundle does not inherit old assertions. Changing or removing accepted/rejected assertions requires authenticated admin_review, including attempts to remove them through content or forced evolution.

Unrelated extension metadata retains existing compatibility semantics. The relation namespace is reserved and validated before new embedding/persistence effects. Secret scanning remains on the normal Knowledge write boundary. Parent payload schema stays compatible; readers can retain the extension while ordinary search ranking ignores edges.

## Planned indexed traversal

Slice 3 provides bounded batch adjacency/reverse lookup behind an adapter, with scope filtering before LIMIT, exact identity resolution and stale/index completeness handling. No per-hop corpus scan is accepted as the final implementation. Any derived index must be rebuildable from canonical Knowledge and must not become an independent truth store.

Slice 4 implements bounded BFS, allowed kinds/direction, cycle detection and path provenance. Proposed starting limits: depth 2, 32 nodes, 64 edges and 8 storage calls. These limits are design targets, not active settings; exceeding budgets must expose truncation.

Slice 5 adds explicit caller relation recall and integrates the same engine with Dreaming under a separate temporal/evidence policy. Every source/edge/target/evidence in a path must be authorized; inaccessible intermediaries cannot bridge a visible path. Eligibility precedes ranking and context packing. Graph ranking scores remain distinct from semantic similarity and confidence.

Current mode requires accepted, effective assertions and valid targets. Historical mode requires explicit as_of and version/time-consistent evidence. Ambiguous resolution, unknown schema and incomplete authority fail closed. Storage failures are explicit.

## Acceptance gates

Controlled fixtures and real isolated Qdrant must verify schema validation, scope isolation, review authority, relation-only evolution, restart recovery, native-reader compatibility and idempotency. Later gates cover multi-hop paths, reverse dependencies, cycles/diamonds, temporal updates, hidden intermediaries, truncation and bounded storage calls.

Benchmark against vector/hybrid baselines on identical evidence and context budgets: path correctness, evidence precision, Recall@K, temporal/update behavior, isolation, p50/p95 Latency, storage calls and tokens. Scalability needs separate fan-out/corpus-size measurement.

Deployment requires reserved-namespace compatibility census, protected backups, canary and rollback checks. No corpus backfill or production activation is part of slices 1–2. Longitudinal live learning evidence is recorded separately and never deducted from source acceptance.
