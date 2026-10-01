# SPDX-License-Identifier: MPL-2.0
"""Temporal reviewed-relation evidence for Dream; never auto-accept assertions."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from cyberbrain.core.token_budget import DeterministicTokenCounter
from cyberbrain.dreaming.planner import TemporalBucket
from cyberbrain.dreaming.reasoner import EvidenceItem
from cyberbrain.tenancy.enforcement import TenancyOperation
from cyberbrain.tenancy.runtime import enforce_operation

from .recall import RelationRecallRequest, RelationRecallService
from .traversal import TraversalPolicy


class DreamRelationRecall:
    def __init__(
        self,
        service: RelationRecallService,
        *,
        total_limit: int = 12,
        context_tokens: int = 4096,
        max_storage_calls: int = 16,
    ):
        self.service = service
        self.total_limit = total_limit
        self.context_tokens = context_tokens
        self.max_storage_calls = max_storage_calls
        if not 1 <= total_limit <= 32 or not 512 <= context_tokens <= 16384:
            raise ValueError("invalid Dream relation evidence budget")
        if not 1 <= max_storage_calls <= 32:
            raise ValueError("invalid Dream relation read budget")

    def expand(self, *, seed: list[EvidenceItem], bucket: TemporalBucket) -> list[EvidenceItem]:
        enforce_operation(TenancyOperation.BACKGROUND_EVIDENCE_READ)
        groups = {}
        for item in seed:
            if item.record_type != "knowledge":
                continue
            partition = tuple(
                item.metadata.get(key)
                for key in ("tenant", "user", "agent", "project", "session_id")
            )
            groups.setdefault(partition, []).append(item.id)
        seen = {(item.record_type, item.id) for item in seed}
        result = []
        calls_left = self.max_storage_calls
        tokens_left = self.context_tokens
        # No ambient authority widening: the index uses BACKGROUND_EVIDENCE_READ.
        for ids in groups.values():
            if calls_left < 1 or tokens_left < 512 or len(result) >= self.total_limit:
                break
            recalled = self.service.recall(
                RelationRecallRequest(
                    seed_ids=tuple(ids[:32]),
                    policy=TraversalPolicy(
                        as_of=bucket.end, max_nodes=32, max_paths=32, max_storage_calls=calls_left
                    ),
                    context_tokens=tokens_left,
                )
            )
            calls_left -= recalled["storage_calls"]
            tokens_left -= recalled["estimated_tokens"]

            def build(paths, recalled=recalled):
                paths_by_ref = {}
                for path in paths:
                    refs = {("knowledge", record_id) for record_id in path["record_ids"]}
                    refs.update(
                        (proof["record_type"], proof["id"])
                        for step in path["steps"]
                        for proof in step["evidence"]
                    )
                    for ref in refs - seen:
                        paths_by_ref.setdefault(ref, []).append(path)
                items = []
                for (kind, point_id), proof_paths in sorted(paths_by_ref.items()):
                    row = recalled["records"][kind + ":" + point_id]
                    timestamp = row.get("event_time") or row["created_at"]
                    items.append(
                        EvidenceItem(
                            id=point_id,
                            record_type=kind,
                            content=row["text"],
                            score=None,
                            event_time=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
                            metadata={
                                "relation_paths": proof_paths,
                                "relation_as_of": recalled["evaluated_at"],
                                "relation_bucket": bucket.name,
                                "relation_truncated": recalled["truncated"],
                                "relation_truncation_reasons": recalled["truncation_reasons"],
                                **{
                                    key: row[key]
                                    for key in ("topic", "entity_name", "version", "project")
                                    if key in row
                                },
                            },
                        )
                    )
                return items

            selected = []
            packed = []
            for path in recalled["paths"]:
                proposed = build([*selected, path])
                items = [*result, *proposed]
                tokens = DeterministicTokenCounter().estimate_tokens(
                    json.dumps([asdict(item) for item in items], ensure_ascii=False, default=str)
                )
                if len(items) > self.total_limit or tokens > self.context_tokens:
                    continue
                selected.append(path)
                packed = proposed
            result.extend(packed)
            seen.update((item.record_type, item.id) for item in packed)
        return result
