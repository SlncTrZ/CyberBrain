# SPDX-License-Identifier: MPL-2.0
"""Explicit proposal/review through native Knowledge Evolution."""

from __future__ import annotations

import inspect
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from cyberbrain.core.errors import ConfigurationError, ConflictError
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.tenancy import OperationClass, current_authority
from cyberbrain.tenancy.enforcement import TenancyOperation
from cyberbrain.tenancy.runtime import enforce_operation

from .admission import _canonical_payload, require_review_authority
from .index import INDEX_KEY, verify_projection
from .models import RelationBundle, RelationStatus, bundle_from_extensions
from .storage import ReadBudget, RelationIndex


class RelationProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: UUID
    bundle: RelationBundle


class RelationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: UUID
    relation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["accepted", "rejected"]
    note: str = Field(min_length=1, max_length=1000)


class RelationReviewService:
    def __init__(self, index: RelationIndex, evolution: KnowledgeEvolutionService):
        self.index = index
        self.evolution = evolution

    def _source(self, source_id: UUID) -> dict:
        caller = current_authority()
        if caller is None or OperationClass.WRITE not in caller.grant.operations:
            raise ConfigurationError("relation proposal/review requires canonical write authority")
        points = self.index.read(
            must=[
                {"has_id": [str(source_id)]},
                {"key": "record_type", "match": {"value": "knowledge"}},
                {"key": "record_class", "match": {"value": "knowledge"}},
                {"key": "status", "match": {"value": "active"}},
                {"key": "ordinary_recall", "match": {"value": True}},
                {"key": "lifecycle_state", "match": {"value": "active"}},
            ],
            budget=ReadBudget(1),
        )
        if len(points) != 1:
            raise ConfigurationError("relation source unavailable")
        payload = _canonical_payload(points[0], record_type="knowledge", point_id=source_id)
        enforce_operation(TenancyOperation.KNOWLEDGE_WRITE, payload)
        if INDEX_KEY in payload["extensions"]:
            verify_projection(payload)
        return payload

    def _write(self, source: dict, bundle: RelationBundle):
        allowed = set(inspect.signature(KnowledgeEvolutionService.store).parameters)
        values = {key: value for key, value in source.items() if key in allowed}
        extensions = dict(source["extensions"])
        extensions.pop(INDEX_KEY, None)
        extensions["relations"] = bundle.model_dump(mode="json")
        values.update(extensions=extensions, expected_previous_id=UUID(source["id"]))
        return self.evolution.store(**values)

    def propose(self, source_id: UUID, bundle: RelationBundle):
        # Strict fresh validation prevents model_copy/model_construct bypass.
        bundle = RelationBundle.model_validate(bundle)
        if not bundle.edges or any(edge.status != RelationStatus.PROPOSED for edge in bundle.edges):
            raise ConfigurationError("proposal must contain only proposed assertions")
        source = self._source(source_id)
        previous = bundle_from_extensions(source["extensions"])
        additions = {edge.relation_id: edge for edge in previous.edges}
        for edge in bundle.edges:
            if edge.relation_id in additions and additions[edge.relation_id] != edge:
                raise ConflictError("proposal cannot replace an existing assertion")
            additions[edge.relation_id] = edge
        combined = RelationBundle(schema_version=1, edges=tuple(additions.values()))
        return self._write(source, combined)

    def review(self, source_id: UUID, relation_id: str, status: RelationStatus, note: str):
        require_review_authority()
        if status not in (RelationStatus.ACCEPTED, RelationStatus.REJECTED):
            raise ValueError("review status must be accepted or rejected")
        source = self._source(source_id)
        previous = bundle_from_extensions(source["extensions"])
        edges = []
        found = False
        for edge in previous.edges:
            if edge.relation_id == relation_id:
                found = True
                raw = edge.model_dump(mode="json")
                raw.update(status=status.value, review_note=note)
                edges.append(type(edge).model_validate(raw))
            else:
                edges.append(edge)
        if not found:
            raise ConfigurationError("relation assertion unavailable")
        return self._write(source, RelationBundle(schema_version=1, edges=tuple(edges)))
