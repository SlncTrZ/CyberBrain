# SPDX-License-Identifier: MPL-2.0

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from cyberbrain.core.errors import ConfigurationError
from cyberbrain.tenancy import DeploymentMode, IdentityScope


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
    retrieval_literal_shadow_enabled: bool = False
    retrieval_literal_shadow_cache_ttl_seconds: float = 300.0
    retrieval_literal_shadow_max_records: int = 5_000
    knowledge_evolution_lock_file: str | None = None

    cognition_m3_m7_enabled: bool = True
    cognition_m6_auto_accept_enabled: bool = True
    cognition_m7_actuation_enabled: bool = True
    cognition_prefetch_multiplier: int = 3
    cognition_concept_evidence_limit: int = 256

    mcp_auth_token: str | None = Field(default=None, repr=False)
    require_auth: bool = True
    deployment_mode: DeploymentMode = DeploymentMode.SINGLE_OWNER
    trusted_agent_id: str | None = None

    dream_queue_db: str = "/data/dream_queue.sqlite"
    dream_audit_db: str = "/data/dream_audit.sqlite"
    dream_reason_task_db: str = "/data/dream_reason_tasks.sqlite"
    dream_mcp_wait_seconds: float = 30.0
    dream_mcp_poll_seconds: float = 0.5
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
    dream_retrieval_score_threshold: float | None = 0.55

    def validate_runtime(self) -> None:
        if self.require_auth and not (self.mcp_auth_token or "").strip():
            raise ConfigurationError("CYBERBRAIN_MCP_AUTH_TOKEN is required when auth is enabled")
        if self.trusted_agent_id is not None:
            if not self.require_auth:
                raise ConfigurationError(
                    "CYBERBRAIN_TRUSTED_AGENT_ID requires authenticated MCP transport"
                )
            try:
                trusted_scope = IdentityScope.from_values(agent=self.trusted_agent_id)
            except (TypeError, ValueError) as exc:
                raise ConfigurationError("CYBERBRAIN_TRUSTED_AGENT_ID is invalid") from exc
            if len(trusted_scope.agent) != 1:
                raise ConfigurationError("CYBERBRAIN_TRUSTED_AGENT_ID must identify one agent")
        if self.deployment_mode is not DeploymentMode.SINGLE_OWNER:
            raise ConfigurationError(
                f"deployment mode {self.deployment_mode.value!r} remains disabled until full "
                "P3 read/write/background isolation and persisted identity requirements are wired"
            )
        if self.embedding_dimension <= 0:
            raise ConfigurationError("embedding_dimension must be > 0")
        for name, value in (
            ("knowledge_search_score_threshold", self.knowledge_search_score_threshold),
            ("memory_search_score_threshold", self.memory_search_score_threshold),
        ):
            if value is not None and not 0 <= value <= 1:
                raise ConfigurationError(f"{name} must be between 0 and 1 or null")
        if self.retrieval_literal_shadow_cache_ttl_seconds <= 0:
            raise ConfigurationError("retrieval_literal_shadow_cache_ttl_seconds must be > 0")
        if self.retrieval_literal_shadow_max_records < 1:
            raise ConfigurationError("retrieval_literal_shadow_max_records must be > 0")
        if self.cognition_prefetch_multiplier < 1 or self.cognition_prefetch_multiplier > 10:
            raise ConfigurationError("cognition_prefetch_multiplier must be between 1 and 10")
        if self.cognition_concept_evidence_limit < 8:
            raise ConfigurationError("cognition_concept_evidence_limit must be >= 8")
        if (
            self.retrieval_literal_shadow_enabled
            and self.deployment_mode is not DeploymentMode.SINGLE_OWNER
        ):
            raise ConfigurationError(
                "retrieval literal shadow is currently supported only in single_owner mode"
            )
        if self.dream_mcp_wait_seconds < 0:
            raise ConfigurationError("dream_mcp_wait_seconds must be >= 0")
        if self.dream_mcp_poll_seconds <= 0:
            raise ConfigurationError("dream_mcp_poll_seconds must be > 0")
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
        if (
            self.dream_retrieval_score_threshold is not None
            and not 0 <= self.dream_retrieval_score_threshold <= 1
        ):
            raise ConfigurationError(
                "dream_retrieval_score_threshold must be between 0 and 1 or null"
            )

    def validate_dream_worker(self) -> None:
        self.validate_runtime()
        if not (self.dream_reasoner_url or "").strip():
            raise ConfigurationError("CYBERBRAIN_DREAM_REASONER_URL is required for dream worker")
        if not self.dream_reasoner_tool.strip():
            raise ConfigurationError("dream_reasoner_tool must not be empty")
