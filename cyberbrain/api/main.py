# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import uvicorn

from cyberbrain.api.http import create_app
from cyberbrain.core.runtime import build_runtime
from cyberbrain.core.settings import Settings
from cyberbrain.dreaming.reason_task_inbox import DreamReasonTaskInbox
from cyberbrain.dreaming.runtime import build_dream_operations
from cyberbrain.mcp.server import (
    configure_dream_operations,
    configure_reason_task_inbox,
    configure_runtime,
)


def main() -> None:
    settings = Settings()
    settings.validate_runtime()
    runtime = build_runtime(settings)
    configure_runtime(runtime)
    configure_dream_operations(build_dream_operations(settings, services=runtime))
    configure_reason_task_inbox(DreamReasonTaskInbox(settings.dream_reason_task_db))

    def readiness_probe() -> None:
        runtime.repository.scroll(settings.knowledge_collection, limit=1)
        runtime.repository.scroll(settings.episodic_collection, limit=1)
        runtime.embedding.embed("cyberbrain readiness probe")

    app = create_app(
        settings,
        metrics=runtime.metrics,
        readiness_probe=readiness_probe,
    )
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
