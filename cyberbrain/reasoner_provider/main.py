# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import uvicorn

from cyberbrain.reasoner_provider.backends.deterministic import DeterministicMicroReasoningBackend
from cyberbrain.reasoner_provider.backends.ollama import OllamaMicroReasoningBackend
from cyberbrain.reasoner_provider.http import create_reasoner_app
from cyberbrain.reasoner_provider.server import configure_micro_backend
from cyberbrain.reasoner_provider.settings import ReasonerProviderSettings


def main() -> None:
    settings = ReasonerProviderSettings()
    settings.validate_runtime()
    if settings.backend == "deterministic":
        backend = DeterministicMicroReasoningBackend()
    else:
        backend = OllamaMicroReasoningBackend(
            base_url=str(settings.ollama_url),
            model=str(settings.ollama_model),
            timeout_seconds=settings.ollama_timeout_seconds,
            num_predict=settings.ollama_num_predict,
        )
    configure_micro_backend(backend)
    app = create_reasoner_app(
        auth_token=settings.auth_token,
        require_auth=settings.require_auth,
    )
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
