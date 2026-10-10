# SPDX-License-Identifier: MPL-2.0
"""Release regressions for scoped, immutable predictions and evidence-backed reasoning."""

from __future__ import annotations

import json
import multiprocessing
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from time import sleep
from uuid import UUID

import pytest

from cyberbrain.agent_adapter.adapter import UniversalAgentAdapter
from cyberbrain.agent_adapter.mcp_client import MCPAgentClient
from cyberbrain.agent_adapter.models import AgentScope, Observation
from cyberbrain.cognition.prediction import PredictionLearningService
from cyberbrain.core.errors import ConfigurationError
from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import DreamEvidenceGate
from cyberbrain.dreaming.orchestration import MultipassDreamReasoner
from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
    ReasoningClaim,
    ReasoningTask,
    ReasoningTaskKind,
)
from cyberbrain.memory.service import MemoryService
from cyberbrain.reasoning.engine import BoundedReasoningEngine
from cyberbrain.relations.models import RelationKind, RelationStatus
from cyberbrain.tenancy import (
    DeploymentMode,
    IdentityScope,
    OperationClass,
    authority_for_authenticated_scope,
    bind_authority,
)
from tests.test_audit_remediation import NOW, _edge, _entity
from tests.test_prediction_learning import FakeEmbedding, FakeRepository


class CountingRepository(FakeRepository):
    def __init__(self):
        super().__init__()
        self.writes = 0
        self.reads = 0

    def upsert(self, collection, **kwargs):
        self.writes += 1
        return super().upsert(collection, **kwargs)

    def retrieve(self, collection, point_id, *, qdrant_filter=None):
        self.reads += 1
        point = super().retrieve(collection, point_id)
        if point is None:
            return None
        for condition in (qdrant_filter or {}).get("must", []):
            if "key" in condition:
                value = point["payload"].get(condition["key"])
                match = condition["match"]
                if "value" in match and value != match["value"]:
                    return None
                if "any" in match and value not in match["any"]:
                    return None
        return point


class SlowEmbedding(FakeEmbedding):
    def embed(self, text):
        sleep(0.05)
        return super().embed(text)


def _service(repo, *, slow=False, lock_file=None):
    memory = MemoryService(
        repository=repo,
        embedding=SlowEmbedding() if slow else FakeEmbedding(),
        collection="episode",
    )
    options = {} if lock_file is None else {"process_lock_file": lock_file}
    return PredictionLearningService(
        memory=memory,
        repository=repo,
        episodic_collection="episode",
        **options,
    )


def _record(service, **kwargs):
    values = dict(
        expected_outcome="original prospective expectation",
        confidence=0.8,
        session_id="s",
        agent="a",
        project="p",
        event_time=NOW,
        correlation_id="c",
    )
    return service.record_prediction(**(values | kwargs))


def _authority(tenant="t", user="u", *, operations=None, **scope):
    return authority_for_authenticated_scope(
        DeploymentMode.MULTI_USER,
        scope=IdentityScope.from_values(tenant=tenant, user=user, **scope),
        operations=frozenset(OperationClass if operations is None else operations),
    )


@pytest.mark.parametrize("tenant,user", [("other", "u"), ("t", "other")])
def test_prediction_correlation_is_principal_scoped(tenant, user):
    repo = CountingRepository()
    service = _service(repo)
    with bind_authority(_authority()):
        a = _record(service)
    with bind_authority(_authority(tenant, user)):
        b = _record(service, expected_outcome="independent expectation")
    assert a.id != b.id
    assert (b.tenant, b.user) == (tenant, user)
    assert b.context["cognition"]["expected_outcome"] == "independent expectation"
    assert repo.writes == 2


def test_prediction_retry_authorizes_before_read_or_write():
    repo = CountingRepository()
    service = _service(repo)
    with bind_authority(_authority(project="p")):
        _record(service)
    before = (repo.reads, repo.writes)
    with bind_authority(_authority(project="p", operations={OperationClass.READ})):
        with pytest.raises(ConfigurationError):
            _record(service)
    with bind_authority(_authority(project="other")):
        with pytest.raises(ConfigurationError):
            _record(service)
    assert (repo.reads, repo.writes) == before


