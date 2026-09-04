# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class KnowledgeStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class Verification(StrEnum):
    USER_CONFIRMED = "user_confirmed"
    OBSERVED = "observed"
    TESTED = "tested"
    DERIVED = "derived"
    RESEARCH = "research"
    UNVERIFIED = "unverified"


class Origin(StrEnum):
    MANUAL = "manual"
    AGENT = "agent"
    INGESTION = "ingestion"
    DREAM = "dream"
    MIGRATION = "migration"


class DreamStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    SKIPPED = "skipped"
    FAILED = "failed"


class EpisodeRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    SUMMARY = "summary"
    OTHER = "other"


def utc_now() -> datetime:
    return datetime.now(UTC)


class KnowledgeRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    schema_version: int = 1
    record_type: str = "knowledge"

    content: str
    summary: str | None = None

    domain: str
    topic: str
    entity_type: str
    entity_name: str

    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    version: int = 1
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE
    supersedes_id: UUID | None = None
    superseded_by_id: UUID | None = None
    change_reason: str | None = None

    importance: str | None = None
    verification: Verification = Verification.UNVERIFIED
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    provenance_type: str | None = None
    source: str | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)

    origin: Origin = Origin.INGESTION
    dream_run_id: str | None = None
    negative_knowledge: bool = False

    content_hash: str
    embedding_version: str | None = None

    context: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("record_type")
    @classmethod
    def validate_record_type(cls, value: str) -> str:
        if value != "knowledge":
            raise ValueError("record_type must be 'knowledge'")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_knowledge_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("knowledge timestamps must include a timezone")
        return value.astimezone(UTC)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value < 1:
            raise ValueError("version must be >= 1")
        return value


class EpisodeRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    schema_version: int = 1
    record_type: str = "episode"

    content: str
    summary: str | None = None

    session_id: str
    event_time: datetime

    channel: str | None = None
    role: EpisodeRole | None = None
    agent: str | None = None
    project: str | None = None
    topic: str | None = None
    keywords: list[str] = Field(default_factory=list)
    importance: str | None = None
    source: str | None = None

    dream_status: DreamStatus = DreamStatus.PENDING
    dream_run_id: str | None = None
    dreamed_at: datetime | None = None

    content_hash: str
    embedding_version: str | None = None

    context: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("record_type")
    @classmethod
    def validate_record_type(cls, value: str) -> str:
        if value != "episode":
            raise ValueError("record_type must be 'episode'")
        return value

    @field_validator("event_time", "dreamed_at", "created_at")
    @classmethod
    def normalize_episode_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("episode timestamps must include a timezone")
        return value.astimezone(UTC)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("session_id must not be empty")
        return value
