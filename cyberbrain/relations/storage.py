# SPDX-License-Identifier: MPL-2.0
"""Scoped Qdrant adjacency; projections are disposable, never graph truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cyberbrain.core.errors import ConfigurationError
from cyberbrain.tenancy import current_authority
from cyberbrain.tenancy.enforcement import TenancyOperation
from cyberbrain.tenancy.runtime import enforce_operation, scope_conditions

from .admission import require_review_authority
from .index import INDEX_FIELDS, INDEX_KEY, INDEX_PREFIX, project_relations


class RelationRepository(Protocol):
    def scroll_page(
        self, collection: str, *, qdrant_filter: dict, limit: int, offset: Any = None
    ) -> tuple[list[dict], Any]: ...
    def collection_info(self, name: str) -> dict | None: ...
    def create_payload_index(self, collection: str, *, field: str, schema: str) -> None: ...
    def set_payload(self, collection: str, *, point_id: Any, payload: dict) -> None: ...


class TraversalLimit(Exception):
    """A bounded phase cannot be completed safely."""


@dataclass
class ReadBudget:
    maximum: int
    used: int = 0

    def charge(self) -> None:
        if self.used >= self.maximum:
            raise TraversalLimit("storage_calls")
        self.used += 1


class RelationIndex:
    def __init__(
        self,
        repository: RelationRepository,
        knowledge_collection: str,
        episodic_collection: str,
        *,
        background: bool = False,
    ):
        self.repository = repository
        self.background = background
        self.knowledge_collection = knowledge_collection
        self.episodic_collection = episodic_collection
        self._verified = False

    def verify_indexes(self) -> None:
        self._verified = False
        info = self.repository.collection_info(self.knowledge_collection) or {}
        schema = info.get("payload_schema") or {}
        if any(
            (schema.get(field) or {}).get("data_type") != kind
            for field, kind in INDEX_FIELDS.items()
        ):
            raise ConfigurationError("relation payload indexes missing; prepare indexes required")
        self._verified = True

    def prepare_indexes(self) -> None:
        require_review_authority()
        enforce_operation(TenancyOperation.KNOWLEDGE_GET)
        for field, kind in INDEX_FIELDS.items():
            self.repository.create_payload_index(
                self.knowledge_collection, field=field, schema=kind
            )
        self.verify_indexes()

    def conditions(self, *, episode: bool = False) -> list[dict]:
        if current_authority() is None:
            raise ConfigurationError("relation reads require authenticated authority")
        plan = enforce_operation(
            TenancyOperation.BACKGROUND_EVIDENCE_READ
            if self.background
            else TenancyOperation.MEMORY_GET
            if episode
            else TenancyOperation.KNOWLEDGE_GET
        )
        return scope_conditions(plan)

    def read(
        self,
        *,
        must: list[dict],
        budget: ReadBudget,
        episode: bool = False,
        limit: int = 256,
        must_not: list[dict] | None = None,
        complete: bool = True,
    ) -> list[dict]:
        # Authority is checked before charging or making a storage request.
        conditions = self.conditions(episode=episode)
        budget.charge()
        query = {"must": [*conditions, *must]}
        if must_not:
            query["must_not"] = must_not
        points, continuation = self.repository.scroll_page(
            self.episodic_collection if episode else self.knowledge_collection,
            qdrant_filter=query,
            limit=limit,
        )
        if complete and continuation is not None:
            raise TraversalLimit("candidate_capacity")
        return points

    def require_ready(self, budget: ReadBudget) -> None:
        self.conditions()
        if not self._verified:
            raise ConfigurationError("relation indexes have not been verified")
        # Completeness is checked inside caller scope; never silently miss old rows.
        points = self.read(
            must=[
                {"key": "record_type", "match": {"value": "knowledge"}},
                {"key": "record_class", "match": {"value": "knowledge"}},
            ],
            must_not=[{"key": INDEX_PREFIX + ".schema_version", "match": {"value": 1}}],
            budget=budget,
            limit=1,
            complete=False,
        )
        if points:
            raise ConfigurationError("relation index is missing; rebuild required")

    def rebuild(self, *, maximum_records: int = 256) -> int:
        """Explicit bounded maintenance; audit the whole page before any mutation."""
        require_review_authority()
        enforce_operation(TenancyOperation.KNOWLEDGE_WRITE)
        if type(maximum_records) is not int or not 1 <= maximum_records <= 256:
            raise ValueError("rebuild maximum_records must be between 1 and 256")
        points = self.read(
            must=[
                {"key": "record_type", "match": {"value": "knowledge"}},
                {"key": "record_class", "match": {"value": "knowledge"}},
            ],
            budget=ReadBudget(1),
            limit=maximum_records,
        )
        from .admission import _canonical_payload

        pending = []
        for point in points:
            payload = _canonical_payload(point, record_type="knowledge", point_id=point["id"])
            extensions = dict(payload["extensions"])
            extensions[INDEX_KEY] = project_relations(payload)
            pending.append((point["id"], extensions))
        for point_id, extensions in pending:
            self.repository.set_payload(
                self.knowledge_collection, point_id=point_id, payload={"extensions": extensions}
            )
        return len(pending)