def test_prediction_fingerprint_uses_normalized_scope_and_unambiguous_encoding():
    repo = CountingRepository()
    service = _service(repo)
    with bind_authority(_authority(project="p")):
        first = _record(service, project=" p ", session_id=" s ")
        retry = _record(service, project="p", session_id="s", expected_outcome="retry")
    assert first == retry
    # A delimiter inside one dimension must not collide with another dimension.
    a = _record(service, session_id="s:a", agent="b")
    b = _record(service, session_id="s", agent="a:b")
    assert a.id != b.id
    assert repo.writes == 3


def test_prediction_retry_never_overwrites_invalid_provenance():
    repo = CountingRepository()
    service = _service(repo)
    first = _record(service)
    repo.points[first.id]["payload"]["context"]["cognition"]["prediction_id"] = str(UUID(int=1))
    with pytest.raises(ValueError, match="provenance"):
        _record(service)
    assert repo.writes == 1


def test_concurrent_service_instances_return_one_immutable_prediction():
    repo = CountingRepository()
    services = [_service(repo, slow=True), _service(repo, slow=True)]
    barrier = Barrier(2)

    def run(index):
        barrier.wait(timeout=5)
        return _record(services[index], expected_outcome=f"expectation {index}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(run, range(2)))
    assert a == b
    assert repo.writes == 1
    assert a.model_dump(mode="json") == repo.points[a.id]["payload"]


def test_retry_after_ambiguous_write_preserves_original_prediction():
    class AmbiguousWriteRepository(CountingRepository):
        def upsert(self, collection, **kwargs):
            super().upsert(collection, **kwargs)
            if self.writes == 1:
                raise ConnectionError("response lost after durable write")

    repo = AmbiguousWriteRepository()
    service = _service(repo)
    with pytest.raises(ConnectionError):
        _record(service)
    retry = _record(service, expected_outcome="changed retry expectation")
    assert retry.context["cognition"]["expected_outcome"] == "original prospective expectation"
    assert repo.writes == 1


class SQLiteRepository:
    """Disposable shared backend to test process coordination at the real OS boundary."""

    def __init__(self, path):
        self.path = str(path)

    def retrieve(self, collection, point_id, **kwargs):
        with sqlite3.connect(self.path) as conn:
            row = conn.execute("SELECT payload FROM points WHERE id=?", (str(point_id),)).fetchone()
        return None if row is None else {"id": str(point_id), "payload": json.loads(row[0])}

    def upsert(self, collection, *, point_id, vector, payload):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO points VALUES (?, ?)",
                (
                    str(point_id),
                    json.dumps(payload),
                ),
            )
            conn.execute("UPDATE writes SET count=count+1")


def _process_prediction(backend, lock_file, barrier, output, index):
    service = _service(SQLiteRepository(backend), slow=True, lock_file=lock_file)
    barrier.wait(timeout=10)
    output.put(
        _record(service, expected_outcome=f"process expectation {index}").model_dump(mode="json")
    )


@pytest.mark.skipif(sys.platform != "linux", reason="runtime process locks require Linux/fcntl")
def test_runtime_process_workers_share_immutable_prediction(tmp_path):
    backend = tmp_path / "points.sqlite"
    with sqlite3.connect(backend) as conn:
        conn.execute("CREATE TABLE points (id TEXT PRIMARY KEY, payload TEXT)")
        conn.execute("CREATE TABLE writes (count INTEGER)")
        conn.execute("INSERT INTO writes VALUES (0)")
    ctx = multiprocessing.get_context("fork")
    barrier, output = ctx.Barrier(2), ctx.Queue()
    workers = [
        ctx.Process(
            target=_process_prediction,
            args=(backend, str(tmp_path / "prediction.lock"), barrier, output, i),
        )
        for i in range(2)
    ]
    try:
        for worker in workers:
            worker.start()
        results = [output.get(timeout=15) for _ in workers]
        for worker in workers:
            worker.join(timeout=15)
            assert worker.exitcode == 0
        assert results[0] == results[1]
        with sqlite3.connect(backend) as conn:
            assert conn.execute("SELECT count FROM writes").fetchone()[0] == 1
            assert (
                json.loads(conn.execute("SELECT payload FROM points").fetchone()[0]) == results[0]
            )
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
        output.close()


