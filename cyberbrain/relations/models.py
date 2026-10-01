# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cyberbrain.tenancy.normalization import normalize_identifier

RELATIONS_KEY = "relations"
IDENTITY_FIELDS = ("tenant", "user", "agent", "project", "session_id")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class RelationScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    tenant: str | None = None
    user: str | None = None
    agent: str | None = None
    project: str | None = None
    session_id: str | None = None

    @field_validator(*IDENTITY_FIELDS)
    @classmethod
    def normalize_scope(cls, value: str | None) -> str | None:
        if value is not None and normalize_identifier(value) != value:
            raise ValueError("relation scope must use canonical normalized identifiers")
        return value


class EntityRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    domain: str = Field(min_length=1, max_length=256)
    topic: str = Field(min_length=1, max_length=256)
    entity_type: str = Field(min_length=1, max_length=256)
    entity_name: str = Field(min_length=1, max_length=256)
    context: dict[str, Any] = Field(default_factory=dict)
    scope: RelationScope = Field(default_factory=RelationScope)

    @field_validator("domain", "topic", "entity_type", "entity_name")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("entity identity must use exact canonical labels")
        return value

    @field_validator("context")
    @classmethod
    def validate_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = canonical_json(value)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("entity context must be finite JSON") from exc
        if len(encoded.encode("utf-8")) > 16_384:
            raise ValueError("entity context exceeds 16384 bytes")
        return json.loads(encoded)

    @property
    def key(self) -> str:
        return fingerprint(self.model_dump(mode="json"))

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> EntityRef:
        return cls(
            **{
                field: payload[field] for field in ("domain", "topic", "entity_type", "entity_name")
            },
            context=payload.get("context") or {},
            scope=RelationScope(**{field: payload.get(field) for field in IDENTITY_FIELDS}),
        )


class RelationKind(StrEnum):
    DEPENDS_ON = "depends_on"
    PART_OF = "part_of"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CAUSES = "causes"
    # supersedes is derived from native Evolution links, never caller-created.


class RelationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    record_type: Literal["knowledge", "episode"]
    id: UUID


class RelationEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    relation_id: str | None = None
    kind: RelationKind
    source: EntityRef
    target: EntityRef
    target_record_id: UUID
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=32)
    status: RelationStatus = RelationStatus.PROPOSED
    valid_from: datetime
    valid_until: datetime | None = None
    review_note: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("valid_from", "valid_until")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("relation time requires an explicit timezone")
            return value.astimezone(UTC)
        return None

    @model_validator(mode="after")
    def validate_edge(self) -> RelationEdge:
        if self.source.key == self.target.key:
            raise ValueError("self relations are not admitted")
        if self.source.scope != self.target.scope:
            raise ValueError("cross-partition relations are not admitted")
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must follow valid_from")
        if self.status != RelationStatus.PROPOSED and not (
            self.review_note and self.review_note.strip()
        ):
            raise ValueError("reviewed relations require a review note")
        evidence = tuple(sorted(set(self.evidence), key=lambda ref: (ref.record_type, str(ref.id))))
        object.__setattr__(self, "evidence", evidence)
        endpoints = [self.source.key, self.target.key]
        if self.kind == RelationKind.CONTRADICTS:
            endpoints.sort()
        expected = fingerprint({"kind": self.kind.value, "endpoints": endpoints})
        if self.relation_id is not None and self.relation_id != expected:
            raise ValueError("relation_id does not match canonical endpoints and kind")
        object.__setattr__(self, "relation_id", expected)
        return self


class RelationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal[1]
    edges: tuple[RelationEdge, ...] = Field(default=(), max_length=64)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("unknown relations schema")
        return value

    @model_validator(mode="after")
    def validate_bundle(self) -> RelationBundle:
        if len({ref for edge in self.edges for ref in edge.evidence}) > 128:
            raise ValueError("relation bundle exceeds 128 distinct evidence references")
        ids = [edge.relation_id for edge in self.edges]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate relation identity")
        object.__setattr__(
            self, "edges", tuple(sorted(self.edges, key=lambda edge: edge.relation_id))
        )
        return self

    @property
    def digest(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


def bundle_from_extensions(extensions: dict[str, Any]) -> RelationBundle:
    raw = extensions.get(RELATIONS_KEY, {"schema_version": 1, "edges": []})
    return RelationBundle.model_validate(raw)
