"""Configuration deployment tests: verifying deploy behavior with profiles.

Unit tests for the config_deploy module covering:
- deploy_configuration function signature
- Profile parameter acceptance
- Target validation
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple
from unittest.mock import patch

import pytest

from lib_shopify_graphql import config_deploy
from lib_shopify_graphql.enums import DeployTarget


class MockDeployResult(NamedTuple):
    """Mock for lib_layered_config.DeployResult."""

    destination: Path


# =============================================================================
# Deploy Configuration Signature Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDeployConfigurationSignature:
    """Tests for deploy_configuration function signature."""

    def test_accepts_targets_parameter(self) -> None:
        """The function accepts a targets parameter."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(targets=[DeployTarget.USER])

            mock_deploy.assert_called_once()

    def test_accepts_force_parameter(self) -> None:
        """The function accepts a force parameter."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(targets=[DeployTarget.USER], force=True)

            call_kwargs = mock_deploy.call_args.kwargs
            assert call_kwargs["force"] is True

    def test_accepts_profile_parameter(self) -> None:
        """The function accepts a profile parameter."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(
                targets=[DeployTarget.USER],
                profile="production",
            )

            call_kwargs = mock_deploy.call_args.kwargs
            assert call_kwargs["profile"] == "production"


# =============================================================================
# Deploy Configuration Profile Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDeployConfigurationProfile:
    """Tests for deploy_configuration with profile parameter."""

    def test_profile_is_passed_to_deploy_config(self) -> None:
        """When profile is specified, it is passed to lib_layered_config."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(
                targets=[DeployTarget.USER],
                profile="staging",
            )

            call_kwargs = mock_deploy.call_args.kwargs
            assert call_kwargs["profile"] == "staging"

    def test_none_profile_is_passed_when_not_specified(self) -> None:
        """When profile is not specified, None is passed."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(targets=[DeployTarget.USER])

            call_kwargs = mock_deploy.call_args.kwargs
            assert call_kwargs["profile"] is None

    def test_profile_with_hyphen_is_accepted(self) -> None:
        """Profile names with hyphens are passed correctly."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(
                targets=[DeployTarget.USER],
                profile="staging-v2",
            )

            call_kwargs = mock_deploy.call_args.kwargs
            assert call_kwargs["profile"] == "staging-v2"

    def test_profile_with_underscore_is_accepted(self) -> None:
        """Profile names with underscores are passed correctly."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(
                targets=[DeployTarget.USER],
                profile="my_test_profile",
            )

            call_kwargs = mock_deploy.call_args.kwargs
            assert call_kwargs["profile"] == "my_test_profile"


# =============================================================================
# Deploy Configuration Target Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDeployConfigurationTargets:
    """Tests for deploy_configuration target handling."""

    def test_user_target_is_converted_to_string(self) -> None:
        """DeployTarget.USER is converted to 'user' string."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(targets=[DeployTarget.USER])

            call_kwargs = mock_deploy.call_args.kwargs
            assert "user" in call_kwargs["targets"]

    def test_app_target_is_converted_to_string(self) -> None:
        """DeployTarget.APP is converted to 'app' string."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(targets=[DeployTarget.APP])

            call_kwargs = mock_deploy.call_args.kwargs
            assert "app" in call_kwargs["targets"]

    def test_host_target_is_converted_to_string(self) -> None:
        """DeployTarget.HOST is converted to 'host' string."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(targets=[DeployTarget.HOST])

            call_kwargs = mock_deploy.call_args.kwargs
            assert "host" in call_kwargs["targets"]

    def test_multiple_targets_are_all_converted(self) -> None:
        """Multiple targets are all converted to strings."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            config_deploy.deploy_configuration(
                targets=[DeployTarget.USER, DeployTarget.HOST],
            )

            call_kwargs = mock_deploy.call_args.kwargs
            assert "user" in call_kwargs["targets"]
            assert "host" in call_kwargs["targets"]


# =============================================================================
# Deploy Configuration Return Value Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDeployConfigurationReturnValue:
    """Tests for deploy_configuration return value."""

    def test_returns_list_of_paths(self) -> None:
        """The function returns a list of Path objects."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = [
                MockDeployResult(destination=Path("/tmp/config.toml")),
            ]

            result = config_deploy.deploy_configuration(targets=[DeployTarget.USER])

            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], Path)

    def test_returns_empty_list_when_no_files_created(self) -> None:
        """When no files are created, returns empty list."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = []

            result = config_deploy.deploy_configuration(targets=[DeployTarget.USER])

            assert result == []

    def test_returns_multiple_paths_for_multiple_targets(self) -> None:
        """When deploying to multiple targets, returns multiple paths."""
        with patch.object(config_deploy, "deploy_config") as mock_deploy:
            mock_deploy.return_value = [
                MockDeployResult(destination=Path("/tmp/user/config.toml")),
                MockDeployResult(destination=Path("/tmp/host/config.toml")),
            ]

            result = config_deploy.deploy_configuration(
                targets=[DeployTarget.USER, DeployTarget.HOST],
            )

            assert len(result) == 2
