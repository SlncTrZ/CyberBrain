# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import multiprocessing as mp
import sys
from typing import Any
from uuid import UUID

import pytest

from cyberbrain.core.errors import ConflictError
from cyberbrain.knowledge.evolution import EvolutionOutcome, KnowledgeEvolutionService


class FakeEmbedding:
    dimension = 3
    version = "fake@v1"

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("empty")
        return [0.1, 0.2, 0.3]


class FakeRepository:
    def __init__(self) -> None:
        self.points: dict[UUID, dict[str, Any]] = {}

    def upsert(
        self,
        collection: str,
        *,
        point_id: UUID,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        self.points[point_id] = {"id": str(point_id), "vector": vector, "payload": payload}

    def set_payload(
        self,
        collection: str,
        *,
        point_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        self.points[point_id]["payload"].update(payload)

    def retrieve(self, collection: str, point_id: UUID) -> dict[str, Any] | None:
        return self.points.get(point_id)

    def search(
        self,
        collection: str,
        *,
        vector: list[float],
        limit: int,
        qdrant_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        for point in self.points.values():
            payload = point["payload"]
            if payload.get("status") != "active":
                continue
            if qdrant_filter:
                matches = all(
                    payload.get(condition["key"]) == condition["match"]["value"]
                    for condition in qdrant_filter.get("must", [])
                )
                if not matches:
                    continue
            result.append(point)
        return result[:limit]

    def scroll(
        self,
        collection: str,
        *,
        qdrant_filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return list(self.points.values())[:limit]


def make_service(repo: FakeRepository) -> KnowledgeEvolutionService:
    return KnowledgeEvolutionService(
        repository=repo,
        embedding=FakeEmbedding(),
        collection="cyberbrain_knowledge",
    )


def _process_lock_worker(lock_file: str, acquired, release) -> None:
    service = KnowledgeEvolutionService(
        repository=FakeRepository(),
        embedding=FakeEmbedding(),
        collection="cyberbrain_knowledge",
        process_lock_file=lock_file,
    )
    with service._process_guard():
        acquired.set()
        if release is not None:
            release.wait(5)


def store(service: KnowledgeEvolutionService, content: str):
    return service.store(
        content=content,
        domain="ops",
        topic="mcp",
        entity_type="decision",
        entity_name="provider_auth",
    )


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl is POSIX-only")
def test_process_lock_serializes_separate_processes(tmp_path) -> None:
    ctx = mp.get_context("fork")
    lock_file = str(tmp_path / "evolution.lock")
    first_acquired = ctx.Event()
    release_first = ctx.Event()
    second_acquired = ctx.Event()

    first = ctx.Process(
        target=_process_lock_worker,
        args=(lock_file, first_acquired, release_first),
    )
    second = ctx.Process(
        target=_process_lock_worker,
        args=(lock_file, second_acquired, None),
    )
    first.start()
    assert first_acquired.wait(2)
    second.start()
    assert not second_acquired.wait(0.25)
    release_first.set()
    assert second_acquired.wait(2)
    first.join(2)
    second.join(2)
    assert first.exitcode == 0
    assert second.exitcode == 0


def test_insert_new_record() -> None:
    repo = FakeRepository()
    result = store(make_service(repo), "Use bearer auth.")

    assert result.outcome == EvolutionOutcome.INSERT_NEW
    assert result.record.version == 1
    assert result.record.status.value == "active"


def test_exact_retry_is_no_change() -> None:
    repo = FakeRepository()
    service = make_service(repo)
    first = store(service, "Use bearer auth.")
    second = store(service, "Use bearer auth.")

    assert second.outcome == EvolutionOutcome.NO_CHANGE
    assert second.record.id == first.record.id
    assert len(repo.points) == 1


def test_evolution_supersedes_previous_version() -> None:
    repo = FakeRepository()
    service = make_service(repo)
    first = store(service, "Use bearer auth.")
    second = store(service, "Use bearer auth and fail closed.")

    assert second.outcome == EvolutionOutcome.EVOLVE
    assert second.record.version == 2
    assert second.record.supersedes_id == first.record.id
    assert repo.points[first.record.id]["payload"]["status"] == "superseded"
    assert repo.points[first.record.id]["payload"]["superseded_by_id"] == str(second.record.id)
    assert repo.points[second.record.id]["payload"]["status"] == "active"


def test_recovers_pending_evolution_after_activation_failure() -> None:
    class ActivationFailRepository(FakeRepository):
        def __init__(self) -> None:
            super().__init__()
            self.fail_next_activation = True

        def set_payload(
            self,
            collection: str,
            *,
            point_id: UUID,
            payload: dict[str, Any],
        ) -> None:
            if (
                self.fail_next_activation
                and payload.get("status") == "active"
                and self.points.get(point_id, {}).get("payload", {}).get("status") == "deprecated"
            ):
                self.fail_next_activation = False
                raise RuntimeError("simulated activation crash")
            super().set_payload(collection, point_id=point_id, payload=payload)

    repo = ActivationFailRepository()
    service = make_service(repo)
    first = store(service, "A")

    with pytest.raises(RuntimeError, match="simulated activation crash"):
        store(service, "B")

    active_after_failure = [
        point
        for point in repo.points.values()
        if point["payload"].get("status") == "active"
    ]
    assert active_after_failure == []

    recovered = store(service, "B")

    assert recovered.outcome == EvolutionOutcome.NO_CHANGE
    active = [
        point
        for point in repo.points.values()
        if point["payload"].get("status") == "active"
    ]
    assert len(active) == 1
    assert active[0]["payload"]["content"] == "B"
    assert repo.points[first.record.id]["payload"]["status"] == "superseded"


def test_recovers_pending_evolution_after_predecessor_update_failure() -> None:
    class PredecessorFailRepository(FakeRepository):
        def __init__(self) -> None:
            super().__init__()
            self.fail_next_supersede = True

        def set_payload(
            self,
            collection: str,
            *,
            point_id: UUID,
            payload: dict[str, Any],
        ) -> None:
            if self.fail_next_supersede and payload.get("status") == "superseded":
                self.fail_next_supersede = False
                raise RuntimeError("simulated predecessor crash")
            super().set_payload(collection, point_id=point_id, payload=payload)

    repo = PredecessorFailRepository()
    service = make_service(repo)
    first = store(service, "A")

    with pytest.raises(RuntimeError, match="simulated predecessor crash"):
        store(service, "B")

    assert repo.points[first.record.id]["payload"]["status"] == "active"

    recovered = store(service, "B")

    assert recovered.outcome == EvolutionOutcome.NO_CHANGE
    active = [
        point
        for point in repo.points.values()
        if point["payload"].get("status") == "active"
    ]
    assert len(active) == 1
    assert active[0]["payload"]["content"] == "B"


def test_startup_reconciliation_recovers_pending_after_activation_crash() -> None:
    class ActivationFailRepository(FakeRepository):
        def __init__(self) -> None:
            super().__init__()
            self.fail_next_activation = True

        def set_payload(
            self,
            collection: str,
            *,
            point_id: UUID,
            payload: dict[str, Any],
        ) -> None:
            if (
                self.fail_next_activation
                and payload.get("status") == "active"
                and self.points.get(point_id, {}).get("payload", {}).get("status") == "deprecated"
            ):
                self.fail_next_activation = False
                raise RuntimeError("simulated activation crash")
            super().set_payload(collection, point_id=point_id, payload=payload)

    repo = ActivationFailRepository()
    service = make_service(repo)
    first = store(service, "A")
    with pytest.raises(RuntimeError, match="simulated activation crash"):
        store(service, "B")

    restarted = make_service(repo)
    recovered = restarted.reconcile_pending()

    assert recovered == 1
    active = [
        point
        for point in repo.points.values()
        if point["payload"].get("status") == "active"
    ]
    assert len(active) == 1
    assert active[0]["payload"]["content"] == "B"
    assert repo.points[first.record.id]["payload"]["status"] == "superseded"


def test_startup_reconciliation_fails_on_multiple_pending_same_identity() -> None:
    repo = FakeRepository()
    service = make_service(repo)
    first = store(service, "A")
    previous_payload = repo.points[first.record.id]["payload"]

    for point_id in (
        UUID("11111111-1111-4111-8111-111111111111"),
        UUID("22222222-2222-4222-8222-222222222222"),
    ):
        payload = dict(previous_payload)
        payload.update(
            {
                "id": str(point_id),
                "content": f"pending-{point_id}",
                "content_hash": str(point_id),
                "version": 2,
                "status": "deprecated",
                "supersedes_id": str(first.record.id),
                "extensions": {
                    "_evolution_state": "pending_activation",
                    "_evolution_previous_id": str(first.record.id),
                },
            }
        )
        repo.points[point_id] = {
            "id": str(point_id),
            "vector": [0.1, 0.2, 0.3],
            "payload": payload,
        }

    with pytest.raises(ConflictError, match="multiple pending evolutions"):
        make_service(repo).reconcile_pending()


def test_multiple_active_versions_fail_loud() -> None:
    repo = FakeRepository()
    service = make_service(repo)
    first = store(service, "A")
    duplicate = dict(repo.points[first.record.id]["payload"])
    duplicate["id"] = "99aa2f4d-59d3-4d72-87aa-02ec5966255a"
    duplicate["content"] = "B"
    duplicate["content_hash"] = "other"
    repo.points[UUID(duplicate["id"])] = {
        "id": duplicate["id"],
        "vector": [0.1, 0.2, 0.3],
        "payload": duplicate,
    }

    with pytest.raises(ConflictError, match="multiple active versions"):
        store(service, "C")
