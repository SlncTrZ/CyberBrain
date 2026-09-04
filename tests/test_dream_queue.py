# SPDX-License-Identifier: MPL-2.0

import threading

from cyberbrain.dreaming.queue import DreamQueue


def test_dream_queue_lifecycle(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "dream.sqlite3")
    job = queue.enqueue("session-1", ["CyberBrain", "MeiLin"])

    assert job.status == "pending"
    assert job.topics == ["CyberBrain", "MeiLin"]

    queue.mark_processing(job.id)
    processing = queue.get_by_session("session-1")
    assert processing.status == "processing"
    assert processing.attempt_count == 1

    queue.mark_failed(job.id, "test failure")
    failed = queue.get_by_session("session-1")
    assert failed.status == "failed"
    assert failed.last_error == "test failure"

    queue.retry(job.id)
    assert queue.get_by_session("session-1").status == "pending"

    queue.mark_processing(job.id)
    queue.mark_processed(job.id)
    assert queue.get_by_session("session-1").status == "processed"


def test_enqueue_is_idempotent_per_session(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "dream.sqlite3")
    first = queue.enqueue("session-1", ["CyberBrain"])
    second = queue.enqueue("session-1", ["CyberBrain", "Dreaming"])

    assert first.id == second.id
    assert second.topics == ["CyberBrain", "Dreaming"]


def test_claim_next_is_atomic_across_concurrent_workers(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "dream.sqlite3")
    queue.enqueue("session-1", ["CyberBrain"])
    barrier = threading.Barrier(2)
    claimed = []

    def worker() -> None:
        barrier.wait()
        job = queue.claim_next()
        claimed.append(job.id if job is not None else None)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(item for item in claimed if item is not None) == [1]
    assert claimed.count(None) == 1
    current = queue.get_by_session("session-1")
    assert current.status == "processing"
    assert current.attempt_count == 1


def test_mark_processing_is_conditional_on_pending_status(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "dream.sqlite3")
    job = queue.enqueue("session-1", ["CyberBrain"])

    assert queue.mark_processing(job.id) is True
    assert queue.mark_processing(job.id) is False
    assert queue.get_by_session("session-1").attempt_count == 1
