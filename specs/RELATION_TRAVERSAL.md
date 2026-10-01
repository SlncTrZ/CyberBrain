# Typed Relation Traversal

Canonical source contract. Relation models, Knowledge Evolution persistence, indexed adjacency/reverse lookup and bounded traversal are implemented in source. Public caller/Dream wiring, explicit proposal/review workflows and controlled benchmark/rollout tooling are implemented. Deployment acceptance is recorded separately from source gates. Automated extraction/acceptance is not provided.

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

## Indexed adjacency and bounded traversal

New canonical Knowledge writes generate the server-owned `extensions._relation_index` projection, including records with no assertions so withdrawal and version-head resolution remain visible. It stores schema version, scoped owner key, accepted target keys and canonical bundle digest. Caller-supplied projection is rejected. Non-indexable ordinary identities without assertions receive an ineligible marker; they cannot become graph nodes.

`RelationIndex` uses native Qdrant keyword/integer indexes for source/reverse lookup and a datetime index for created_at. `prepare_indexes` requires authenticated admin_review and read authority; `verify_indexes` checks actual field types before serving traversal. Schema verification is a setup operation, outside per-request read counts. No third canonical collection is created. Every hop uses bounded batch lookups rather than a corpus scan.

A scoped completeness check runs before seeds are read. Missing/unknown projection schema fails with rebuild-required. Loaded owners and version heads must match their canonical projection exactly. This assumes server-controlled canonical writes; a scope census/backfill must audit legacy namespace collisions and out-of-band corruption before activation. The bounded maintenance `rebuild(maximum_records<=256)` validates the complete scoped batch before modifying it, refuses a continuation, and preserves all other extension fields. It requires read/write/admin_review and quiesced writers. It is not a production-scale backfill or transaction; partial storage write failures are explicit and require retry/audit. Existing NO_CHANGE retries do not silently backfill.

`RelationTraversal.traverse(seed_ids, TraversalPolicy(...))` is an internal source API requiring bound authenticated read authority. Seeds must share the same exact partition. Directed kinds support out/in/both; contradicts permits both traversal directions while retaining the original assertion owner. Only accepted, effective assertions contribute paths. Evidence remains typed, authorized, canonical and eligible for ordinary recall; episodic proof additionally requires Memory read authority and an event time no later than evaluation time.

| Limit | Default | Hard maximum |
| --- | --- | --- |
| Depth | 2 | 3 |
| Unique nodes, including seeds | 32 | 128 |
| Unique relationship identities | 64 | 256 |
| Returned path prefixes | 128 | 512 |
| Physical storage reads | 8 | 32 |
| Points per physical page | 256 | 256 |

Limits apply before appending results. A page continuation abandons that incomplete phase and reports candidate_capacity rather than picking an arbitrary partial head. Exhausted storage budgets preserve only paths from completed earlier hops. Node/edge/path limits report explicit reasons. Reaching depth with an unexpanded frontier conservatively reports depth truncation. Storage and authorization failures propagate. Diamond paths retain distinct provenance; cycles are stopped per path, allowing multiple legitimate routes to a node.

Each path contains node keys, ordered version UUIDs and per-step relation ID/kind/direction, owning UUID/version, immutable target anchor, typed proof IDs and validity interval. Graph path metadata is separate from cosine similarity and confidence; chaining causes does not infer a transitive causal fact.

Current mode requires one unique active version per entity and exact target UUID equality. It never redirects stale anchors to successors. Explicit historical as_of selects the highest non-staged version created by that time, with unique version resolution, accepted assertions and [valid_from, valid_until) intervals. Knowledge/episode proof creation times and episode event times cannot exceed as_of. Mutable lifecycle/privacy suppression remains enforced today: historical mode does not replay former privacy grants or restore hidden/deprecated/rejected data. Results explicitly state snapshot_consistent=false because Qdrant reads are not an atomic multi-record snapshot.

Slice 5 provides explicit caller relation recall and the same engine in Dreaming under separate temporal/evidence and background-authority policies. Every source/edge/target/evidence in a path must be authorized; inaccessible intermediaries cannot bridge a visible path. Eligibility precedes ranking and context packing. Graph ranking scores remain distinct from semantic similarity and confidence.

Ambiguous resolution, unknown schema and incomplete authority fail closed. Storage failures are explicit.

## Acceptance gates

Controlled fixtures and real isolated Qdrant must verify schema validation, scope isolation, review authority, relation-only evolution, restart recovery, native-reader compatibility and idempotency. Source gates now cover 1–3 hops, reverse dependencies, symmetric contradiction, cycles/diamonds, temporal updates, typed episode proof, hidden intermediaries, truncation and physical storage read bounds. The real isolated Qdrant gate exercises indexed diamond/reverse paths, historical selection and foreign-seed rejection.

Benchmark against vector/hybrid baselines on identical evidence and context budgets: path correctness, evidence precision, Recall@K, temporal/update behavior, isolation, p50/p95 Latency, storage calls and tokens. Scalability needs separate fan-out/corpus-size measurement.

Deployment requires reserved-namespace compatibility census, protected backups, canary and rollback checks. No corpus backfill or production activation is part of slices 1–4. Longitudinal live learning evidence is recorded separately and never deducted from source acceptance.

## Source integration and controlled measurement

Caller recall rehydrates every selected node/owner/proof within principal scope, checks
canonical identity/status/interval/proof agreement, then packs whole paths and typed records
under one estimated JSON context budget. It never returns a path with missing hydrated proof.
Current/historical and snapshot_consistent=false semantics remain unchanged.

Proposal/review tools merge explicit assertions, preserve canonical metadata and use an
expected active UUID checked under existing Evolution locks. Read/write authority is required;
accept/reject additionally requires admin_review. No similarity/LLM output triggers acceptance.

Dream integration is opt-in and uses BACKGROUND_EVIDENCE_READ instead of foreground READ.
Seeds first pass direct topic eligibility. Full reviewed paths justify related evidence without
requiring neighbors to repeat the query's lexical terms. Complete path/proof groups fit the
actual serialized EvidenceItem token and item budget. The reasoner retains independent claim
relevance/evidence gates; no relationship is invented or promoted.

Qdrant owns a reusable HTTP client by default; caller-supplied clients keep their external
lifetime. API/worker process shutdown closes repository-owned connections. The controlled
benchmark records current vector/hybrid/typed modes with equal text/context budgets, known
seeds, synthetic 3D vectors, path gold labels, native target updates and real Qdrant timings.
Unsupported historical ordinary-search modes are omitted rather than scored as zero.
It measures source mechanics, not general embedding quality or superiority to other projects.

Rollout requires a quiesced census, protected verified snapshots of both existing collections,
a matching canonical source hash and bounded paginated backfill. Namespace collision, unknown
parent/assertion schema, source drift and checkpoint corruption fail before projection writes.
Partial projection writes can retry with the same checkpoint because source hashes exclude the
derived index; canonical changes require a new checkpoint. ID/vector/content/other extension
preservation and a real snapshot restore/reapply are verified on isolated Qdrant.