class ServiceInvoker:
    def __init__(self, service):
        self.service = service
        self.resolutions = []

    async def invoke_async(self, *, tool, arguments):
        if tool.endswith("prediction_pending"):
            return self.service.pending(**arguments).model_dump(mode="json")
        if tool.endswith("prediction_resolve"):
            self.resolutions.append(arguments)
            return {"id": arguments["prediction_id"]}
        raise AssertionError(tool)


@pytest.mark.asyncio
async def test_provider_clipped_pending_envelope_blocks_adapter_correlation_resolution():
    repo = CountingRepository()
    service = _service(repo)
    for i in range(21):
        # Legacy predictions can legitimately contain duplicated correlation values.
        record = _record(service, correlation_id=None, event_time=NOW + timedelta(seconds=i))
        repo.points[record.id]["payload"]["context"]["cognition"]["correlation_id"] = (
            "duplicate" if i in (0, 20) else f"other-{i}"
        )
    pending = service.pending(limit=20)
    assert pending.returned == 20
    assert pending.may_be_incomplete
    invoker = ServiceInvoker(service)
    adapter = UniversalAgentAdapter(MCPAgentClient(invoker))
    match, record = await adapter.resolve_prediction(
        observation=Observation(
            observed_outcome="done",
            assessment="confirmed",
            event_time=NOW + timedelta(minutes=1),
            correlation_id="duplicate",
        ),
        scope=AgentScope(session_id="s", agent="a", project="p"),
    )
    assert match.prediction_id is None
    assert match.reason_code == "incomplete_scan_cannot_verify_correlation_uniqueness"
    assert record is None
    assert invoker.resolutions == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [{"prediction_id": "p", "correlation_id": "c"}],
        {"items": [{"prediction_id": "p", "correlation_id": "c"}]},
        {"items": [{"prediction_id": "p", "correlation_id": "c"}], "may_be_incomplete": "false"},
    ],
)
async def test_unknown_provider_completeness_cannot_authorize_correlation_match(payload):
    class Invoker:
        async def invoke_async(self, *, tool, arguments):
            assert tool.endswith("prediction_pending")
            return payload

    match, record = await UniversalAgentAdapter(MCPAgentClient(Invoker())).resolve_prediction(
        observation=Observation("done", "confirmed", NOW, correlation_id="c"),
        scope=AgentScope(session_id="s"),
    )
    assert match.prediction_id is None
    assert record is None


def _evidence(project="CyberBrain", domain="engineering", index=1):
    return EvidenceItem(
        id=str(UUID(int=index)),
        record_type="episodic",
        content="context-bound evidence",
        score=0.9,
        event_time=NOW,
        metadata={"project": project, "domain": domain, "verification": "tested"},
    )


def _request(evidence):
    return DreamReasoningRequest(
        request_id="r",
        session_id="s",
        focal_topics=["code"],
        session_start=NOW,
        session_end=NOW,
        evidence_by_topic={"code": evidence},
    )


def _candidate(evidence, **kwargs):
    return DreamCandidate(
        **(
            dict(
                entity_name="claim",
                entity_type="fact",
                summary="same claim",
                content="same claim",
                evidence_ids=[evidence.id],
                confidence=0.9,
                classification="new_knowledge",
                context={"topic": "code"},
            )
            | kwargs
        )
    )


