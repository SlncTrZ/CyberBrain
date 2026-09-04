# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID

from cyberbrain.core.content import content_hash, normalize_content
from cyberbrain.core.errors import ConflictError
from cyberbrain.core.secrets import SecretScanner
from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.schemas.models import (
    KnowledgeRecord,
    KnowledgeStatus,
    Origin,
    Verification,
    utc_now,
)
from cyberbrain.storage.base import PointRepository

_EVOLUTION_STATE_KEY = "_evolution_state"
_EVOLUTION_PREVIOUS_ID_KEY = "_evolution_previous_id"
_PENDING = "pending_activation"
_COMMITTED = "committed"
_ABORTED = "aborted"


class EvolutionOutcome(StrEnum):
    INSERT_NEW = "insert_new"
    NO_CHANGE = "no_change"
    EVOLVE = "evolve"


@dataclass(frozen=True)
class EvolutionResult:
    outcome: EvolutionOutcome
    record: KnowledgeRecord
    previous_id: UUID | None = None


class KnowledgeEvolutionService:
    def __init__(
        self,
        *,
        repository: PointRepository,
        embedding: EmbeddingProvider,
        collection: str,
        secret_scanner: SecretScanner | None = None,
        process_lock_file: str | None = None,
    ) -> None:
        self._repository = repository
        self._embedding = embedding
        self._collection = collection
        self._secret_scanner = secret_scanner or SecretScanner()
        self._process_lock_file = process_lock_file
        self._locks: dict[str, Lock] = {}
        self._locks_guard = Lock()

    def _identity_key(
        self,
        *,
        domain: str,
        topic: str,
        entity_type: str,
        entity_name: str,
        context: dict[str, Any] | None,
    ) -> str:
        context_items = sorted((context or {}).items())
        return "|".join(
            [
                domain.strip().lower(),
                topic.strip().lower(),
                entity_type.strip().lower(),
                entity_name.strip().lower(),
                repr(context_items),
            ]
        )

    def _lock_for(self, identity: str) -> Lock:
        with self._locks_guard:
            return self._locks.setdefault(identity, Lock())

    @contextmanager
    def _process_guard(self):
        if self._process_lock_file is None:
            yield
            return
        try:
            import fcntl
        except ImportError as exc:
            raise RuntimeError(
                "knowledge evolution process lock requires fcntl support"
            ) from exc
        path = Path(self._process_lock_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _active_filter(
        self,
        *,
        domain: str,
        topic: str,
        entity_type: str,
        entity_name: str,
    ) -> dict[str, Any]:
        return {
            "must": [
                {"key": "domain", "match": {"value": domain}},
                {"key": "topic", "match": {"value": topic}},
                {"key": "entity_type", "match": {"value": entity_type}},
                {"key": "entity_name", "match": {"value": entity_name}},
                {"key": "status", "match": {"value": KnowledgeStatus.ACTIVE.value}},
            ]
        }

    def _pending_filter(
        self,
        *,
        domain: str,
        topic: str,
        entity_type: str,
        entity_name: str,
    ) -> dict[str, Any]:
        return {
            "must": [
                {"key": "domain", "match": {"value": domain}},
                {"key": "topic", "match": {"value": topic}},
                {"key": "entity_type", "match": {"value": entity_type}},
                {"key": "entity_name", "match": {"value": entity_name}},
                {"key": "status", "match": {"value": KnowledgeStatus.DEPRECATED.value}},
                {
                    "key": f"extensions.{_EVOLUTION_STATE_KEY}",
                    "match": {"value": _PENDING},
                },
            ]
        }

    def reconcile_pending(self, *, max_pending: int = 1000) -> int:
        if max_pending < 1:
            raise ValueError("max_pending must be >= 1")
        with self._process_guard():
            points = self._repository.scroll(
                self._collection,
                qdrant_filter={
                    "must": [
                        {"key": "status", "match": {"value": KnowledgeStatus.DEPRECATED.value}},
                        {
                            "key": f"extensions.{_EVOLUTION_STATE_KEY}",
                            "match": {"value": _PENDING},
                        },
                    ]
                },
                limit=max_pending + 1,
            )
            pending = [
                point
                for point in points
                if (point.get("payload") or {}).get("status")
                == KnowledgeStatus.DEPRECATED.value
                and self._pending_state(point) == _PENDING
            ]
            if len(pending) > max_pending:
                raise ConflictError("pending evolution reconciliation limit exceeded")

            identities: dict[str, tuple[str, str, str, str, dict[str, Any]]] = {}
            for point in pending:
                payload = point.get("payload") or {}
                required = {
                    key: str(payload.get(key) or "").strip()
                    for key in ("domain", "topic", "entity_type", "entity_name")
                }
                if not all(required.values()):
                    raise ConflictError("pending evolution is missing canonical identity fields")
                context = dict(payload.get("context") or {})
                identity = self._identity_key(
                    domain=required["domain"],
                    topic=required["topic"],
                    entity_type=required["entity_type"],
                    entity_name=required["entity_name"],
                    context=context,
                )
                if identity in identities:
                    raise ConflictError(
                        "multiple pending evolutions exist for canonical entity identity"
                    )
                identities[identity] = (
                    required["domain"],
                    required["topic"],
                    required["entity_type"],
                    required["entity_name"],
                    context,
                )

            for identity, values in identities.items():
                domain, topic, entity_type, entity_name, context = values
                with self._lock_for(identity):
                    self._recover_pending(
                        domain=domain,
                        topic=topic,
                        entity_type=entity_type,
                        entity_name=entity_name,
                        context=context,
                    )
            return len(identities)

    def store(
        self,
        *,
        content: str,
        domain: str,
        topic: str,
        entity_type: str,
        entity_name: str,
        summary: str | None = None,
        project: str | None = None,
        change_reason: str | None = None,
        importance: str | None = None,
        verification: Verification = Verification.UNVERIFIED,
        confidence: float | None = None,
        provenance_type: str | None = None,
        source: str | None = None,
        evidence_ids: list[UUID] | None = None,
        origin: Origin = Origin.INGESTION,
        dream_run_id: str | None = None,
        negative_knowledge: bool = False,
        context: dict[str, Any] | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> EvolutionResult:
        normalized = normalize_content(content)
        self._secret_scanner.assert_safe(
            normalized,
            summary,
            project,
            change_reason,
            source,
            repr(context or {}),
            repr(extensions or {}),
        )
        digest = content_hash(normalized)
        context_value = context or {}
        identity = self._identity_key(
            domain=domain,
            topic=topic,
            entity_type=entity_type,
            entity_name=entity_name,
            context=context_value,
        )

        with self._process_guard():
            with self._lock_for(identity):
                self._recover_pending(
                    domain=domain,
                    topic=topic,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    context=context_value,
                )

                lookup_vector = self._embedding.embed(f"{topic} {entity_name}")
                active = self._repository.search(
                    self._collection,
                    vector=lookup_vector,
                    limit=10,
                    qdrant_filter=self._active_filter(
                        domain=domain,
                        topic=topic,
                        entity_type=entity_type,
                        entity_name=entity_name,
                    ),
                )

                exact_context = [
                    point
                    for point in active
                    if (point.get("payload") or {}).get("context", {}) == context_value
                ]
                if len(exact_context) > 1:
                    raise ConflictError(
                        "multiple active versions exist for canonical entity identity"
                    )

                previous = exact_context[0] if exact_context else None
                previous_payload = (previous or {}).get("payload") or {}
                previous_id = UUID(str(previous["id"])) if previous else None

                if previous and previous_payload.get("content_hash") == digest:
                    return EvolutionResult(
                        outcome=EvolutionOutcome.NO_CHANGE,
                        record=KnowledgeRecord.model_validate(previous_payload),
                        previous_id=previous_id,
                    )

                version = int(previous_payload.get("version", 0)) + 1 if previous else 1
                now = utc_now()
                base_extensions = dict(extensions or {})
                record = KnowledgeRecord(
                    content=normalized,
                    summary=summary,
                    domain=domain,
                    topic=topic,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    project=project,
                    version=version,
                    status=(
                        KnowledgeStatus.DEPRECATED
                        if previous_id is not None
                        else KnowledgeStatus.ACTIVE
                    ),
                    supersedes_id=previous_id,
                    change_reason=change_reason,
                    importance=importance,
                    verification=verification,
                    confidence=confidence,
                    provenance_type=provenance_type,
                    source=source,
                    evidence_ids=evidence_ids or [],
                    origin=origin,
                    dream_run_id=dream_run_id,
                    negative_knowledge=negative_knowledge,
                    content_hash=digest,
                    embedding_version=self._embedding.version,
                    context=context_value,
                    extensions=self._staging_extensions(base_extensions, previous_id),
                    created_at=now,
                    updated_at=now,
                )
                vector = self._embedding.embed(record.content)
                self._repository.upsert(
                    self._collection,
                    point_id=record.id,
                    vector=vector,
                    payload=record.model_dump(mode="json"),
                )

                if previous_id is None:
                    return EvolutionResult(outcome=EvolutionOutcome.INSERT_NEW, record=record)

                self._commit_staged_evolution(
                    staged=record,
                    previous_id=previous_id,
                    previous_payload=previous_payload,
                )
                committed = record.model_copy(
                    update={
                        "status": KnowledgeStatus.ACTIVE,
                        "extensions": self._committed_extensions(base_extensions),
                        "updated_at": now,
                    }
                )
                return EvolutionResult(
                    outcome=EvolutionOutcome.EVOLVE,
                    record=committed,
                    previous_id=previous_id,
                )

    def _recover_pending(
        self,
        *,
        domain: str,
        topic: str,
        entity_type: str,
        entity_name: str,
        context: dict[str, Any],
    ) -> None:
        pending = self._repository.scroll(
            self._collection,
            qdrant_filter=self._pending_filter(
                domain=domain,
                topic=topic,
                entity_type=entity_type,
                entity_name=entity_name,
            ),
            limit=20,
        )
        exact = [
            point
            for point in pending
            if (point.get("payload") or {}).get("context", {}) == context
            and self._pending_state(point) == _PENDING
        ]
        if not exact:
            return
        if len(exact) > 1:
            raise ConflictError("multiple pending evolutions exist for canonical entity identity")

        point = exact[0]
        payload = point.get("payload") or {}
        staged_id = UUID(str(point["id"]))
        previous_raw = (payload.get("extensions") or {}).get(_EVOLUTION_PREVIOUS_ID_KEY)
        if not previous_raw:
            raise ConflictError("pending evolution is missing previous knowledge id")
        previous_id = UUID(str(previous_raw))

        previous = self._repository.retrieve(self._collection, previous_id)
        if previous is None:
            raise ConflictError("pending evolution previous knowledge record is missing")
        previous_payload = previous.get("payload") or {}
        previous_status = previous_payload.get("status")
        previous_next = previous_payload.get("superseded_by_id")

        if previous_status == KnowledgeStatus.ACTIVE.value:
            if previous_next not in (None, "", str(staged_id)):
                raise ConflictError("active previous record points to a different successor")
            self._repository.set_payload(
                self._collection,
                point_id=previous_id,
                payload={
                    "status": KnowledgeStatus.SUPERSEDED.value,
                    "superseded_by_id": str(staged_id),
                    "updated_at": utc_now().isoformat(),
                },
            )
        elif not (
            previous_status == KnowledgeStatus.SUPERSEDED.value
            and str(previous_next) == str(staged_id)
        ):
            raise ConflictError("pending evolution previous record is in an inconsistent state")

        self._activate_staged(staged_id, payload)

    def _commit_staged_evolution(
        self,
        *,
        staged: KnowledgeRecord,
        previous_id: UUID,
        previous_payload: dict[str, Any],
    ) -> None:
        current_next = previous_payload.get("superseded_by_id")
        if current_next not in (None, "", str(staged.id)):
            raise ConflictError("previous knowledge already points to a different successor")

        now = utc_now()
        self._repository.set_payload(
            self._collection,
            point_id=previous_id,
            payload={
                "status": KnowledgeStatus.SUPERSEDED.value,
                "superseded_by_id": str(staged.id),
                "updated_at": now.isoformat(),
            },
        )
        try:
            self._activate_staged(staged.id, staged.model_dump(mode="json"))
        except Exception:
            # The pending staged record remains recoverable. A later store call
            # completes activation after verifying the predecessor linkage.
            raise

    def _activate_staged(self, staged_id: UUID, payload: dict[str, Any]) -> None:
        extensions = dict(payload.get("extensions") or {})
        extensions[_EVOLUTION_STATE_KEY] = _COMMITTED
        extensions.pop(_EVOLUTION_PREVIOUS_ID_KEY, None)
        self._repository.set_payload(
            self._collection,
            point_id=staged_id,
            payload={
                "status": KnowledgeStatus.ACTIVE.value,
                "extensions": extensions,
                "updated_at": utc_now().isoformat(),
            },
        )

    @staticmethod
    def _staging_extensions(
        extensions: dict[str, Any],
        previous_id: UUID | None,
    ) -> dict[str, Any]:
        result = dict(extensions)
        if previous_id is None:
            return result
        result[_EVOLUTION_STATE_KEY] = _PENDING
        result[_EVOLUTION_PREVIOUS_ID_KEY] = str(previous_id)
        return result

    @staticmethod
    def _committed_extensions(extensions: dict[str, Any]) -> dict[str, Any]:
        result = dict(extensions)
        result[_EVOLUTION_STATE_KEY] = _COMMITTED
        result.pop(_EVOLUTION_PREVIOUS_ID_KEY, None)
        return result

    @staticmethod
    def _pending_state(point: dict[str, Any]) -> str | None:
        payload = point.get("payload") or {}
        extensions = payload.get("extensions") or {}
        return extensions.get(_EVOLUTION_STATE_KEY)
