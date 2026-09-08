# SPDX-License-Identifier: MPL-2.0
"""Transient M5 Working Memory state service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import RLock

from cyberbrain.core.metrics import MetricsRegistry

from .models import (
    WorkingMemoryCandidate,
    WorkingMemoryCloseout,
    WorkingMemoryEmission,
    WorkingMemoryEmissionLedger,
    WorkingMemoryIdentity,
    WorkingMemorySnapshot,
)
from .policy import WorkingMemoryPolicy, WorkingMemorySelector


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("working memory timestamps must be timezone-aware")
    return value.astimezone(UTC)


class WorkingMemoryService:
    """CyberBrain-owned transient active context; no durable persistence."""

    def __init__(
        self,
        policy: WorkingMemoryPolicy | None = None,
        *,
        selector: WorkingMemorySelector | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.policy = policy or (selector.policy if selector is not None else WorkingMemoryPolicy())
        self.selector = selector or WorkingMemorySelector(self.policy)
        self.metrics = metrics or MetricsRegistry()
        self._lock = RLock()
        self._snapshots: dict[tuple[str, str, str], WorkingMemorySnapshot] = {}

    def activate(
        self,
        identity: WorkingMemoryIdentity,
        candidates: list[WorkingMemoryCandidate] | tuple[WorkingMemoryCandidate, ...],
        *,
        now: datetime,
    ) -> WorkingMemorySnapshot:
        instant = _utc(now)
        items, report = self.selector.select(identity, candidates)
        with self._lock:
            previous = self._active_snapshot_unlocked(identity, instant)
            revision = 1 if previous is None else previous.revision + 1
            created_at = instant if previous is None else previous.created_at
            snapshot = WorkingMemorySnapshot(
                identity=identity,
                revision=revision,
                items=items,
                estimated_tokens=sum(item.estimated_tokens for item in items),
                created_at=created_at,
                updated_at=instant,
                expires_at=instant + timedelta(seconds=self.policy.ttl_seconds),
                selection=report,
            )
            self._snapshots[identity.key] = snapshot
        self.metrics.increment("working_memory_activations_total")
        self.metrics.increment("working_memory_selected_items_total", len(items))
        self.metrics.observe("working_memory_selected_tokens", snapshot.estimated_tokens)
        return snapshot

    def get(
        self,
        identity: WorkingMemoryIdentity,
        *,
        now: datetime,
    ) -> WorkingMemorySnapshot | None:
        instant = _utc(now)
        with self._lock:
            snapshot = self._active_snapshot_unlocked(identity, instant)
        self.metrics.increment("working_memory_reads_total")
        if snapshot is None:
            self.metrics.increment("working_memory_misses_total")
        return snapshot

    def emit(
        self,
        identity: WorkingMemoryIdentity,
        *,
        ledger: WorkingMemoryEmissionLedger,
        now: datetime,
    ) -> WorkingMemoryEmission:
        if ledger.identity != identity:
            raise ValueError("working memory emission ledger identity mismatch")
        snapshot = self.get(identity, now=now)
        if snapshot is None:
            return WorkingMemoryEmission(identity, 0, (), 0, 0)

        items = []
        repeated = 0
        for item in snapshot.items:
            previous = ledger.emitted_fingerprints.get(item.candidate_id)
            if previous == item.content_fingerprint:
                repeated += 1
                continue
            items.append(item)
            ledger.emitted_fingerprints[item.candidate_id] = item.content_fingerprint
            ledger.emitted_tokens += item.estimated_tokens
        tokens = sum(item.estimated_tokens for item in items)
        self.metrics.increment("working_memory_emissions_total")
        self.metrics.increment("working_memory_repeated_injection_suppressed_total", repeated)
        self.metrics.observe("working_memory_emitted_tokens", tokens)
        return WorkingMemoryEmission(
            identity=identity,
            revision=snapshot.revision,
            items=tuple(items),
            estimated_tokens=tokens,
            repeated_suppressed_count=repeated,
        )

    def close(
        self,
        identity: WorkingMemoryIdentity,
        *,
        now: datetime,
    ) -> WorkingMemoryCloseout:
        instant = _utc(now)
        with self._lock:
            snapshot = self._active_snapshot_unlocked(identity, instant)
            self._snapshots.pop(identity.key, None)
        self.metrics.increment("working_memory_closeouts_total")
        if snapshot is None:
            return WorkingMemoryCloseout(identity, False, None, 0, 0)
        return WorkingMemoryCloseout(
            identity=identity,
            existed=True,
            final_revision=snapshot.revision,
            final_item_count=len(snapshot.items),
            final_estimated_tokens=snapshot.estimated_tokens,
        )

    def purge_expired(self, *, now: datetime) -> int:
        instant = _utc(now)
        with self._lock:
            expired = [
                key for key, snapshot in self._snapshots.items() if snapshot.expires_at <= instant
            ]
            for key in expired:
                self._snapshots.pop(key, None)
        if expired:
            self.metrics.increment("working_memory_expired_total", len(expired))
        return len(expired)

    def _active_snapshot_unlocked(
        self,
        identity: WorkingMemoryIdentity,
        now: datetime,
    ) -> WorkingMemorySnapshot | None:
        snapshot = self._snapshots.get(identity.key)
        if snapshot is None:
            return None
        if snapshot.expires_at <= now:
            self._snapshots.pop(identity.key, None)
            self.metrics.increment("working_memory_expired_total")
            return None
        return snapshot
