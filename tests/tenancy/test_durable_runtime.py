# SPDX-License-Identifier: MPL-2.0
"""Durable boundaries survive process restarts without cross-principal work."""

import json
import sqlite3
import threading
from datetime import UTC, datetime

import pytest

from cyberbrain.core.errors import ConfigurationError
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.scheduler import collect_candidates
from cyberbrain.dreaming.worker import DreamWorker
from cyberbrain.dreaming.writeback import DreamKnowledgeWriter, DreamWriteStatus
from cyberbrain.tenancy import bind_authority, current_authority
from cyberbrain.tenancy.durable import authority_snapshot, restore_authority
from cyberbrain.tenancy.limiter import SQLiteQuotaLimiter
from cyberbrain.tenancy.quota import QuotaLimit, QuotaPolicy, QuotaResource
from tests.tenancy.test_runtime_enforcement import authority
from tests.test_dream_writeback import _gate, _request, _result


def test_restart_keeps_identically_named_sessions_in_distinct_scopes(tmp_path):
    path = tmp_path / "queue.sqlite"
    queue = DreamQueue(path)
    with bind_authority(authority(tenant="one", user="same", project="p")):
        first = queue.enqueue("same-session", ["first"])
    with bind_authority(authority(tenant="two", user="same", project="p")):
        second = queue.enqueue("same-session", ["second"])
    reopened = DreamQueue(path)
    assert first.id != second.id
    with bind_authority(authority(tenant="one", user="same", project="p")):
        assert reopened.get_by_session("same-session").topics == ["first"]
    with bind_authority(authority(tenant="three", user="same", project="p")):
        with pytest.raises(KeyError):
            reopened.get_by_session("same-session")


