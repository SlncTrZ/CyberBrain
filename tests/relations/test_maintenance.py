# SPDX-License-Identifier: MPL-2.0
import json
from copy import deepcopy
from uuid import UUID, uuid4

import pytest

from cyberbrain.core.errors import ConfigurationError, ConflictError
from cyberbrain.relations.index import INDEX_KEY
from cyberbrain.relations.maintenance import RelationMaintenance
from cyberbrain.tenancy import bind_authority
from tests.relations.test_persistence import owner
from tests.relations.test_traversal import ready


class Snapshots:
    def __init__(self, repo):
        self.repo = repo

    def create_and_download(self, *, collection, destination):
        path = destination / (collection + ".snapshot")
        points = [
            point
            for key, point in self.repo.points.items()
            if self.repo.collections[key] == collection
        ]
        path.write_text(json.dumps(points))
        return path


def legacy_fixture():
    repo, records, index, _ = ready()
    for point in repo.points.values():
        point["payload"]["extensions"].pop(INDEX_KEY)
    return repo, records, RelationMaintenance(index)


def test_quiesced_backfill_is_checkpointed_idempotent_and_preserves_canonical_vectors(tmp_path):
    repo, _, maintenance = legacy_fixture()
    before = deepcopy(repo.points)
    checkpoint = tmp_path / "checkpoint"
    with bind_authority(owner()):
        census = maintenance.census()
        assert census.missing == 4 and census.records == 4
        maintenance.checkpoint(
            destination=checkpoint, snapshots=Snapshots(repo), writers_quiesced=True
        )
        after = maintenance.apply(
            checkpoint=checkpoint, expected_source_hash=census.source_hash, writers_quiesced=True
        )
        assert after.missing == 0 and after.source_hash == census.source_hash
        assert (
            maintenance.apply(
                checkpoint=checkpoint,
                expected_source_hash=census.source_hash,
                writers_quiesced=True,
            )
            == after
        )
    for point_id, point in repo.points.items():
        payload = deepcopy(point["payload"])
        payload["extensions"].pop(INDEX_KEY)
        assert payload == before[point_id]["payload"]
        assert point["vector"] == before[point_id]["vector"]
        assert point["id"] == before[point_id]["id"]
    assert len(list(checkpoint.glob("*.snapshot"))) == 2


@pytest.mark.parametrize("operation", ["checkpoint", "apply"])
def test_quiescence_is_required_before_backup_or_mutation(tmp_path, operation):
    repo, _, maintenance = legacy_fixture()
    before = deepcopy(repo.points)
    with bind_authority(owner()), pytest.raises(ConfigurationError, match="quiesced"):
        if operation == "checkpoint":
            maintenance.checkpoint(
                destination=tmp_path / "backup", snapshots=Snapshots(repo), writers_quiesced=False
            )
        else:
            maintenance.apply(checkpoint=tmp_path, expected_source_hash="x", writers_quiesced=False)
    assert repo.points == before


def test_changed_canonical_source_refuses_checkpoint_reuse(tmp_path):
    repo, records, maintenance = legacy_fixture()
    checkpoint = tmp_path / "checkpoint"
    with bind_authority(owner()):
        census = maintenance.checkpoint(
            destination=checkpoint, snapshots=Snapshots(repo), writers_quiesced=True
        )
        repo.points[records["a"].id]["payload"]["content"] = "Concurrent external write."
        before = deepcopy(repo.points)
        with pytest.raises(ConflictError, match="changed"):
            maintenance.apply(
                checkpoint=checkpoint,
                expected_source_hash=census.source_hash,
                writers_quiesced=True,
            )
    assert repo.points == before


@pytest.mark.parametrize("tamper", ["snapshot", "manifest"])
def test_corrupt_checkpoint_never_writes_projection(tmp_path, tamper):
    repo, _, maintenance = legacy_fixture()
    checkpoint = tmp_path / "checkpoint"
    with bind_authority(owner()):
        census = maintenance.checkpoint(
            destination=checkpoint, snapshots=Snapshots(repo), writers_quiesced=True
        )
        file = checkpoint / ("knowledge.snapshot" if tamper == "snapshot" else "manifest.json")
        file.write_text("{}")
        before = deepcopy(repo.points)
        with pytest.raises((ConfigurationError, ValueError)):
            maintenance.apply(
                checkpoint=checkpoint,
                expected_source_hash=census.source_hash,
                writers_quiesced=True,
            )
    assert repo.points == before


def test_namespace_collision_unknown_parent_schema_and_capacity_fail_before_writes():
    repo, records, maintenance = legacy_fixture()
    point = repo.points[records["a"].id]["payload"]
    with bind_authority(owner()):
        point["extensions"][INDEX_KEY] = {"legacy": "reserved-name collision"}
        with pytest.raises(ConfigurationError, match="inconsistent"):
            maintenance.census()
        point["extensions"].pop(INDEX_KEY)
        point["schema_version"] = 99
        with pytest.raises(ConfigurationError, match="unavailable"):
            maintenance.census()
        point["schema_version"] = 2
        maintenance.max_records = 1
        with pytest.raises(ConfigurationError, match="capacity"):
            maintenance.census()
    assert all(INDEX_KEY not in p["payload"]["extensions"] for p in repo.points.values())


def test_paged_census_and_apply_cover_more_than_one_page(tmp_path):
    repo, records, maintenance = legacy_fixture()
    template = repo.points[records["a"].id]
    for i in range(270):
        point = deepcopy(template)
        point["id"] = str(uuid4())
        point["payload"].update(id=point["id"], entity_name=f"extra-{i}")
        point["payload"]["extensions"].pop("relations")
        repo.upsert(
            "knowledge",
            point_id=UUID(point["id"]),
            vector=point["vector"],
            payload=point["payload"],
        )

    def scroll_page(collection, *, qdrant_filter, limit, offset=None):
        points = sorted(
            (
                deepcopy(p)
                for key, p in repo.points.items()
                if repo.collections[key] == collection and repo.match(p, qdrant_filter)
            ),
            key=lambda p: p["id"],
        )
        start = offset or 0
        return points[start : start + limit], (
            start + limit if start + limit < len(points) else None
        )

    repo.scroll_page = scroll_page
    with bind_authority(owner()):
        census = maintenance.checkpoint(
            destination=tmp_path / "checkpoint", snapshots=Snapshots(repo), writers_quiesced=True
        )
        assert census.records == 274 and census.pages == 2
        after = maintenance.apply(
            checkpoint=tmp_path / "checkpoint",
            expected_source_hash=census.source_hash,
            writers_quiesced=True,
        )
        assert (
            after.records == 274 and after.missing == 0 and after.source_hash == census.source_hash
        )
