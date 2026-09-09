# SPDX-License-Identifier: MPL-2.0

import pytest

from cyberbrain.core.errors import ConfigurationError
from cyberbrain.core.settings import Settings
from cyberbrain.tenancy import DeploymentMode


def test_require_auth_needs_token() -> None:
    settings = Settings(mcp_auth_token=None, require_auth=True)
    with pytest.raises(ConfigurationError):
        settings.validate_runtime()


def test_auth_can_be_explicitly_disabled_for_local_test_mode() -> None:
    settings = Settings(mcp_auth_token=None, require_auth=False)
    settings.validate_runtime()


@pytest.mark.parametrize(
    "mode",
    [DeploymentMode.AGENT_READY, DeploymentMode.MULTI_USER],
)
def test_non_single_owner_mode_remains_disabled_until_full_p3_integration(
    mode: DeploymentMode,
) -> None:
    settings = Settings(
        mcp_auth_token="secret",
        require_auth=True,
        deployment_mode=mode,
    )
    with pytest.raises(ConfigurationError, match="full P3 read/write/background isolation"):
        settings.validate_runtime()


def test_trusted_agent_identity_requires_authenticated_transport() -> None:
    with pytest.raises(ConfigurationError, match="requires authenticated MCP transport"):
        Settings(
            mcp_auth_token=None,
            require_auth=False,
            trusted_agent_id="agent-a",
        ).validate_runtime()


def test_trusted_agent_identity_rejects_wildcard_like_value() -> None:
    with pytest.raises(ConfigurationError, match="TRUSTED_AGENT_ID is invalid"):
        Settings(
            mcp_auth_token="secret",
            require_auth=True,
            trusted_agent_id="agent-*",
        ).validate_runtime()


def test_single_owner_can_configure_trusted_agent_identity_without_enabling_agent_ready() -> None:
    Settings(
        mcp_auth_token="secret",
        require_auth=True,
        trusted_agent_id="agent-a",
    ).validate_runtime()


def test_literal_shadow_bounds_must_be_positive() -> None:
    with pytest.raises(ConfigurationError, match="cache_ttl_seconds"):
        Settings(
            mcp_auth_token=None,
            require_auth=False,
            retrieval_literal_shadow_cache_ttl_seconds=0,
        ).validate_runtime()

    with pytest.raises(ConfigurationError, match="max_records"):
        Settings(
            mcp_auth_token=None,
            require_auth=False,
            retrieval_literal_shadow_max_records=0,
        ).validate_runtime()


def test_dream_mcp_wait_can_be_zero_but_not_negative() -> None:
    Settings(
        mcp_auth_token=None,
        require_auth=False,
        dream_mcp_wait_seconds=0,
    ).validate_runtime()

    with pytest.raises(ConfigurationError, match="dream_mcp_wait_seconds"):
        Settings(
            mcp_auth_token=None,
            require_auth=False,
            dream_mcp_wait_seconds=-1,
        ).validate_runtime()


def test_dream_mcp_poll_must_be_positive() -> None:
    with pytest.raises(ConfigurationError, match="dream_mcp_poll_seconds"):
        Settings(
            mcp_auth_token=None,
            require_auth=False,
            dream_mcp_poll_seconds=0,
        ).validate_runtime()


def test_active_cognition_bounds_are_validated() -> None:
    Settings(
        mcp_auth_token=None,
        require_auth=False,
        cognition_prefetch_multiplier=3,
        cognition_concept_evidence_limit=256,
    ).validate_runtime()

    with pytest.raises(ConfigurationError, match="prefetch_multiplier"):
        Settings(
            mcp_auth_token=None,
            require_auth=False,
            cognition_prefetch_multiplier=0,
        ).validate_runtime()
    with pytest.raises(ConfigurationError, match="concept_evidence_limit"):
        Settings(
            mcp_auth_token=None,
            require_auth=False,
            cognition_concept_evidence_limit=7,
        ).validate_runtime()
