# SPDX-License-Identifier: MPL-2.0
"""Explicit relation recall with complete path/evidence context packing."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from cyberbrain.core.token_budget import DeterministicTokenCounter

from .admission import _canonical_payload
from .index import verify_projection
from .models import EntityRef, RelationStatus, bundle_from_extensions
from .storage import ReadBudget, TraversalLimit
from .traversal import RelationTraversal, TraversalPolicy, _time, _visible


class RelationRecallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed_ids: tuple[UUID, ...] = Field(min_length=1, max_length=128)
    policy: TraversalPolicy = Field(default_factory=TraversalPolicy)
    context_tokens: int = Field(default=4096, strict=True, ge=512, le=16384)
    record_tokens: int = Field(default=256, strict=True, ge=32, le=1024)


class RelationRecallService:
    def __init__(self, traversal: RelationTraversal):
        self.traversal = traversal
        self.counter = DeterministicTokenCounter()

    def recall(self, request: RelationRecallRequest) -> dict:
        result = self.traversal.traverse(list(request.seed_ids), request.policy)
        raw_paths = result["paths"]
        result = {
            **result,
            "paths": [],
            "records": {},
            "context_budget": request.context_tokens,
            "estimated_tokens": 0,
        }
        budget = ReadBudget(request.policy.max_storage_calls, result["storage_calls"])
        reasons = set(result["truncation_reasons"])
        identifiers = {"knowledge": set(), "episode": set()}
        for path in raw_paths:
            identifiers["knowledge"].update(path["record_ids"])
            for step in path["steps"]:
                identifiers["knowledge"].add(step["owner_record_id"])
                for ref in step["evidence"]:
                    identifiers[ref["record_type"]].add(ref["id"])
        payloads = {}
        try:
            for kind, ids in identifiers.items():
                if not ids:
                    continue
                points = self.traversal.index.read(
                    must=[
                        {"has_id": sorted(ids)},
                        {"key": "record_type", "match": {"value": kind}},
                    ],
                    budget=budget,
                    episode=kind == "episode",
                )
                for point in points:
                    payload = _canonical_payload(point, record_type=kind, point_id=point["id"])
                    payloads[(kind, payload["id"])] = payload
        except TraversalLimit as exc:
            # Context cannot contain paths whose full typed proof set wasn't hydrated.
            reasons.add(str(exc))
            raw_paths = []
        at = datetime.fromisoformat(result["evaluated_at"]).astimezone(UTC)

        def visible(payload, *, endpoint=False):
            if payload is None or not _visible(payload) or _time(payload["created_at"]) > at:
                return False
            if payload["record_type"] == "episode":
                return _time(payload["event_time"]) <= at
            if payload["record_class"] != "knowledge" or payload["status"] not in (
                "active",
                "superseded",
            ):
                return False
            if payload["extensions"].get("_evolution_state") in ("pending_activation", "aborted"):
                return False
            return not endpoint or request.policy.as_of is not None or payload["status"] == "active"

        for path in raw_paths:
            refs = {("knowledge", value) for value in path["record_ids"]}
            valid = all(visible(payloads.get(ref), endpoint=True) for ref in refs)
            if valid:
                valid = all(
                    EntityRef.from_payload(payloads[("knowledge", point_id)]).key == key
                    for point_id, key in zip(path["record_ids"], path["node_keys"], strict=True)
                )
            for position, step in enumerate(path["steps"]):
                owner = payloads.get(("knowledge", step["owner_record_id"]))
                if not visible(owner, endpoint=True) or owner["version"] != step["owner_version"]:
                    valid = False
                    break
                verify_projection(owner)
                edge = next(
                    (
                        edge
                        for edge in bundle_from_extensions(owner["extensions"]).edges
                        if edge.relation_id == step["relation_id"]
                    ),
                    None,
                )
                if (
                    edge is None
                    or edge.status != RelationStatus.ACCEPTED
                    or str(edge.target_record_id) != step["target_record_id"]
                    or edge.valid_from > at
                    or (edge.valid_until is not None and at >= edge.valid_until)
                ):
                    valid = False
                    break
                endpoint_keys = (edge.source.key, edge.target.key)
                if step["direction"] == "in":
                    endpoint_keys = tuple(reversed(endpoint_keys))
                if (
                    tuple(path["node_keys"][position : position + 2]) != endpoint_keys
                    or step["kind"] != edge.kind.value
                    or _time(step["valid_from"]) != edge.valid_from
                    or (None if step["valid_until"] is None else _time(step["valid_until"]))
                    != edge.valid_until
                ):
                    valid = False
                    break
                canonical_proofs = [ref.model_dump(mode="json") for ref in edge.evidence]
                if canonical_proofs != step["evidence"]:
                    valid = False
                    break
                refs.add(("knowledge", step["owner_record_id"]))
                for proof in canonical_proofs:
                    ref = (proof["record_type"], proof["id"])
                    refs.add(ref)
                    proof_payload = payloads.get(ref)
                    if not visible(proof_payload):
                        valid = False
                    elif any(
                        proof_payload.get(key) != value
                        for key, value in edge.source.scope.model_dump().items()
                        if key != "session_id" or value is not None
                    ):
                        valid = False
            if not valid:
                reasons.add("revalidation")
                continue
            records = dict(result["records"])
            for kind, point_id in sorted(refs):
                payload = payloads[(kind, point_id)]
                text = payload["content"]
                records[kind + ":" + point_id] = {
                    "id": point_id,
                    "record_type": kind,
                    "text": self.counter.clip_to_tokens(text, request.record_tokens),
                    "text_clipped": self.counter.estimate_tokens(text) > request.record_tokens,
                    **{
                        key: payload[key]
                        for key in ("entity_name", "topic", "version", "created_at", "event_time")
                        if key in payload
                    },
                }
            proposed = {**result, "paths": [*result["paths"], path], "records": records}
            # Reserve a small envelope allowance for final truncation/call/token metadata.
            if (
                self.counter.estimate_tokens(json.dumps(proposed, ensure_ascii=False))
                > request.context_tokens - 64
            ):
                reasons.add("context_tokens")
                continue
            result = proposed
        result["storage_calls"] = budget.used
        result["truncation_reasons"] = sorted(reasons)
        result["truncated"] = bool(reasons)
        # Counts distinguish validated exploration from context actually returned.
        result["returned_path_count"] = len(result["paths"])
        result["returned_record_count"] = len(result["records"])
        for _ in range(3):
            result["estimated_tokens"] = self.counter.estimate_tokens(
                json.dumps(result, ensure_ascii=False)
            )
        return result
