# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from cyberbrain.core.errors import ConfigurationError
from cyberbrain.schemas.models import CURRENT_SCHEMA_VERSION, EpisodeRecord, KnowledgeRecord
from cyberbrain.storage.base import PointRepository
from cyberbrain.tenancy import OperationClass, current_authority
from cyberbrain.tenancy.enforcement import TenancyOperation
from cyberbrain.tenancy.runtime import enforce_operation, scope_conditions

from .models import EntityRef, RelationBundle, RelationScope, RelationStatus


def require_review_authority() -> None:
    authority = current_authority()
    if authority is None or OperationClass.ADMIN_REVIEW not in authority.grant.operations:
        raise ConfigurationError("relation review requires authenticated admin_review authority")


def _partition_conditions(scope: RelationScope, *, include_session: bool) -> list[dict]:
    return [
        {"is_empty": {"key": key}} if value is None else {"key": key, "match": {"value": value}}
        for key, value in scope.model_dump().items()
        if key != "session_id" or include_session
    ]


def _canonical_payload(point: Any, *, record_type: str, point_id: Any) -> dict:
    payload = (point or {}).get("payload") or {}
    if (
        point is None
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != CURRENT_SCHEMA_VERSION
        or payload.get("record_type") != record_type
        or str(point.get("id")) != str(point_id)
        or str(payload.get("id")) != str(point_id)
    ):
        raise ConfigurationError("relation endpoint or evidence unavailable")
    try:
        model = KnowledgeRecord if record_type == "knowledge" else EpisodeRecord
        return model.model_validate(payload).model_dump(mode="json")
    except (TypeError, ValueError):
        raise ConfigurationError("relation endpoint or evidence unavailable") from None


def admit_relations(
    *,
    raw: Any,
    source: EntityRef,
    repository: PointRepository,
    knowledge_collection: str,
    episodic_collection: str | None,
) -> RelationBundle:
    """Validate explicit assertions, never infer semantic entailment from ID existence."""
    try:
        bundle = RelationBundle.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        raise ConfigurationError("invalid relations schema or assertion") from None
    for edge in bundle.edges:
        if edge.source.key != source.key:
            raise ConfigurationError("relation source differs from canonical Knowledge identity")
        if edge.status != RelationStatus.PROPOSED:
            require_review_authority()

    # Permission checks precede any candidate read.
    knowledge_plan = enforce_operation(TenancyOperation.KNOWLEDGE_GET)
    has_episodes = any(
        ref.record_type == "episode" for edge in bundle.edges for ref in edge.evidence
    )
    episode_plan = enforce_operation(TenancyOperation.MEMORY_GET) if has_episodes else None
    if has_episodes and episodic_collection is None:
        raise ConfigurationError("episodic relation evidence repository is not configured")

    target_filter = {
        "must": [
            *_partition_conditions(source.scope, include_session=True),
            *scope_conditions(knowledge_plan),
            {"key": "status", "match": {"value": "active"}},
            {
                "should": [
                    {"key": "record_class", "match": {"value": "knowledge"}},
                    {"is_empty": {"key": "record_class"}},
                ]
            },
            {
                "should": [
                    {"key": "ordinary_recall", "match": {"value": True}},
                    {"is_empty": {"key": "ordinary_recall"}},
                ]
            },
        ]
    }
    historical_target_filter = {
        "must": [
            *_partition_conditions(source.scope, include_session=True),
            *scope_conditions(knowledge_plan),
            {"key": "record_class", "match": {"value": "knowledge"}},
        ]
    }
    targets: dict = {}
    evidence_payloads: dict = {}
    for edge in bundle.edges:
        historical = edge.status == RelationStatus.REJECTED
        target_key = (edge.target_record_id, historical)
        if target_key not in targets:
            targets[target_key] = repository.retrieve(
                knowledge_collection,
                edge.target_record_id,
                qdrant_filter=historical_target_filter if historical else target_filter,
            )
        target = targets[target_key]
        if target is None:
            raise ConfigurationError("relation endpoint or evidence unavailable")
        payload = _canonical_payload(
            target,
            record_type="knowledge",
            point_id=edge.target_record_id,
        )
        try:
            valid_target = (
                type(payload.get("schema_version")) is int
                and payload["schema_version"] == CURRENT_SCHEMA_VERSION
                and payload.get("record_type") == "knowledge"
                and EntityRef.from_payload(payload).key == edge.target.key
            )
        except (KeyError, TypeError, ValueError):
            valid_target = False
        if not valid_target:
            raise ConfigurationError("relation endpoint or evidence unavailable")

        for ref in edge.evidence:
            key = (ref.record_type, ref.id)
            if key in evidence_payloads:
                if not historical and evidence_payloads[key].get("ordinary_recall") is False:
                    raise ConfigurationError("relation endpoint or evidence unavailable")
                continue
            plan = knowledge_plan if ref.record_type == "knowledge" else episode_plan
            evidence_filter = {
                "must": [
                    *_partition_conditions(
                        source.scope,
                        include_session=source.scope.session_id is not None,
                    ),
                    *scope_conditions(plan),
                    {"key": "record_type", "match": {"value": ref.record_type}},
                ]
            }
            if ref.record_type == "knowledge":
                evidence_filter["must"].append(
                    {"key": "record_class", "match": {"value": "knowledge"}}
                )
            point = repository.retrieve(
                knowledge_collection if ref.record_type == "knowledge" else episodic_collection,
                ref.id,
                qdrant_filter=evidence_filter,
            )
            evidence_payload = _canonical_payload(
                point,
                record_type=ref.record_type,
                point_id=ref.id,
            )
            if (
                point is None
                or type(evidence_payload.get("schema_version")) is not int
                or evidence_payload.get("schema_version") != CURRENT_SCHEMA_VERSION
                or (not historical and evidence_payload.get("ordinary_recall") is False)
                or evidence_payload.get("record_type") != ref.record_type
            ):
                raise ConfigurationError("relation endpoint or evidence unavailable")
            evidence_payloads[key] = evidence_payload
    return bundle
