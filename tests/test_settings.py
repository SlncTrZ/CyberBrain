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
def test_non_single_owner_mode_requires_trusted_identity_source(mode: DeploymentMode) -> None:
    settings = Settings(
        mcp_auth_token="secret",
        require_auth=True,
        deployment_mode=mode,
    )
    with pytest.raises(ConfigurationError, match="trusted caller identity source"):
        settings.validate_runtime()


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
