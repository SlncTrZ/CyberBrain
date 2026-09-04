# SPDX-License-Identifier: MPL-2.0

from cyberbrain.dreaming.queue import DreamQueue


def test_recover_processing_requeues_below_attempt_limit(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "queue.sqlite")
    job = queue.enqueue("session-1", ["CyberBrain"])
    queue.mark_processing(job.id)

    recovered = queue.recover_processing(max_attempts=3)

    assert recovered == 1
    current = queue.get_by_session("session-1")
    assert current.status == "pending"
    assert current.attempt_count == 1
    assert current.last_error == "worker_restarted"


def test_recover_processing_marks_failed_at_attempt_limit(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "queue.sqlite")
    job = queue.enqueue("session-1", ["CyberBrain"])
    queue.mark_processing(job.id)
    queue.mark_failed(job.id, "first")
    queue.retry(job.id)
    queue.mark_processing(job.id)

    recovered = queue.recover_processing(max_attempts=2)

    assert recovered == 1
    current = queue.get_by_session("session-1")
    assert current.status == "failed"
    assert current.attempt_count == 2
    assert current.last_error == "worker_restarted"


def test_retry_failed_only_requeues_jobs_below_attempt_limit(tmp_path) -> None:
    queue = DreamQueue(tmp_path / "queue.sqlite")
    first = queue.enqueue("session-1", ["CyberBrain"])
    queue.mark_processing(first.id)
    queue.mark_failed(first.id, "temporary")

    second = queue.enqueue("session-2", ["CyberBrain"])
    queue.mark_processing(second.id)
    queue.mark_failed(second.id, "first")
    queue.retry(second.id)
    queue.mark_processing(second.id)
    queue.mark_failed(second.id, "second")

    retried = queue.retry_failed(max_attempts=2)

    assert retried == 1
    assert queue.get_by_session("session-1").status == "pending"
    assert queue.get_by_session("session-2").status == "failed"
