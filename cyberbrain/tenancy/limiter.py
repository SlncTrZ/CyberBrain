# SPDX-License-Identifier: MPL-2.0
"""Atomic durable quota reservations before foreground or background work."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path

from cyberbrain.core.errors import ConfigurationError
from cyberbrain.tenancy.auth import CallerAuthority
from cyberbrain.tenancy.quota import (
    QuotaDecisionInput,
    QuotaPolicy,
    QuotaResource,
    QuotaScopeKey,
    evaluate_quota,
)


class QuotaExceededError(ConfigurationError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("runtime quota exceeded")
        self.retry_after = retry_after


class SQLiteQuotaLimiter:
    def __init__(self, path: str | Path, policy: QuotaPolicy) -> None:
        self._path = str(path)
        self._policy = policy
        if self._path == ":memory:":
            raise ConfigurationError("runtime quotas require durable SQLite storage")
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS quota_usage (
                    scope_key TEXT NOT NULL, resource TEXT NOT NULL,
                    window_start INTEGER NOT NULL, used INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY(scope_key, resource, window_start)
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def reserve(
        self, authority: CallerAuthority, charges: dict[QuotaResource, int],
        *, now: float | None = None,
    ) -> None:
        stamp = time.time() if now is None else now
        if not math.isfinite(stamp) or stamp < 0:
            raise ValueError("quota time must not be negative")
        scope = authority.grant.scope.as_dict()
        # Policy charges each constrained tenant/user separately, so another agent
        # or session cannot bypass the tenant or user budget.
        keys = [
            QuotaScopeKey((("tenant", tenant),)) for tenant in scope.get("tenant", ())
        ]
        for user in scope.get("user", ()):
            for tenant in scope.get("tenant", ()) or (None,):
                values = (("user", user),) if tenant is None else (
                    ("tenant", tenant), ("user", user),
                )
                keys.append(QuotaScopeKey(values))
        if not keys:
            keys = [
                QuotaScopeKey((("agent", value),)) for value in scope.get("agent", ())
            ] or [QuotaScopeKey((("agent", "__single_owner__"),))]
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM quota_usage WHERE expires_at <= ?", (int(stamp),))
            updates = []
            for key in keys:
                serialized = json.dumps(key.values, separators=(",", ":"))
                for resource, amount in charges.items():
                    limit = self._policy.limit_for(resource)
                    if limit is None:
                        continue
                    start = int(stamp // limit.window_seconds) * limit.window_seconds if (
                        limit.window_seconds is not None
                    ) else 0
                    row = connection.execute(
                        "SELECT used FROM quota_usage "
                        "WHERE scope_key=? AND resource=? AND window_start=?",
                        (serialized, resource.value, start),
                    ).fetchone()
                    used = row[0] if row is not None and limit.window_seconds is not None else 0
                    decision = evaluate_quota(
                        self._policy, QuotaDecisionInput(resource, key, used, amount),
                    )
                    if not decision.allow:
                        retry_after = max(start + (limit.window_seconds or 1) - int(stamp), 1)
                        raise QuotaExceededError(retry_after)
                    if limit.window_seconds is not None:
                        updates.append((serialized, resource.value, start,
                                        used + amount, start + limit.window_seconds))
            connection.executemany("""
                INSERT INTO quota_usage VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scope_key, resource, window_start) DO UPDATE SET
                    used=excluded.used, expires_at=excluded.expires_at
            """, updates)
