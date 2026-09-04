# SPDX-License-Identifier: MPL-2.0

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from cyberbrain.core.errors import ConfigurationError


class ReasonerProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REASONER_", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8770
    auth_token: str | None = Field(default=None, repr=False)
    require_auth: bool = True

    backend: str = "ollama"
    ollama_url: str | None = None
    ollama_model: str | None = None
    ollama_timeout_seconds: float = 120.0
    ollama_num_predict: int = 700

    def validate_runtime(self) -> None:
        if self.require_auth and not (self.auth_token or "").strip():
            raise ConfigurationError("REASONER_AUTH_TOKEN is required when auth is enabled")
        if self.port < 1 or self.port > 65535:
            raise ConfigurationError("reasoner port must be between 1 and 65535")
        if self.backend not in {"ollama", "deterministic"}:
            raise ConfigurationError(f"unsupported Reasoner backend: {self.backend}")
        if self.backend == "ollama":
            if not (self.ollama_url or "").strip():
                raise ConfigurationError("REASONER_OLLAMA_URL is required for Ollama backend")
            if not (self.ollama_model or "").strip():
                raise ConfigurationError("REASONER_OLLAMA_MODEL is required for Ollama backend")
            if self.ollama_timeout_seconds <= 0:
                raise ConfigurationError("ollama_timeout_seconds must be > 0")
            if self.ollama_num_predict < 64:
                raise ConfigurationError("ollama_num_predict must be >= 64")
