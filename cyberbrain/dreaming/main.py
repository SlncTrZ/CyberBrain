# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import signal
import time

from cyberbrain.core.settings import Settings
from cyberbrain.dreaming.runtime import build_dream_worker_runtime

_STOP = False


def _request_stop(signum: int, frame) -> None:  # noqa: ANN001
    del signum, frame
    global _STOP
    _STOP = True


def run_worker(settings: Settings) -> None:
    runtime = build_dream_worker_runtime(settings)
    runtime.queue.recover_processing(max_attempts=settings.dream_worker_max_attempts)

    while not _STOP:
        result = runtime.worker.process_next()
        if result is not None:
            continue

        retried = runtime.queue.retry_failed(
            max_attempts=settings.dream_worker_max_attempts,
            limit=1,
        )
        if retried:
            continue
        time.sleep(settings.dream_worker_poll_seconds)


def main() -> None:
    settings = Settings()
    settings.validate_dream_worker()
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    run_worker(settings)


if __name__ == "__main__":
    main()