@pytest.mark.parametrize("difference", ["project", "domain", "polarity", "context"])
def test_dedupe_preserves_partition_polarity_and_semantic_context(difference):
    a = _evidence(index=1)
    b = _evidence(
        project="Other" if difference == "project" else "CyberBrain",
        domain="other" if difference == "domain" else "engineering",
        index=2,
    )
    c1, c2 = _candidate(a), _candidate(b)
    if difference == "polarity":
        c2 = replace(c2, negative_knowledge=True)
    if difference == "context":
        c2 = replace(c2, context={"topic": "code", "branch": "other"})
    result = DreamReasoningResult("r", [c1, c2])
    gate = DreamEvidenceGate().evaluate(_request([a, b]), result)
    assert all("duplicate_candidate_in_run" not in c.reasons for c in gate.candidates)
    assert result.candidates[0].evidence_ids == [a.id]
    assert result.candidates[1].evidence_ids == [b.id]


def test_multipass_review_project_filter_uses_selected_evidence_and_keeps_cursor(tmp_path):
    a, b = _evidence(index=1), _evidence(project="Other", index=2)
    a2, b2 = _evidence(index=3), _evidence(project="Other", index=4)
    task = ReasoningTask("t", "r", "code", ReasoningTaskKind.CAVEAT, "", [a, b, a2, b2])
    candidates = [
        MultipassDreamReasoner._candidate_from_claim(
            task,
            ReasoningClaim("context-bound caveat", evidence, 0.8),
            i,
        )
        for i, evidence in enumerate([[b.id, b2.id], [a.id, a2.id], [a.id, a2.id]])
    ]
    result = DreamReasoningResult("r", candidates)
    request = _request([a, b, a2, b2])
    # Distinct context avoids collapsing the two legitimate review items for project A.
    candidates[2].context["branch"] = "second"
    gate = DreamEvidenceGate().evaluate(request, result)
    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    audit.start(dream_run_id="run", request=request)
    audit.complete(dream_run_id="run", result=result, gate=gate)
    page1 = audit.pending_reviews(project="CyberBrain", limit=1)
    assert len(page1) == 1
    assert page1[0]["candidate_index"] == 1
    after = (page1[0]["created_at"], page1[0]["dream_run_id"], page1[0]["candidate_index"])
    page2 = audit.pending_reviews(project="CyberBrain", limit=1, after=after)
    assert len(page2) == 1 and page2[0]["candidate_index"] == 2


def test_project_review_does_not_trust_context_over_mixed_evidence(tmp_path):
    a, b = _evidence(index=1), _evidence(project="Other", index=2)
    candidate = _candidate(
        a,
        evidence_ids=[a.id, b.id],
        classification="context_dependent",
        context={"project": "CyberBrain"},
    )
    request, result = _request([a, b]), DreamReasoningResult("r", [candidate])
    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    audit.start(dream_run_id="run", request=request)
    audit.complete(
        dream_run_id="run",
        result=result,
        gate=DreamEvidenceGate().evaluate(request, result),
    )
    assert len(audit.pending_reviews()) == 1
    assert audit.pending_reviews(project="CyberBrain") == []


@pytest.mark.parametrize("rejected_side", ["candidate", "base"])
def test_rejected_edges_do_not_create_counterfactual_conflicts(rejected_side):
    a, b = _entity("a"), _entity("b")
    cand = _edge(RelationKind.SUPPORTS, a, b)
    base = _edge(RelationKind.CONTRADICTS, a, b)
    if rejected_side == "candidate":
        cand = cand.model_copy(update={"status": RelationStatus.REJECTED})
    else:
        base = base.model_copy(update={"status": RelationStatus.REJECTED})
    result = BoundedReasoningEngine().evaluate_counterfactual(
        hypothetical_edges=[cand],
        base_edges=[base],
    )
    assert result.is_consistent and not result.is_incomplete
    assert result.contradictions == []


