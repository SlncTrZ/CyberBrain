# SPDX-License-Identifier: MPL-2.0
"""Bounded BFS over reviewed assertions, preserving each explicit path."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cyberbrain.core.errors import ConfigurationError

from .admission import _canonical_payload, _partition_conditions
from .index import INDEX_PREFIX, verify_projection
from .models import EntityRef, RelationKind, RelationStatus, bundle_from_extensions
from .storage import ReadBudget, RelationIndex, TraversalLimit


class TraversalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    depth: int = Field(default=2, strict=True, ge=1, le=3)
    max_nodes: int = Field(default=32, strict=True, ge=1, le=128)
    max_edges: int = Field(default=64, strict=True, ge=1, le=256)
    max_paths: int = Field(default=128, strict=True, ge=1, le=512)
    max_storage_calls: int = Field(default=8, strict=True, ge=1, le=32)
    direction: Literal["out", "in", "both"] = "out"
    kinds: frozenset[RelationKind] = Field(default_factory=lambda: frozenset(RelationKind))
    as_of: datetime | None = None

    @field_validator("as_of")
    @classmethod
    def aware_time(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("as_of requires a timezone")
            return value.astimezone(UTC)
        return value


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _visible(payload: dict) -> bool:
    return payload.get("ordinary_recall") is True and payload.get("lifecycle_state") == "active"


class RelationTraversal:
    def __init__(self, index: RelationIndex):
        self.index = index

    def traverse(self, seed_ids: list[UUID], policy: TraversalPolicy | None = None) -> dict:
        policy = policy or TraversalPolicy()
        if not seed_ids or len(seed_ids) > policy.max_nodes:
            raise ValueError("seed count must be within node budget")
        seed_ids = sorted({str(UUID(str(value))) for value in seed_ids})
        now = datetime.now(UTC)
        at = policy.as_of or now
        if at > now:
            raise ValueError("as_of cannot be in the future")
        budget = ReadBudget(policy.max_storage_calls)
        paths: list[dict] = []
        nodes: set[str] = set()
        edge_ids: set[str] = set()
        reasons: set[str] = set()
        base = [
            {"key": "record_type", "match": {"value": "knowledge"}},
            {"key": "record_class", "match": {"value": "knowledge"}},
        ]
        temporal = [{"key": "created_at", "range": {"lte": at.isoformat()}}]
        current = [] if policy.as_of else [{"key": "status", "match": {"value": "active"}}]

        def canonical(point, record_type="knowledge"):
            return _canonical_payload(point, record_type=record_type, point_id=point["id"])

        def head_map(points):
            groups = {}
            for point in points:
                payload = canonical(point)
                verify_projection(payload)
                try:
                    key = EntityRef.from_payload(payload).key
                except (ValueError, KeyError, TypeError):
                    continue
                if _time(payload["created_at"]) > at:
                    continue
                if payload["extensions"].get("_evolution_state") in (
                    "pending_activation",
                    "aborted",
                ):
                    continue
                groups.setdefault(key, []).append(payload)
            heads = {}
            for key, candidates in groups.items():
                if policy.as_of:
                    version = max(p["version"] for p in candidates)
                    candidates = [p for p in candidates if p["version"] == version]
                else:
                    candidates = [p for p in candidates if p["status"] == "active"]
                if len(candidates) > 1:
                    raise ConfigurationError("ambiguous relation entity head")
                if candidates and candidates[0]["status"] in ("active", "superseded"):
                    heads[key] = candidates[0]
            return heads

        def eligible(payload):
            return (
                _visible(payload)
                and _time(payload["created_at"]) <= at
                and (
                    payload["record_type"] != "knowledge"
                    or (
                        payload["status"] in ("active", "superseded")
                        and payload["extensions"].get("_evolution_state")
                        not in ("pending_activation", "aborted")
                    )
                )
            )

        try:
            self.index.require_ready(budget)
            seed_points = self.index.read(
                must=[*base, {"has_id": seed_ids}, *temporal, *current], budget=budget
            )
            seeds = [canonical(p) for p in seed_points]
            if {p["id"] for p in seeds} != set(seed_ids) or any(not eligible(p) for p in seeds):
                raise ConfigurationError("relation seed unavailable")
            refs = [EntityRef.from_payload(p) for p in seeds]
            if len({r.scope for r in refs}) != 1:
                raise ConfigurationError("relation seeds must share one partition")
            scope = refs[0].scope
            partition = _partition_conditions(scope, include_session=True)
            proof_partition = _partition_conditions(
                scope, include_session=scope.session_id is not None
            )
            for payload in seeds:
                verify_projection(payload)
            frontier = [
                {"node_keys": [ref.key], "record_ids": [p["id"]], "steps": []}
                for ref, p in zip(refs, seeds, strict=True)
            ]
            nodes.update(ref.key for ref in refs)
            for level in range(policy.depth):
                keys = sorted({path["node_keys"][-1] for path in frontier})
                if not keys:
                    break
                owners = self.index.read(
                    must=[
                        *base,
                        *partition,
                        *temporal,
                        *current,
                        {
                            "should": [
                                {"key": INDEX_PREFIX + ".owner_key", "match": {"any": keys}},
                                {"key": INDEX_PREFIX + ".target_keys", "match": {"any": keys}},
                            ]
                        },
                    ],
                    budget=budget,
                )
                claims = []
                head_keys = set(keys)
                proof_ids = {"knowledge": set(), "episode": set()}
                for point in owners:
                    payload = canonical(point)
                    verify_projection(payload)
                    if not eligible(payload):
                        continue
                    for edge in bundle_from_extensions(payload["extensions"]).edges:
                        if (
                            edge.status != RelationStatus.ACCEPTED
                            or edge.kind not in policy.kinds
                            or edge.valid_from > at
                            or (edge.valid_until is not None and at >= edge.valid_until)
                        ):
                            continue
                        outgoing = edge.source.key in keys and policy.direction in ("out", "both")
                        incoming = edge.target.key in keys and policy.direction in ("in", "both")
                        symmetric = edge.kind == RelationKind.CONTRADICTS and (
                            edge.source.key in keys or edge.target.key in keys
                        )
                        if not (outgoing or incoming or symmetric):
                            continue
                        claims.append((payload, edge))
                        head_keys.update((edge.source.key, edge.target.key))
                        for proof in edge.evidence:
                            proof_ids[proof.record_type].add(str(proof.id))
                selectors = [
                    {"key": INDEX_PREFIX + ".owner_key", "match": {"any": sorted(head_keys)}}
                ]
                if proof_ids["knowledge"]:
                    selectors.append({"has_id": sorted(proof_ids["knowledge"])})
                records = self.index.read(
                    must=[*base, *proof_partition, *temporal, {"should": selectors}],
                    budget=budget,
                )
                # Evidence can be a superseded canonical version. Heads and evidence
                # remain distinct, and anchors never silently follow successor links.
                knowledge = {str(p["id"]): canonical(p) for p in records}
                heads = head_map(
                    [
                        p
                        for p in records
                        if (
                            p["payload"]
                            .get("extensions", {})
                            .get("_relation_index", {})
                            .get("owner_key")
                            in head_keys
                        )
                    ]
                )
                episodes = {}
                if proof_ids["episode"]:
                    points = self.index.read(
                        must=[
                            *proof_partition,
                            {"key": "record_type", "match": {"value": "episode"}},
                            {"has_id": sorted(proof_ids["episode"])},
                        ],
                        budget=budget,
                        episode=True,
                    )
                    episodes = {str(p["id"]): canonical(p, "episode") for p in points}
                adjacency = {}
                for owner, edge in claims:
                    source = heads.get(edge.source.key)
                    target = heads.get(edge.target.key)
                    if (
                        source is None
                        or target is None
                        or source["id"] != owner["id"]
                        or target["id"] != str(edge.target_record_id)
                        or not eligible(source)
                        or not eligible(target)
                    ):
                        continue
                    valid = True
                    for proof in edge.evidence:
                        payload = (knowledge if proof.record_type == "knowledge" else episodes).get(
                            str(proof.id)
                        )
                        if payload is None or not eligible(payload):
                            valid = False
                            break
                        if proof.record_type == "episode" and _time(payload["event_time"]) > at:
                            valid = False
                            break
                        actual = {k: payload.get(k) for k in scope.model_dump()}
                        if any(
                            actual[k] != v
                            for k, v in scope.model_dump().items()
                            if k != "session_id" or v is not None
                        ):
                            valid = False
                            break
                    if not valid:
                        continue
                    transitions = []
                    if policy.direction in ("out", "both") or edge.kind == RelationKind.CONTRADICTS:
                        transitions.append((edge.source.key, edge.target.key, target, "out"))
                    if policy.direction in ("in", "both") or edge.kind == RelationKind.CONTRADICTS:
                        transitions.append((edge.target.key, edge.source.key, source, "in"))
                    for start, end, endpoint, direction in transitions:
                        adjacency.setdefault(start, []).append(
                            (
                                end,
                                endpoint,
                                {
                                    "relation_id": edge.relation_id,
                                    "kind": edge.kind.value,
                                    "direction": direction,
                                    "owner_record_id": owner["id"],
                                    "owner_version": owner["version"],
                                    "target_record_id": str(edge.target_record_id),
                                    "evidence": [
                                        ref.model_dump(mode="json") for ref in edge.evidence
                                    ],
                                    "valid_from": edge.valid_from.isoformat(),
                                    "valid_until": edge.valid_until.isoformat()
                                    if edge.valid_until
                                    else None,
                                },
                            )
                        )
                next_frontier = []
                for path in frontier:
                    head = heads.get(path["node_keys"][-1])
                    if head is None or head["id"] != path["record_ids"][-1] or not eligible(head):
                        continue
                    for end, endpoint, step in sorted(
                        adjacency.get(path["node_keys"][-1], []),
                        key=lambda value: (value[0], value[2]["relation_id"]),
                    ):
                        if end in path["node_keys"]:
                            continue
                        if end not in nodes and len(nodes) >= policy.max_nodes:
                            reasons.add("nodes")
                            continue
                        if (
                            step["relation_id"] not in edge_ids
                            and len(edge_ids) >= policy.max_edges
                        ):
                            reasons.add("edges")
                            continue
                        if len(paths) >= policy.max_paths:
                            reasons.add("paths")
                            continue
                        extended = {
                            "node_keys": [*path["node_keys"], end],
                            "record_ids": [*path["record_ids"], endpoint["id"]],
                            "steps": [*path["steps"], step],
                        }
                        nodes.add(end)
                        edge_ids.add(step["relation_id"])
                        paths.append(extended)
                        next_frontier.append(extended)
                frontier = next_frontier
                if level + 1 == policy.depth and frontier:
                    reasons.add("depth")
        except TraversalLimit as exc:
            reasons.add(str(exc))
        return {
            "paths": paths,
            "node_count": len(nodes),
            "edge_count": len(edge_ids),
            "storage_calls": budget.used,
            "truncated": bool(reasons),
            "truncation_reasons": sorted(reasons),
            "evaluated_at": at.isoformat(),
            "mode": "historical" if policy.as_of else "current",
            "snapshot_consistent": False,
        }
