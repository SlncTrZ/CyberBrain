# SPDX-License-Identifier: MPL-2.0
"""Bounded coordination for immutable prospective prediction retries."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from time import monotonic, sleep
from uuid import UUID

# Fixed stripes bound memory and lock-file growth across service instances.
_LOCKS = tuple(Lock() for _ in range(64))
_TIMEOUT_SECONDS = 30.0


@contextmanager
def prediction_write_guard(prediction_id: UUID, process_lock_file: str | None = None):
    """Serialize a read/create pair; runtime workers share the same state volume."""
    stripe = prediction_id.int % len(_LOCKS)
    deadline = monotonic() + _TIMEOUT_SECONDS
    lock = _LOCKS[stripe]
    if not lock.acquire(timeout=_TIMEOUT_SECONDS):
        raise TimeoutError("prediction write coordination timed out")
    try:
        if process_lock_file is None:
            yield
            return
        try:
            import fcntl
        except ImportError as exc:
            raise RuntimeError("prediction process coordination requires fcntl support") from exc
        path = Path(f"{process_lock_file}.{stripe}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError("prediction write coordination timed out") from None
                    sleep(min(0.01, remaining))
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        lock.release()