@pytest.mark.parametrize("overlap", [False, True])
def test_counterfactual_conflicts_require_overlapping_validity(overlap):
    a, b = _entity("a"), _entity("b")
    base = _edge(RelationKind.CONTRADICTS, a, b, valid_until=NOW + timedelta(days=1))
    cand = _edge(
        RelationKind.SUPPORTS,
        a,
        b,
        valid_from=NOW + timedelta(hours=12 if overlap else 48),
    )
    result = BoundedReasoningEngine().evaluate_counterfactual(
        hypothetical_edges=[cand],
        base_edges=[base],
    )
    assert result.is_consistent is (not overlap)
    assert len(result.contradictions) == int(overlap)


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_dependency_depth_keeps_complete_original_proofs(depth):
    entities = [_entity(str(i)) for i in range(6)]
    edges = [
        _edge(RelationKind.DEPENDS_ON, a, b)
        for a, b in zip(entities[:-1], entities[1:], strict=True)
    ]
    inferred = BoundedReasoningEngine().derive_inferences(edges, max_depth=depth)
    from_first = {
        inf.edge.target.entity_name: inf for inf in inferred if inf.edge.source == entities[0]
    }
    assert set(from_first) == {str(i) for i in range(2, depth + 1)}
    for hops in range(2, depth + 1):
        assertion = from_first[str(hops)]
        assert assertion.premises == tuple(edge.relation_id for edge in edges[:hops])
        assert set(assertion.edge.evidence) == {ev for edge in edges[:hops] for ev in edge.evidence}
        assert assertion.edge.target_record_id == edges[hops - 1].target_record_id
        assert assertion.edge.status == RelationStatus.PROPOSED


@pytest.mark.skipif(sys.platform != "linux", reason="runtime process locks require Linux/fcntl")
def test_process_coordination_timeout_has_no_storage_side_effects(tmp_path, monkeypatch):
    import fcntl

    from cyberbrain.cognition import coordination

    repo = CountingRepository()
    lock_file = str(tmp_path / "prediction.lock")
    service = _service(repo, lock_file=lock_file)
    first = _record(service)
    before = (repo.reads, repo.writes)
    stripe = first.id.int % 64
    monkeypatch.setattr(coordination, "_TIMEOUT_SECONDS", 0.03)
    with open(f"{lock_file}.{stripe}", "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            with pytest.raises(TimeoutError, match="coordination"):
                _record(service)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    assert (repo.reads, repo.writes) == before


def test_deeper_dependency_requires_common_validity_across_all_original_premises():
    a, b, c, d = [_entity(name) for name in "abcd"]
    edges = [
        _edge(RelationKind.DEPENDS_ON, a, b, valid_until=NOW + timedelta(days=1)),
        _edge(RelationKind.DEPENDS_ON, b, c),
        _edge(RelationKind.DEPENDS_ON, c, d, valid_from=NOW + timedelta(days=2)),
    ]
    assertions = BoundedReasoningEngine().derive_inferences(edges, max_depth=3)
    assert not any(inf.edge.source == a and inf.edge.target == d for inf in assertions)


def test_dependency_cycles_and_budget_remain_bounded():
    a, b, c = [_entity(name) for name in "abc"]
    edges = [
        _edge(RelationKind.DEPENDS_ON, a, b),
        _edge(RelationKind.DEPENDS_ON, b, c),
        _edge(RelationKind.DEPENDS_ON, c, a),
    ]
    assertions = BoundedReasoningEngine(max_inferences=2).derive_inferences(edges, max_depth=5)
    assert len(assertions) <= 2
    assert all(inf.edge.source != inf.edge.target for inf in assertions)


def test_authorized_write_only_caller_can_create_and_retry_its_own_prediction():
    repo = CountingRepository()
    service = _service(repo)
    with bind_authority(_authority(operations={OperationClass.WRITE})):
        first = _record(service)
        retry = _record(service, expected_outcome="different retry")
    assert first == retry
    assert repo.writes == 1