def test_legacy_queue_migration_preserves_ids_attempts_and_terminal_state(tmp_path):
    path = tmp_path / "queue.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE dream_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL UNIQUE,
                topics_json TEXT NOT NULL, status TEXT NOT NULL, attempt_count INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_error TEXT
            )
        """)
        db.execute("INSERT INTO dream_jobs VALUES(41,'s','[]','failed',3,'old','new','error')")
    queue = DreamQueue(path)
    job = queue.get_by_session("s")
    assert (job.id, job.status, job.attempt_count, job.last_error) == (41, "failed", 3, "error")
    assert job.authority_json is None
    with bind_authority(authority(tenant="new")):
        new = queue.enqueue("s", [])
    assert new.id > 41
    assert DreamQueue(path).pending()[0].id == new.id


def test_scheduler_separates_scopes_even_when_session_names_collide():
    points = [{"payload": {
        "tenant": tenant, "user": "u", "agent": "a", "project": "p",
        "session_id": "same", "event_time": datetime.now(UTC).isoformat(), "topic": tenant,
    }} for tenant in ("one", "two")]
    candidates = list(collect_candidates(points).values())
    assert len(candidates) == 2
    assert {tuple(c.topics) for c in candidates} == {("one",), ("two",)}
    assert {restore_authority(c.authority_json).grant.scope.tenant for c in candidates} == {
        frozenset({"one"}), frozenset({"two"}),
    }


def test_worker_restores_scope_before_loading_or_mutating_any_evidence(tmp_path):
    queue = DreamQueue(tmp_path / "queue.sqlite")
    with bind_authority(authority(tenant="one", user="u", project="p")):
        queue.enqueue("s", [])
    seen = []
    class Loader:
        def load(self, session):
            seen.append(current_authority().grant.scope.as_dict())
            raise RuntimeError("fixture failure")
        def update_status(self, session, **kwargs):
            seen.append(current_authority().grant.scope.as_dict())
    worker = DreamWorker(
        queue=queue, session_loader=Loader(), engine=None, promotion=None, writeback=None,
    )
    result = worker.process_next()
    assert result.status == "failed"
    assert seen == [{"tenant": ("one",), "user": ("u",), "project": ("p",)}] * 2
    assert current_authority() is None


@pytest.mark.parametrize("snapshot", [
    '{"schema":2}', '{"schema":true}', '{}', '[]', 'invalid',
])
def test_unknown_durable_authority_fails_closed(snapshot):
    with pytest.raises(ConfigurationError):
        restore_authority(snapshot)


def test_snapshot_contains_identity_and_grants_only():
    with bind_authority(authority(tenant="t", user="u", agent="a")):
        value = json.loads(authority_snapshot())
    assert set(value) == {"schema", "mode", "scope", "operations"}
    assert value["scope"] == {"tenant": ["t"], "user": ["u"], "agent": ["a"]}


@pytest.mark.parametrize("dimension", ["tenant", "user", "agent", "project"])
def test_dream_writeback_blocks_mixed_identity_before_canonical_write(dimension):
    request = _request()
    items = request.evidence_by_topic["cyberbrain"]
    for index, item in enumerate(items):
        item.metadata[dimension] = "one" if index == 0 else "two"
    class NoWrites:
        def store(self, **kwargs):
            pytest.fail("mixed scope reached canonical persistence")
    result = DreamKnowledgeWriter(NoWrites()).write_promoted(
        request=request, result=_result(request), gate=_gate(request), dream_run_id="run",
    )
    assert result[0].status == DreamWriteStatus.BLOCKED_METADATA


def policy(amount=2):
    return QuotaPolicy((QuotaLimit(QuotaResource.REQUESTS, amount, 60),))


def test_quota_survives_restart_and_rejects_without_partial_reservation(tmp_path):
    path = tmp_path / "quota.sqlite"
    caller = authority(tenant="t", user="u")
    first = SQLiteQuotaLimiter(path, policy())
    first.reserve(caller, {QuotaResource.REQUESTS: 1}, now=10)
    reopened = SQLiteQuotaLimiter(path, policy())
    with pytest.raises(ConfigurationError):
        reopened.reserve(caller, {QuotaResource.REQUESTS: 2}, now=11)
    reopened.reserve(caller, {QuotaResource.REQUESTS: 1}, now=12)
    with pytest.raises(ConfigurationError):
        first.reserve(caller, {QuotaResource.REQUESTS: 1}, now=13)
    reopened.reserve(caller, {QuotaResource.REQUESTS: 2}, now=60)


def test_agent_rotation_cannot_bypass_tenant_budget(tmp_path):
    limiter = SQLiteQuotaLimiter(tmp_path / "quota.sqlite", policy(1))
    limiter.reserve(authority(tenant="t", user="u1", agent="a"),
                    {QuotaResource.REQUESTS: 1}, now=10)
    with pytest.raises(ConfigurationError):
        limiter.reserve(authority(tenant="t", user="u2", agent="b"),
                        {QuotaResource.REQUESTS: 1}, now=10)
    limiter.reserve(authority(tenant="other", user="u3", agent="a"),
                    {QuotaResource.REQUESTS: 1}, now=10)


def test_concurrent_process_connections_do_not_overbook_budget(tmp_path):
    path = tmp_path / "quota.sqlite"
    limiters = [SQLiteQuotaLimiter(path, policy(1)) for _ in range(2)]
    barrier = threading.Barrier(2)
    outcomes = []
    def reserve(limiter):
        barrier.wait()
        try:
            limiter.reserve(authority(tenant="t"), {QuotaResource.REQUESTS: 1}, now=10)
            outcomes.append("accepted")
        except ConfigurationError:
            outcomes.append("denied")
    threads = [threading.Thread(target=reserve, args=(limiter,)) for limiter in limiters]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["accepted", "denied"]


def test_recall_ceiling_denial_does_not_consume_request_budget(tmp_path):
    limiter = SQLiteQuotaLimiter(tmp_path / "quota.sqlite", QuotaPolicy((
        QuotaLimit(QuotaResource.REQUESTS, 1, 60),
        QuotaLimit(QuotaResource.RECALL_LIMIT, 5),
    )))
    caller = authority(agent="a")
    with pytest.raises(ConfigurationError):
        limiter.reserve(caller, {QuotaResource.REQUESTS: 1, QuotaResource.RECALL_LIMIT: 6}, now=10)
    limiter.reserve(caller, {QuotaResource.REQUESTS: 1, QuotaResource.RECALL_LIMIT: 5}, now=10)


def test_quota_defers_background_without_spending_retry_budget(tmp_path):
    from cyberbrain.tenancy.limiter import QuotaExceededError
    class ExhaustedLimiter:
        def reserve(self, *args, **kwargs):
            raise QuotaExceededError(60)
    queue = DreamQueue(tmp_path / "queue.sqlite")
    job = queue.enqueue("s", [])
    class NoEvidenceAccess:
        def load(self, session):
            pytest.fail("quota-denied work accessed evidence")
        def update_status(self, *args, **kwargs):
            pytest.fail("quota-denied work mutated evidence")
    worker = DreamWorker(
        queue=queue, session_loader=NoEvidenceAccess(), engine=None,
        promotion=None, writeback=None, quota_limiter=ExhaustedLimiter(),
    )
    result = worker.process_next()
    assert result.status == "deferred"
    assert queue.get_by_session("s").attempt_count == 0
    assert queue.get_by_session("s").id == job.id
    assert queue.claim_next() is None


def test_broader_worker_does_not_claim_legacy_owner_jobs(tmp_path):
    from cyberbrain.tenancy import DeploymentMode
    queue = DreamQueue(tmp_path / "queue.sqlite")
    queue.enqueue("legacy", [])
    assert queue.claim_next(deployment_mode=DeploymentMode.MULTI_USER) is None
    assert queue.get_by_session("legacy").status == "pending"


def test_background_audit_filters_before_pagination_and_rejects_foreign_resolution(tmp_path):
    from cyberbrain.dreaming.audit import DreamRunAuditStore
    audit = DreamRunAuditStore(tmp_path / "audit.sqlite")
    for tenant in ("foreign", "allowed"):
        with bind_authority(authority(tenant=tenant)):
            request = _request()
            request = type(request)(**{**request.__dict__, "request_id": tenant})
            audit.start(dream_run_id=tenant, request=request)
            gate = _gate(request)
            from dataclasses import replace

            from cyberbrain.dreaming.gate import PromotionDecision
            gate = replace(gate, candidates=[
                replace(gate.candidates[0], decision=PromotionDecision.REVIEW),
            ])
            audit.complete(dream_run_id=tenant, result=_result(request), gate=gate)
    with bind_authority(authority(tenant="allowed")):
        rows = audit.pending_reviews(limit=1)
        assert [row["dream_run_id"] for row in rows] == ["allowed"]
        with pytest.raises(KeyError):
            audit.request_snapshot("foreign")
        with pytest.raises(KeyError):
            audit.resolve_review(dream_run_id="foreign", candidate_index=0,
                                 resolution="approved", reviewer="fixture")
    assert audit.review_resolution("foreign", 0) is None


def test_reason_task_scope_survives_restart_and_rejects_foreign_token_submission(tmp_path):
    from cyberbrain.dreaming.reason_task_inbox import DreamReasonTaskInbox
    from tests.test_reason_task_inbox import _request as task_request
    path = tmp_path / "reason.sqlite"
    inbox = DreamReasonTaskInbox(path)
    with bind_authority(authority(tenant="one", user="u")):
        inbox.publish(task_request(), wait_seconds=60)
        lease = inbox.claim_next(claimed_by="fixture")
    restarted = DreamReasonTaskInbox(path)
    with bind_authority(authority(tenant="two", user="u")):
        assert restarted.claim_next(claimed_by="other") is None
        assert restarted.task_state("task-1") is None
        with pytest.raises(KeyError):
            restarted.submit(task_id="task-1", claim_token=lease.claim_token, claims=[])
    with bind_authority(authority(tenant="one", user="u")):
        assert restarted.task_state("task-1").status == "claimed"


def test_numeric_telemetry_is_scoped_and_timing_storage_is_constant_size():
    from cyberbrain.core.metrics import MetricSample, MetricsRegistry
    metrics = MetricsRegistry()
    with bind_authority(authority(tenant="one", user="u", agent="a")):
        for _ in range(1000):
            metrics.increment("requests")
            metrics.observe("latency", 0.5)
    with bind_authority(authority(tenant="two", user="u", agent="a")):
        metrics.increment("requests", 2)
        metrics.observe("latency", 1.0)
    one = metrics.snapshot(scope=authority(tenant="one", user="u").grant.scope)
    two = metrics.snapshot(scope=authority(tenant="two", user="u").grant.scope)
    assert one["counters"] == {"requests": 1000}
    assert two["counters"] == {"requests": 2}
    assert one["timings"]["latency"]["avg"] == 0.5
    assert two["timings"]["latency"]["count"] == 1
    assert isinstance(metrics._timings["latency"], MetricSample)


def test_m6_does_not_pool_same_agent_outcomes_across_tenants():
    from datetime import timedelta

    from cyberbrain.cognition.prediction import PredictionLearningService
    from cyberbrain.cognition.runtime_path import CognitiveRuntimePath
    from cyberbrain.core.metrics import MetricsRegistry
    from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
    from cyberbrain.lifecycle import MemoryLifecycleService
    from cyberbrain.memory.service import MemoryService
    from cyberbrain.schemas.models import IdentityTrust
    from cyberbrain.self_model import SelfModelPersistence, SelfModelService
    from cyberbrain.tenancy import TrustedIdentityEvidence
    from tests.tenancy.test_runtime_enforcement import CountingEmbedding, ScopedRepository

    repo = ScopedRepository()
    embedding = CountingEmbedding()
    memory = MemoryService(repository=repo, embedding=embedding, collection="episode")
    learning = PredictionLearningService(
        memory=memory, repository=repo, episodic_collection="episode",
    )
    now = datetime.now(UTC)
    for tenant, count in (("foreign", 20), ("own", 1)):
        with bind_authority(authority(tenant=tenant, user="u", agent="shared")):
            for index in range(count):
                prediction = learning.record_prediction(
                    expected_outcome="prospective fixture", confidence=0.8,
                    session_id=f"session-{index % 3}", event_time=now,
                    agent="shared", topic=f"topic-{index % 3}",
                    identity_trust=IdentityTrust.AUTHENTICATED,
                )
                learning.record_outcome(
                    prediction_id=prediction.id, observed_outcome="fixture succeeded",
                    assessment="confirmed", event_time=now + timedelta(seconds=1),
                )
    evolution = KnowledgeEvolutionService(
        repository=repo, embedding=embedding, collection="knowledge",
    )
    path = CognitiveRuntimePath(
        repository=repo, knowledge_collection="knowledge", episodic_collection="episode",
        metrics=MetricsRegistry(), self_model=SelfModelService(),
        self_model_persistence=SelfModelPersistence(
            evolution=evolution, repository=repo, collection="knowledge",
        ), memory_lifecycle=MemoryLifecycleService(repository=repo),
    )
    own = authority(tenant="own", user="u", agent="shared")
    identity = TrustedIdentityEvidence.from_authentication_boundary(
        scope=own.grant.scope, authentication_source="fixture-boundary",
    )
    before = len(repo.points)
    with bind_authority(own):
        result = path.run_self_model(
            trusted_identity=identity, generated_at=now + timedelta(seconds=2),
        )
    assert result["status"] == "insufficient_evidence"
    assert result["trusted_resolved_outcomes"] == 1
    assert len(repo.points) == before


def test_quota_creates_its_configured_parent_and_preserves_usage(tmp_path):
    from cyberbrain.tenancy.limiter import QuotaExceededError
    path = tmp_path / "nested" / "quotas.sqlite"
    policy = QuotaPolicy((QuotaLimit(QuotaResource.REQUESTS, 1, 60),))
    caller = authority(tenant="one", user="u")
    SQLiteQuotaLimiter(path, policy).reserve(caller, {QuotaResource.REQUESTS: 1}, now=1)
    with pytest.raises(QuotaExceededError):
        SQLiteQuotaLimiter(path, policy).reserve(caller, {QuotaResource.REQUESTS: 1}, now=2)


def test_quota_rejects_transient_storage():
    from cyberbrain.core.errors import ConfigurationError
    with pytest.raises(ConfigurationError, match="durable SQLite"):
        SQLiteQuotaLimiter(":memory:", QuotaPolicy(()))
