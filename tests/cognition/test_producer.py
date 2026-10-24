# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

from cyberbrain.cognition.prediction import (
    PredictionLearningService,
)
from cyberbrain.cognition.producer import PredictionHandle, track_prediction
from cyberbrain.memory.service import MemoryService


class MockRepo:
    def __init__(self):
        self.points = {}

    def upsert(self, collection, point_id, vector, payload):
        self.points[point_id] = {"id": str(point_id), "vector": vector, "payload": payload}

    def retrieve(self, collection, point_id, qdrant_filter=None):
        return self.points.get(point_id)

    def scroll(self, collection, qdrant_filter=None, limit=100):
        items = list(self.points.values())
        if qdrant_filter:
            must = qdrant_filter.get("must") or []
            filtered = []
            for item in items:
                match = True
                payload = item["payload"]
                for cond in must:
                    if "key" in cond and "match" in cond:
                        if payload.get(cond["key"]) != cond["match"]["value"]:
                            match = False
                            break
                if match:
                    filtered.append(item)
            items = filtered
        return items[:limit]

    def scroll_page(self, collection, qdrant_filter=None, limit=100, offset=None):
        return self.scroll(collection, qdrant_filter=qdrant_filter, limit=limit), None


class MockEmbedding:
    dimension = 3
    version = "v1"

    def embed(self, text):
        return [0.1, 0.2, 0.3]


def setup_service():
    repo = MockRepo()
    embedding = MockEmbedding()
    memory = MemoryService(
        repository=repo,
        embedding=embedding,
        collection="test_episodic",
    )
    return PredictionLearningService(
        memory=memory,
        repository=repo,
        episodic_collection="test_episodic",
    )


def test_track_prediction_success():
    service = setup_service()
    with track_prediction(
        service,
        expected_outcome="All tasks finish cleanly",
        confidence=0.92,
        action="Run build",
    ) as handle:
        assert isinstance(handle, PredictionHandle)
        assert handle.prediction_id is not None
        assert not handle.resolved

    assert handle.resolved
    obs = service.observe()
    assert obs.predictions_total == 1
    assert obs.outcomes_total == 1
    assert obs.resolved_predictions == 1


def test_track_prediction_exception_auto_contradicted():
    service = setup_service()
    with pytest.raises(RuntimeError, match="boom"):
        with track_prediction(
            service,
            expected_outcome="Will not fail",
            confidence=0.85,
            action="Dangerous step",
        ) as handle:
            raise RuntimeError("boom")

    assert handle.resolved
    obs = service.observe()
    assert obs.predictions_total == 1
    assert obs.outcomes_total == 1
    assert obs.resolved_predictions == 1


def test_run_command_with_prediction():
    import sys

    from cyberbrain.cognition.producer import run_command_with_prediction

    service = setup_service()
    code = run_command_with_prediction(
        service,
        command=[sys.executable, "-c", "print('OK')"],
        action="Verify echo",
        expected_outcome="Exit code 0",
        confidence=0.95,
        session_id="test_cmd_session",
        project="test_proj",
        topic="test_topic",
    )
    assert code == 0
    obs = service.observe()
    assert obs.predictions_total == 1
    assert obs.resolved_predictions == 1
