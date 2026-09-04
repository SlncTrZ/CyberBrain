# SPDX-License-Identifier: MPL-2.0

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from cyberbrain.core.errors import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CYBERBRAIN_", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8767

    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    knowledge_collection: str = "cyberbrain_knowledge"
    episodic_collection: str = "cyberbrain_episodic"

    embedding_url: str = "http://embedding:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dimension: int = 768
    embedding_version: str = "nomic-embed-text@v1"
    knowledge_search_score_threshold: float | None = 0.55
    memory_search_score_threshold: float | None = 0.55
    knowledge_evolution_lock_file: str | None = None

    mcp_auth_token: str | None = Field(default=None, repr=False)
    require_auth: bool = True

    dream_queue_db: str = "/data/dream_queue.sqlite"
    dream_audit_db: str = "/data/dream_audit.sqlite"
    dream_worker_poll_seconds: float = 2.0
    dream_worker_max_attempts: int = 3
    dream_reasoner_url: str | None = None
    dream_reasoner_tool: str = "reason_task"
    dream_reasoner_bearer_token: str | None = Field(default=None, repr=False)
    dream_reasoner_api_key: str | None = Field(default=None, repr=False)
    dream_reasoner_timeout_seconds: float = 60.0
    dream_association_depth: int = 2
    dream_association_per_query_limit: int = 3
    dream_association_total_limit: int = 12
    dream_per_bucket_limit: int = 5

    def validate_runtime(self) -> None:
        if self.require_auth and not (self.mcp_auth_token or "").strip():
            raise ConfigurationError("CYBERBRAIN_MCP_AUTH_TOKEN is required when auth is enabled")
        if self.embedding_dimension <= 0:
            raise ConfigurationError("embedding_dimension must be > 0")
        for name, value in (
            ("knowledge_search_score_threshold", self.knowledge_search_score_threshold),
            ("memory_search_score_threshold", self.memory_search_score_threshold),
        ):
            if value is not None and not 0 <= value <= 1:
                raise ConfigurationError(f"{name} must be between 0 and 1 or null")
        if self.dream_worker_poll_seconds <= 0:
            raise ConfigurationError("dream_worker_poll_seconds must be > 0")
        if self.dream_worker_max_attempts < 1:
            raise ConfigurationError("dream_worker_max_attempts must be >= 1")
        if self.dream_reasoner_timeout_seconds <= 0:
            raise ConfigurationError("dream_reasoner_timeout_seconds must be > 0")
        if not 0 <= self.dream_association_depth <= 2:
            raise ConfigurationError("dream_association_depth must be between 0 and 2")
        if self.dream_association_per_query_limit < 1:
            raise ConfigurationError("dream_association_per_query_limit must be >= 1")
        if self.dream_association_total_limit < 1:
            raise ConfigurationError("dream_association_total_limit must be >= 1")
        if self.dream_per_bucket_limit < 1:
            raise ConfigurationError("dream_per_bucket_limit must be >= 1")

    def validate_dream_worker(self) -> None:
        self.validate_runtime()
        if not (self.dream_reasoner_url or "").strip():
            raise ConfigurationError("CYBERBRAIN_DREAM_REASONER_URL is required for dream worker")
        if not self.dream_reasoner_tool.strip():
            raise ConfigurationError("dream_reasoner_tool must not be empty")
