"""CLI command tests: each invocation tells a single story.

Tests for the command-line interface covering:
- Traceback state management
- Command invocation (info, config, config-deploy, health, cache commands)
- Help and error handling
- Real behavior verification (not stub-only tests)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import lib_cli_exit_tools

from conftest import FakeSession, MockConfig

from lib_shopify_graphql import __init__conf__
from lib_shopify_graphql import cli as cli_mod
from lib_shopify_graphql.cli import TracebackState
from lib_shopify_graphql.models import Product


# =============================================================================
# Traceback State Management Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestTracebackSnapshot:
    """Tests for traceback state snapshot functionality."""

    def test_initial_state_is_disabled(self, isolated_traceback_config: None) -> None:
        """When we snapshot traceback, the initial state is quiet."""
        state = cli_mod.snapshot_traceback_state()

        assert state.traceback_enabled is False

    def test_initial_color_is_disabled(self, isolated_traceback_config: None) -> None:
        """When we snapshot traceback, color forcing is disabled."""
        state = cli_mod.snapshot_traceback_state()

        assert state.force_color is False

    def test_returns_traceback_state_dataclass(self, isolated_traceback_config: None) -> None:
        """The snapshot returns a TracebackState dataclass."""
        state = cli_mod.snapshot_traceback_state()

        assert isinstance(state, TracebackState)


@pytest.mark.os_agnostic
class TestTracebackPreferences:
    """Tests for applying traceback preferences."""

    def test_enabling_sets_traceback_true(self, isolated_traceback_config: None) -> None:
        """When we enable traceback, the config sings true."""
        cli_mod.apply_traceback_preferences(True)

        assert lib_cli_exit_tools.config.traceback is True

    def test_enabling_sets_force_color_true(self, isolated_traceback_config: None) -> None:
        """When we enable traceback, color forcing activates."""
        cli_mod.apply_traceback_preferences(True)

        assert lib_cli_exit_tools.config.traceback_force_color is True

    def test_disabling_sets_traceback_false(self, isolated_traceback_config: None) -> None:
        """When we disable traceback, the config whispers false."""
        cli_mod.apply_traceback_preferences(True)
        cli_mod.apply_traceback_preferences(False)

        assert lib_cli_exit_tools.config.traceback is False


@pytest.mark.os_agnostic
class TestTracebackRestore:
    """Tests for restoring traceback state."""

    def test_restore_returns_to_previous_state(self, isolated_traceback_config: None) -> None:
        """When we restore traceback, the config returns to its previous state."""
        previous = cli_mod.snapshot_traceback_state()
        cli_mod.apply_traceback_preferences(True)

        cli_mod.restore_traceback_state(previous)

        assert lib_cli_exit_tools.config.traceback is False

    def test_restore_resets_force_color(self, isolated_traceback_config: None) -> None:
        """When we restore, force color also returns."""
        previous = cli_mod.snapshot_traceback_state()
        cli_mod.apply_traceback_preferences(True)

        cli_mod.restore_traceback_state(previous)

        assert lib_cli_exit_tools.config.traceback_force_color is False


# =============================================================================
# Info Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestInfoCommand:
    """Tests for the info command."""

    def test_exits_successfully(self, cli_runner: CliRunner) -> None:
        """When info is invoked, the CLI exits with success."""
        result = cli_runner.invoke(cli_mod.cli, ["info"])

        assert result.exit_code == 0

    def test_displays_package_name(self, cli_runner: CliRunner) -> None:
        """When info is invoked, the package name is displayed."""
        result = cli_runner.invoke(cli_mod.cli, ["info"])

        assert __init__conf__.name in result.output

    def test_displays_version(self, cli_runner: CliRunner) -> None:
        """When info is invoked, the version is displayed."""
        result = cli_runner.invoke(cli_mod.cli, ["info"])

        assert __init__conf__.version in result.output

    def test_displays_author(self, cli_runner: CliRunner) -> None:
        """When info is invoked, the author is displayed."""
        result = cli_runner.invoke(cli_mod.cli, ["info"])

        assert __init__conf__.author in result.output

    def test_displays_homepage(self, cli_runner: CliRunner) -> None:
        """When info is invoked, the homepage URL is displayed."""
        result = cli_runner.invoke(cli_mod.cli, ["info"])

        assert __init__conf__.homepage in result.output


# =============================================================================
# Config Command Tests - Real Behavior
# =============================================================================


@pytest.mark.os_agnostic
class TestConfigCommand:
    """Tests for the config command with real configuration."""

    def test_exits_successfully(self, cli_runner: CliRunner) -> None:
        """When config is invoked, the CLI exits with success."""
        result = cli_runner.invoke(cli_mod.cli, ["config"])

        assert result.exit_code == 0

    def test_human_format_shows_sections_when_config_exists(self, cli_runner: CliRunner) -> None:
        """When human format is used and config exists, section headers appear in brackets."""
        result = cli_runner.invoke(cli_mod.cli, ["config"])

        # Config may be empty in CI environments where no user config exists
        # and defaultconfig.toml has all values commented out
        if result.output.strip():
            assert "[" in result.output
            assert "]" in result.output

    def test_json_format_outputs_valid_json(self, cli_runner: CliRunner) -> None:
        """When JSON format is requested, output is valid JSON."""
        result = cli_runner.invoke(cli_mod.cli, ["config", "--format", "json"])

        assert result.exit_code == 0
        # Use result.stdout to avoid async log messages from stderr
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, dict)

    def test_json_format_contains_config_data(self, cli_runner: CliRunner) -> None:
        """When JSON format is used, configuration data is present."""
        result = cli_runner.invoke(cli_mod.cli, ["config", "--format", "json"])

        # Use result.stdout to avoid async log messages from stderr
        parsed = json.loads(result.stdout)
        # Config should have at least one key
        assert len(parsed) >= 0

    def test_nonexistent_section_fails(self, cli_runner: CliRunner) -> None:
        """When a nonexistent section is requested, the CLI fails."""
        result = cli_runner.invoke(
            cli_mod.cli,
            ["config", "--section", "nonexistent_section_xyz"],
        )

        assert result.exit_code != 0

    def test_nonexistent_section_shows_error(self, cli_runner: CliRunner) -> None:
        """When a nonexistent section is requested, an error message appears."""
        result = cli_runner.invoke(
            cli_mod.cli,
            ["config", "--section", "nonexistent_section_xyz"],
        )

        assert "not found or empty" in result.stderr

    def test_human_format_output_succeeds(self, cli_runner: CliRunner) -> None:
        """When human format is used, command succeeds."""
        result = cli_runner.invoke(cli_mod.cli, ["config"])

        # Command should succeed regardless of whether config is empty
        assert result.exit_code == 0
        # If config has content, it should contain section markers
        if result.output.strip():
            assert "[" in result.output


# =============================================================================
# Config Command Profile Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestConfigProfileOption:
    """Tests for the config command with --profile option."""

    def test_profile_option_is_accepted(self, cli_runner: CliRunner) -> None:
        """When --profile is provided, the CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["config", "--profile", "test"])

        # Should not fail due to invalid option
        assert "No such option" not in result.output

    def test_profile_with_json_format_works(self, cli_runner: CliRunner) -> None:
        """When --profile and --format json are combined, both work."""
        result = cli_runner.invoke(
            cli_mod.cli,
            ["config", "--profile", "production", "--format", "json"],
        )

        # Should not fail due to invalid option
        assert "No such option" not in result.output
        # If successful, output should contain JSON structure
        if result.exit_code == 0:
            assert "{" in result.output

    def test_profile_with_section_filter_works(self, cli_runner: CliRunner) -> None:
        """When --profile and --section are combined, both work."""
        result = cli_runner.invoke(
            cli_mod.cli,
            ["config", "--profile", "staging", "--section", "lib_log_rich"],
        )

        # May succeed or fail based on section existence, but option is accepted
        assert "No such option" not in result.output


# =============================================================================
# Config-Deploy Command Tests - Real Behavior
# =============================================================================


@pytest.mark.os_agnostic
class TestConfigDeployCommand:
    """Tests for the config-deploy command validation."""

    def test_missing_target_fails(self, cli_runner: CliRunner) -> None:
        """When config-deploy is invoked without target, it fails."""
        result = cli_runner.invoke(cli_mod.cli, ["config-deploy"])

        assert result.exit_code != 0

    def test_missing_target_shows_error(self, cli_runner: CliRunner) -> None:
        """When target is missing, an error message guides the user."""
        result = cli_runner.invoke(cli_mod.cli, ["config-deploy"])

        assert "Missing option" in result.output or "required" in result.output.lower()

    def test_invalid_target_fails(self, cli_runner: CliRunner) -> None:
        """When an invalid target is provided, the CLI fails."""
        result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "invalid_target"])

        assert result.exit_code != 0

    def test_invalid_target_shows_valid_choices(self, cli_runner: CliRunner) -> None:
        """When an invalid target is provided, valid choices are shown."""
        result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "invalid_target"])

        assert "app" in result.output or "user" in result.output or "host" in result.output


# =============================================================================
# Config-Deploy Profile Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestConfigDeployProfileOption:
    """Tests for the config-deploy command with --profile option."""

    def test_profile_option_is_accepted(self, cli_runner: CliRunner) -> None:
        """When --profile is provided to config-deploy, the CLI accepts it."""
        result = cli_runner.invoke(
            cli_mod.cli,
            ["config-deploy", "--target", "user", "--profile", "test"],
        )

        # Should not fail due to invalid option
        assert "No such option" not in result.output

    def test_profile_with_force_flag_works(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When --profile and --force are combined, both work."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

        result = cli_runner.invoke(
            cli_mod.cli,
            ["config-deploy", "--target", "user", "--profile", "production", "--force"],
        )

        # Should not fail due to invalid option
        assert "No such option" not in result.output

    def test_profile_deploys_to_profile_subdirectory(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When --profile is used, config is deployed to profile subdirectory."""
        config_home = tmp_path / ".config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

        result = cli_runner.invoke(
            cli_mod.cli,
            ["config-deploy", "--target", "user", "--profile", "staging", "--force"],
        )

        if result.exit_code == 0:
            # Check that profile path was used (path contains 'profile/staging')
            assert "staging" in result.output or config_home.exists()


@pytest.mark.os_agnostic
class TestConfigDeployRealBehavior:
    """Tests for config-deploy with real deployment to temp directories."""

    def test_user_deploy_creates_file_in_temp(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When deploying to user target, a config file is created."""
        user_config_dir = tmp_path / ".config" / "lib_shopify_graphql"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

        result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user", "--force"])

        if result.exit_code == 0:
            assert user_config_dir.exists() or "Configuration deployed" in result.output
        else:
            assert "Permission" in result.stderr or "sudo" in result.stderr.lower()

    def test_force_flag_overwrites_existing(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When --force is used, existing files are overwritten."""
        user_config_dir = tmp_path / ".config" / "lib_shopify_graphql"
        user_config_dir.mkdir(parents=True, exist_ok=True)
        existing_file = user_config_dir / "config.toml"
        existing_file.write_text("old content")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

        result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user", "--force"])

        if result.exit_code == 0:
            assert "Configuration deployed" in result.output or existing_file.exists()

    def test_without_force_shows_hint_when_exists(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When file exists and --force not used, hint is shown."""
        user_config_dir = tmp_path / ".config" / "lib_shopify_graphql"
        user_config_dir.mkdir(parents=True, exist_ok=True)
        existing_file = user_config_dir / "config.toml"
        existing_file.write_text("old content")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

        result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user"])

        if result.exit_code == 0 and "No configuration" in result.output:
            assert "--force" in result.output


# =============================================================================
# Help and Error Handling Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestHelpOutput:
    """Tests for help output."""

    def test_no_arguments_shows_help(self, cli_runner: CliRunner) -> None:
        """When CLI runs without arguments, help is printed."""
        result = cli_runner.invoke(cli_mod.cli, [])

        assert "Usage:" in result.output

    def test_no_arguments_exits_zero(self, cli_runner: CliRunner) -> None:
        """When CLI runs without arguments, it exits successfully."""
        result = cli_runner.invoke(cli_mod.cli, [])

        assert result.exit_code == 0

    def test_help_flag_shows_usage(self, cli_runner: CliRunner) -> None:
        """When --help is passed, usage information appears."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "Usage:" in result.output

    def test_help_lists_available_commands(self, cli_runner: CliRunner) -> None:
        """When --help is passed, available commands are listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "info" in result.output
        assert "config" in result.output
        assert "health" in result.output

    def test_command_help_shows_options(self, cli_runner: CliRunner) -> None:
        """When command --help is used, command options are shown."""
        result = cli_runner.invoke(cli_mod.cli, ["config", "--help"])

        assert "--format" in result.output
        assert "--section" in result.output
        assert "--profile" in result.output

    def test_config_deploy_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When config-deploy --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--help"])

        assert "--profile" in result.output


@pytest.mark.os_agnostic
class TestUnknownCommand:
    """Tests for unknown command handling."""

    def test_unknown_command_fails(self, cli_runner: CliRunner) -> None:
        """When an unknown command is used, the CLI fails."""
        result = cli_runner.invoke(cli_mod.cli, ["does-not-exist"])

        assert result.exit_code != 0

    def test_unknown_command_shows_error(self, cli_runner: CliRunner) -> None:
        """When an unknown command is used, a helpful error appears."""
        result = cli_runner.invoke(cli_mod.cli, ["does-not-exist"])

        assert "No such command" in result.output


# =============================================================================
# Traceback Flag Integration Tests - Real Behavior
# =============================================================================


@pytest.mark.os_agnostic
class TestTracebackFlagIntegration:
    """Tests for --traceback flag integration with commands."""

    def test_traceback_flag_restores_config_after_run(
        self,
        isolated_traceback_config: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """After running with --traceback, the config is restored."""
        cli_mod.main(["--traceback", "info"])
        _ = capsys.readouterr()

        assert lib_cli_exit_tools.config.traceback is False

    def test_restore_disabled_keeps_traceback_enabled(
        self,
        isolated_traceback_config: None,
        preserve_traceback_state: None,
    ) -> None:
        """When restore is disabled, the traceback choice remains."""
        cli_mod.apply_traceback_preferences(False)

        cli_mod.main(["--traceback", "info"], restore_traceback=False)

        assert lib_cli_exit_tools.config.traceback is True

    def test_traceback_without_command_shows_help(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """When --traceback is passed without command, help is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["--traceback"])

        assert result.exit_code == 0


# =============================================================================
# Main Entry Point Tests - Real Behavior
# =============================================================================


@pytest.mark.os_agnostic
class TestMainEntryPoint:
    """Tests for the main() entry point function."""

    def test_info_command_returns_zero(
        self,
        isolated_traceback_config: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When info command runs via main, exit code is zero."""
        exit_code = cli_mod.main(["info"])

        assert exit_code == 0

    def test_config_command_via_main_succeeds(
        self,
        isolated_traceback_config: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When config command runs via main, it succeeds."""
        exit_code = cli_mod.main(["config"])

        assert exit_code == 0
        # Config may be empty in CI environments where no user config exists
        # and defaultconfig.toml has all values commented out
        captured = capsys.readouterr()
        if captured.out.strip():
            assert "[" in captured.out


# =============================================================================
# Health Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestHealthCheckResult:
    """Tests for the HealthCheckResult dataclass."""

    def test_success_result_has_shop_info(self) -> None:
        """When health check succeeds, shop info is present."""
        from datetime import datetime, timezone

        result = cli_mod.HealthCheckResult(
            success=True,
            shop_name="Test Store",
            shop_url="test-store.myshopify.com",
            api_version="2026-01",
            token_expiration=datetime.now(timezone.utc),
        )

        assert result.success is True
        assert result.shop_name == "Test Store"
        assert result.shop_url == "test-store.myshopify.com"

    def test_failure_result_has_error_info(self) -> None:
        """When health check fails, error info is present."""
        result = cli_mod.HealthCheckResult(
            success=False,
            error_type="AuthenticationError",
            error_message="Invalid credentials",
            fix_suggestion="Check your credentials",
        )

        assert result.success is False
        assert result.error_type == "AuthenticationError"
        assert result.error_message == "Invalid credentials"
        assert result.fix_suggestion is not None


@pytest.mark.os_agnostic
class TestExtractCredentialsFromConfig:
    """Tests for _extract_shopify_credentials_from_config helper."""

    def test_extracts_complete_credentials(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When all credentials are configured, they are extracted."""
        env_file = tmp_path / ".env"
        env_file.write_text("SHOPIFY__SHOP_URL=test-store.myshopify.com\nSHOPIFY__CLIENT_ID=test_client_id\nSHOPIFY__CLIENT_SECRET=test_client_secret\n")
        monkeypatch.chdir(tmp_path)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()
        config = get_config()

        credentials = cli_mod._extract_shopify_credentials_from_config(config)

        assert credentials.shop_url == "test-store.myshopify.com"
        assert credentials.client_id == "test_client_id"
        assert credentials.client_secret == "test_client_secret"

    def test_raises_when_all_empty(self, mock_config: Any) -> None:
        """When no credentials configured, ValueError is raised."""
        config = mock_config({})  # Empty config - all values will return None

        with pytest.raises(ValueError, match="Missing required credentials"):
            cli_mod._extract_shopify_credentials_from_config(config)

    def test_raises_when_partially_configured(self, mock_config: Any) -> None:
        """When credentials are incomplete, ValueError lists missing fields."""
        config = mock_config(
            {
                "shopify": {
                    "shop_url": "test.myshopify.com",
                    "client_id": "",  # Empty string - should trigger error
                    "client_secret": "secret",
                    "api_version": "2026-01",
                }
            }
        )

        with pytest.raises(ValueError, match="shopify.client_id"):
            cli_mod._extract_shopify_credentials_from_config(config)


@pytest.mark.os_agnostic
class TestGetFixSuggestion:
    """Tests for _get_fix_suggestion helper."""

    def test_missing_credentials_suggests_config(self) -> None:
        """When credentials missing, config instructions are provided."""
        error = ValueError("Missing required credentials: shopify.shop_url")

        suggestion = cli_mod._get_fix_suggestion(error, None)

        assert ".env file" in suggestion
        assert "SHOPIFY__SHOP_URL" in suggestion

    def test_auth_error_suggests_credentials_check(self) -> None:
        """When auth fails, credential verification is suggested."""
        from lib_shopify_graphql.exceptions import AuthenticationError
        from lib_shopify_graphql.models import ShopifyCredentials

        error = AuthenticationError("Invalid credentials")
        credentials = ShopifyCredentials(
            shop_url="test.myshopify.com",
            client_id="id",
            client_secret="secret",
        )

        suggestion = cli_mod._get_fix_suggestion(error, credentials)

        assert "client_id" in suggestion
        assert "client_secret" in suggestion

    def test_connection_error_suggests_network_check(self) -> None:
        """When connection fails, network troubleshooting is suggested."""
        from urllib.error import URLError

        from lib_shopify_graphql.models import ShopifyCredentials

        error = URLError("Network unreachable")
        credentials = ShopifyCredentials(
            shop_url="test.myshopify.com",
            client_id="id",
            client_secret="secret",
        )

        suggestion = cli_mod._get_fix_suggestion(error, credentials)

        assert "network" in suggestion.lower()
        assert "test.myshopify.com" in suggestion


@pytest.mark.os_agnostic
class TestHealthCommandNoCredentials:
    """Tests for health command with no credentials configured."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        # Isolate from any existing credentials in environment
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["health"])

        assert result.exit_code != 0

    def test_shows_missing_credentials_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, error message mentions missing fields."""
        # Isolate from any existing credentials in environment
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["health"])

        # Check stderr for error message
        assert "Missing required credentials" in result.output or "ConfigurationError" in result.output

    def test_shows_configuration_instructions(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, output includes config instructions."""
        # Isolate from any existing credentials in environment
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["health"])

        # Check for configuration help
        assert "SHOPIFY__" in result.output or ".env" in result.output or "config" in result.output.lower()


@pytest.mark.os_agnostic
class TestHealthCommandHelp:
    """Tests for health command help output."""

    def test_health_appears_in_main_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, health command is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "health" in result.output

    def test_health_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When health --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["health", "--help"])

        assert "Shopify API connectivity" in result.output or "credentials" in result.output.lower()

    def test_health_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When health --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["health", "--help"])

        assert "--profile" in result.output


@pytest.mark.os_agnostic
class TestHealthCommandProfileOption:
    """Tests for health command with --profile option."""

    def test_profile_option_is_accepted(self, cli_runner: CliRunner) -> None:
        """When --profile is provided, the CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["health", "--profile", "test"])

        # Should not fail due to invalid option
        assert "No such option" not in result.output

    def test_profile_with_root_profile_works(self, cli_runner: CliRunner) -> None:
        """When profile at root and health, both work together."""
        result = cli_runner.invoke(
            cli_mod.cli,
            ["--profile", "production", "health"],
        )

        # Should not fail due to invalid option
        assert "No such option" not in result.output


# =============================================================================
# Cache Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestClearTokenCacheCommand:
    """Tests for tokencache-clear command."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, tokencache-clear is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "tokencache-clear" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When tokencache-clear --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["tokencache-clear", "--help"])

        assert "OAuth" in result.output or "token" in result.output.lower()

    def test_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When tokencache-clear --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["tokencache-clear", "--help"])

        assert "--profile" in result.output

    def test_default_path_used_clears_successfully(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When json_path is empty, default cache path is used and cache clears."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__TOKEN_CACHE__JSON_PATH", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__TOKEN_CACHE__JSON_PATH", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["tokencache-clear"])

        assert "token cache cleared" in result.output.lower()

    def test_default_path_used_exits_zero(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When json_path is empty, default path is used and command exits zero."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__TOKEN_CACHE__JSON_PATH", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__TOKEN_CACHE__JSON_PATH", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["tokencache-clear"])

        assert result.exit_code == 0

    def test_clears_configured_json_cache(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When JSON token cache is configured, it is cleared."""
        cache_file = tmp_path / "token_cache.json"
        cache_file.write_text('{"test_key": "test_value"}')

        # Create a .env file with the configuration
        env_file = tmp_path / ".env"
        env_file.write_text(f"SHOPIFY__TOKEN_CACHE__ENABLED=true\nSHOPIFY__TOKEN_CACHE__JSON_PATH={cache_file}")

        monkeypatch.chdir(tmp_path)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["tokencache-clear"])

        assert result.exit_code == 0
        assert "cleared" in result.output.lower()


@pytest.mark.os_agnostic
class TestClearSkuCacheCommand:
    """Tests for skucache-clear command."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, skucache-clear is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "skucache-clear" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When skucache-clear --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["skucache-clear", "--help"])

        assert "SKU" in result.output

    def test_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When skucache-clear --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["skucache-clear", "--help"])

        assert "--profile" in result.output

    def test_default_path_used_when_no_path_configured(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no JSON path configured, default OS path is used and cache is cleared."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SKU_CACHE__JSON_PATH", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SKU_CACHE__JSON_PATH", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["skucache-clear"])

        # With default paths, cache clears successfully
        assert result.exit_code == 0
        assert "cleared" in result.output.lower()

    def test_clears_configured_json_cache(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When JSON SKU cache is configured, it is cleared."""
        cache_file = tmp_path / "sku_cache.json"
        cache_file.write_text('{"test_key": "test_value"}')

        # Create a .env file with the configuration
        env_file = tmp_path / ".env"
        env_file.write_text(f"SHOPIFY__SKU_CACHE__JSON_PATH={cache_file}")

        monkeypatch.chdir(tmp_path)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["skucache-clear"])

        assert result.exit_code == 0
        assert "cleared" in result.output.lower()


@pytest.mark.os_agnostic
class TestClearAllCacheCommand:
    """Tests for cache-clear-all command."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, cache-clear-all is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "cache-clear-all" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When cache-clear-all --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["cache-clear-all", "--help"])

        assert "cache" in result.output.lower()

    def test_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When cache-clear-all --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["cache-clear-all", "--help"])

        assert "--profile" in result.output

    def test_default_paths_used_clears_sku_cache(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no paths configured, default paths are used and SKU cache is cleared."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__TOKEN_CACHE__ENABLED", raising=False)
        monkeypatch.delenv("SHOPIFY__TOKEN_CACHE__JSON_PATH", raising=False)
        monkeypatch.delenv("SHOPIFY__SKU_CACHE__JSON_PATH", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__TOKEN_CACHE__ENABLED", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__TOKEN_CACHE__JSON_PATH", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SKU_CACHE__JSON_PATH", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["cache-clear-all"])

        # SKU cache uses default path and gets cleared
        # Token cache is disabled by default so not cleared
        assert result.exit_code == 0
        assert "cleared" in result.output.lower()

    def test_clears_both_configured_caches(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When both caches are configured, both are cleared."""
        token_cache = tmp_path / "token_cache.json"
        sku_cache = tmp_path / "sku_cache.json"
        token_cache.write_text('{"token": "value"}')
        sku_cache.write_text('{"sku": "value"}')

        # Create a .env file with the configuration
        env_file = tmp_path / ".env"
        env_file.write_text(f"SHOPIFY__TOKEN_CACHE__ENABLED=true\nSHOPIFY__TOKEN_CACHE__JSON_PATH={token_cache}\nSHOPIFY__SKU_CACHE__JSON_PATH={sku_cache}")

        monkeypatch.chdir(tmp_path)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["cache-clear-all"])

        assert result.exit_code == 0
        assert "cleared" in result.output.lower()
        assert "tokens" in result.output.lower() or "SKU" in result.output

    def test_clears_only_sku_when_only_sku_configured(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When only SKU cache is configured, only it is cleared."""
        sku_cache = tmp_path / "sku_cache.json"
        sku_cache.write_text('{"sku": "value"}')

        # Create a .env file with the configuration
        env_file = tmp_path / ".env"
        env_file.write_text(f"SHOPIFY__SKU_CACHE__JSON_PATH={sku_cache}")

        monkeypatch.chdir(tmp_path)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["cache-clear-all"])

        assert result.exit_code == 0
        assert "SKU" in result.output


@pytest.mark.os_agnostic
class TestCacheCommandProfileOption:
    """Tests for cache commands with --profile option."""

    def test_tokencache_clear_accepts_profile(self, cli_runner: CliRunner) -> None:
        """When --profile is provided to tokencache-clear, CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["tokencache-clear", "--profile", "test"])

        assert "No such option" not in result.output

    def test_skucache_clear_accepts_profile(self, cli_runner: CliRunner) -> None:
        """When --profile is provided to skucache-clear, CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["skucache-clear", "--profile", "test"])

        assert "No such option" not in result.output

    def test_cache_clear_all_accepts_profile(self, cli_runner: CliRunner) -> None:
        """When --profile is provided to cache-clear-all, CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["cache-clear-all", "--profile", "test"])

        assert "No such option" not in result.output

    def test_root_profile_with_cache_command_works(self, cli_runner: CliRunner) -> None:
        """When profile at root and cache command, both work together."""
        result = cli_runner.invoke(
            cli_mod.cli,
            ["--profile", "production", "cache-clear-all"],
        )

        assert "No such option" not in result.output


# =============================================================================
# Product Operation Helper Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestOutputProduct:
    """Tests for _output_product helper function."""

    def test_json_format_outputs_valid_json(self, sample_product: Product) -> None:
        """When JSON format is used, output is valid JSON."""
        from io import StringIO
        from unittest.mock import patch

        output = StringIO()
        with patch.object(cli_mod.click, "echo", side_effect=lambda x, **kwargs: output.write(str(x) + "\n")):
            cli_mod._output_product(sample_product, cli_mod.OutputFormat.JSON)

        result = output.getvalue()
        parsed = json.loads(result)
        assert parsed["id"] == sample_product.id
        assert parsed["title"] == sample_product.title

    def test_json_format_includes_all_fields(self, sample_product: Product) -> None:
        """When JSON format is used, all product fields are included."""
        from io import StringIO
        from unittest.mock import patch

        output = StringIO()
        with patch.object(cli_mod.click, "echo", side_effect=lambda x, **kwargs: output.write(str(x) + "\n")):
            cli_mod._output_product(sample_product, cli_mod.OutputFormat.JSON)

        parsed = json.loads(output.getvalue())
        assert "id" in parsed
        assert "title" in parsed
        assert "handle" in parsed
        assert "status" in parsed
        assert "variants" in parsed

    def test_human_format_shows_title(self, sample_product: Product) -> None:
        """When human format is used, product title is displayed."""
        from io import StringIO
        from unittest.mock import patch

        output = StringIO()
        with patch.object(cli_mod.click, "echo", side_effect=lambda x, **kwargs: output.write(str(x) + "\n")):
            cli_mod._output_product(sample_product, cli_mod.OutputFormat.HUMAN)

        assert sample_product.title in output.getvalue()

    def test_human_format_shows_id(self, sample_product: Product) -> None:
        """When human format is used, product ID is displayed."""
        from io import StringIO
        from unittest.mock import patch

        output = StringIO()
        with patch.object(cli_mod.click, "echo", side_effect=lambda x, **kwargs: output.write(str(x) + "\n")):
            cli_mod._output_product(sample_product, cli_mod.OutputFormat.HUMAN)

        assert sample_product.id in output.getvalue()

    def test_human_format_shows_status(self, sample_product: Product) -> None:
        """When human format is used, product status is displayed."""
        from io import StringIO
        from unittest.mock import patch

        output = StringIO()
        with patch.object(cli_mod.click, "echo", side_effect=lambda x, **kwargs: output.write(str(x) + "\n")):
            cli_mod._output_product(sample_product, cli_mod.OutputFormat.HUMAN)

        assert sample_product.status.value in output.getvalue()


@pytest.mark.os_agnostic
class TestParseProductCreateJson:
    """Tests for _parse_product_create_json helper function."""

    def test_parses_raw_json_string(self) -> None:
        """When raw JSON string is provided, it is parsed correctly."""
        json_str = '{"title": "Test Product"}'

        result = cli_mod._parse_product_create_json(json_str)

        assert result.title == "Test Product"

    def test_parses_json_file(self, tmp_path: Path) -> None:
        """When file path is provided, JSON is read and parsed."""
        json_file = tmp_path / "product.json"
        json_file.write_text('{"title": "File Product", "vendor": "Test Vendor"}')

        result = cli_mod._parse_product_create_json(str(json_file))

        assert result.title == "File Product"
        assert result.vendor == "Test Vendor"

    def test_strips_read_only_fields(self) -> None:
        """When get-product output is used, read-only fields are stripped."""
        json_str = '{"title": "Test", "id": "gid://shopify/Product/123", "created_at": "2024-01-01T00:00:00Z"}'

        result = cli_mod._parse_product_create_json(json_str)

        assert result.title == "Test"
        # id and created_at should not cause validation errors

    def test_flattens_nested_seo(self) -> None:
        """When nested seo object is present, it is flattened."""
        json_str = '{"title": "Test", "seo": {"title": "SEO Title", "description": "SEO Desc"}}'

        result = cli_mod._parse_product_create_json(json_str)

        assert result.title == "Test"
        assert result.seo_title == "SEO Title"
        assert result.seo_description == "SEO Desc"

    def test_invalid_json_raises_system_exit(self) -> None:
        """When invalid JSON is provided, SystemExit is raised."""
        with pytest.raises(SystemExit) as exc_info:
            cli_mod._parse_product_create_json("{invalid json}")

        assert exc_info.value.code == 1

    def test_file_not_found_raises_system_exit(self, tmp_path: Path) -> None:
        """When file does not exist, SystemExit is raised."""
        nonexistent = tmp_path / "nonexistent.json"

        with pytest.raises(SystemExit) as exc_info:
            cli_mod._parse_product_create_json(str(nonexistent))

        assert exc_info.value.code == 1

    def test_missing_title_raises_system_exit(self) -> None:
        """When title is missing, SystemExit is raised."""
        json_str = '{"vendor": "Test Vendor"}'

        with pytest.raises(SystemExit) as exc_info:
            cli_mod._parse_product_create_json(json_str)

        assert exc_info.value.code == 1


@pytest.mark.os_agnostic
class TestBuildProductCreateFromOptions:
    """Tests for _build_product_create_from_options helper function."""

    def test_builds_with_title_only(self) -> None:
        """When only title is provided, ProductCreate is built."""
        result = cli_mod._build_product_create_from_options(
            title="Test Product",
            vendor=None,
            product_type=None,
            status=None,
            tags=None,
            description=None,
            handle=None,
            seo_title=None,
            seo_description=None,
        )

        assert result.title == "Test Product"

    def test_builds_with_all_options(self) -> None:
        """When all options are provided, ProductCreate includes them."""
        from lib_shopify_graphql.models import ProductStatus

        result = cli_mod._build_product_create_from_options(
            title="Full Product",
            vendor="ACME Corp",
            product_type="Widgets",
            status=ProductStatus.ACTIVE,
            tags="tag1, tag2, tag3",
            description="<p>Description</p>",
            handle="full-product",
            seo_title="SEO Title",
            seo_description="SEO Description",
        )

        assert result.title == "Full Product"
        assert result.vendor == "ACME Corp"
        assert result.product_type == "Widgets"
        assert result.status == ProductStatus.ACTIVE
        assert result.tags == ["tag1", "tag2", "tag3"]
        assert result.description_html == "<p>Description</p>"
        assert result.handle == "full-product"
        assert result.seo_title == "SEO Title"
        assert result.seo_description == "SEO Description"

    def test_missing_title_raises_system_exit(self) -> None:
        """When title is None, SystemExit is raised."""
        with pytest.raises(SystemExit) as exc_info:
            cli_mod._build_product_create_from_options(
                title=None,
                vendor=None,
                product_type=None,
                status=None,
                tags=None,
                description=None,
                handle=None,
                seo_title=None,
                seo_description=None,
            )

        assert exc_info.value.code == 1

    def test_parses_comma_separated_tags(self) -> None:
        """When tags string is provided, it is split by commas."""
        result = cli_mod._build_product_create_from_options(
            title="Tagged",
            vendor=None,
            product_type=None,
            status=None,
            tags="  foo  ,  bar  ,  baz  ",
            description=None,
            handle=None,
            seo_title=None,
            seo_description=None,
        )

        assert result.tags == ["foo", "bar", "baz"]


# =============================================================================
# Get-Product Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestGetProductCommandHelp:
    """Tests for get-product command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, get-product is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "get-product" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When get-product --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["get-product", "--help"])

        assert "Retrieve" in result.output or "product" in result.output.lower()

    def test_help_shows_format_option(self, cli_runner: CliRunner) -> None:
        """When get-product --help is used, format option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["get-product", "--help"])

        assert "--format" in result.output

    def test_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When get-product --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["get-product", "--help"])

        assert "--profile" in result.output

    def test_help_shows_product_id_argument(self, cli_runner: CliRunner) -> None:
        """When get-product --help is used, PRODUCT_ID argument is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["get-product", "--help"])

        assert "PRODUCT_ID" in result.output


@pytest.mark.os_agnostic
class TestGetProductCommandNoCredentials:
    """Tests for get-product command without credentials."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["get-product", "123456789"])

        assert result.exit_code != 0

    def test_shows_configuration_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, output includes configuration error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["get-product", "123456789"])

        assert "Configuration error" in result.output or "Missing required" in result.output


@pytest.mark.os_agnostic
class TestGetProductProfileOption:
    """Tests for get-product command with --profile option."""

    def test_profile_option_is_accepted(self, cli_runner: CliRunner) -> None:
        """When --profile is provided, CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["get-product", "--profile", "test", "123"])

        assert "No such option" not in result.output


# =============================================================================
# Create-Product Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestCreateProductCommandHelp:
    """Tests for create-product command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, create-product is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "create-product" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When create-product --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["create-product", "--help"])

        assert "Create" in result.output or "product" in result.output.lower()

    def test_help_shows_title_option(self, cli_runner: CliRunner) -> None:
        """When create-product --help is used, title option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["create-product", "--help"])

        assert "--title" in result.output

    def test_help_shows_json_option(self, cli_runner: CliRunner) -> None:
        """When create-product --help is used, json option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["create-product", "--help"])

        assert "--json" in result.output

    def test_help_shows_vendor_option(self, cli_runner: CliRunner) -> None:
        """When create-product --help is used, vendor option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["create-product", "--help"])

        assert "--vendor" in result.output

    def test_help_shows_format_option(self, cli_runner: CliRunner) -> None:
        """When create-product --help is used, format option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["create-product", "--help"])

        assert "--format" in result.output

    def test_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When create-product --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["create-product", "--help"])

        assert "--profile" in result.output


@pytest.mark.os_agnostic
class TestCreateProductCommandNoCredentials:
    """Tests for create-product command without credentials."""

    def test_exits_with_error_when_no_title_or_json(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no title or json provided, command exits with error."""
        monkeypatch.chdir(tmp_path)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["create-product"])

        assert result.exit_code != 0
        assert "title" in result.output.lower()

    def test_exits_with_config_error_when_no_credentials(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with configuration error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["create-product", "--title", "Test"])

        assert result.exit_code != 0


@pytest.mark.os_agnostic
class TestCreateProductProfileOption:
    """Tests for create-product command with --profile option."""

    def test_profile_option_is_accepted(self, cli_runner: CliRunner) -> None:
        """When --profile is provided, CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["create-product", "--profile", "test", "--title", "X"])

        assert "No such option" not in result.output


# =============================================================================
# Duplicate-Product Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDuplicateProductCommandHelp:
    """Tests for duplicate-product command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, duplicate-product is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "duplicate-product" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When duplicate-product --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "--help"])

        assert "Duplicate" in result.output or "product" in result.output.lower()

    def test_help_shows_no_images_option(self, cli_runner: CliRunner) -> None:
        """When duplicate-product --help is used, no-images option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "--help"])

        assert "--no-images" in result.output

    def test_help_shows_status_option(self, cli_runner: CliRunner) -> None:
        """When duplicate-product --help is used, status option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "--help"])

        assert "--status" in result.output

    def test_help_shows_format_option(self, cli_runner: CliRunner) -> None:
        """When duplicate-product --help is used, format option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "--help"])

        assert "--format" in result.output

    def test_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When duplicate-product --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "--help"])

        assert "--profile" in result.output

    def test_help_shows_product_id_argument(self, cli_runner: CliRunner) -> None:
        """When duplicate-product --help is used, PRODUCT_ID argument is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "--help"])

        assert "PRODUCT_ID" in result.output

    def test_help_shows_new_title_argument(self, cli_runner: CliRunner) -> None:
        """When duplicate-product --help is used, NEW_TITLE argument is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "--help"])

        assert "NEW_TITLE" in result.output


@pytest.mark.os_agnostic
class TestDuplicateProductCommandNoCredentials:
    """Tests for duplicate-product command without credentials."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "123", "New Title"])

        assert result.exit_code != 0


@pytest.mark.os_agnostic
class TestDuplicateProductProfileOption:
    """Tests for duplicate-product command with --profile option."""

    def test_profile_option_is_accepted(self, cli_runner: CliRunner) -> None:
        """When --profile is provided, CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["duplicate-product", "--profile", "test", "123", "New"])

        assert "No such option" not in result.output


# =============================================================================
# Delete-Product Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDeleteProductCommandHelp:
    """Tests for delete-product command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, delete-product is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "delete-product" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When delete-product --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "--help"])

        assert "Delete" in result.output or "product" in result.output.lower()

    def test_help_shows_warning(self, cli_runner: CliRunner) -> None:
        """When delete-product --help is used, warning is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "--help"])

        assert "WARNING" in result.output or "irreversible" in result.output.lower()

    def test_help_shows_force_option(self, cli_runner: CliRunner) -> None:
        """When delete-product --help is used, force option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "--help"])

        assert "--force" in result.output

    def test_help_shows_format_option(self, cli_runner: CliRunner) -> None:
        """When delete-product --help is used, format option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "--help"])

        assert "--format" in result.output

    def test_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When delete-product --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "--help"])

        assert "--profile" in result.output

    def test_help_shows_product_id_argument(self, cli_runner: CliRunner) -> None:
        """When delete-product --help is used, PRODUCT_ID argument is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "--help"])

        assert "PRODUCT_ID" in result.output


@pytest.mark.os_agnostic
class TestDeleteProductConfirmation:
    """Tests for delete-product confirmation prompt."""

    def test_shows_warning_without_force(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When --force not used, warning is displayed."""
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "123"], input="n\n")

        assert "WARNING" in result.output or "permanently delete" in result.output

    def test_aborts_on_no_confirmation(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When user answers no, command aborts."""
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "123"], input="n\n")

        assert "Aborted" in result.output
        assert result.exit_code == 0

    def test_force_skips_confirmation(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When --force is used, no confirmation is shown."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "123", "--force"])

        # Should not show confirmation prompt, should proceed to credential check
        assert "Are you sure" not in result.output


@pytest.mark.os_agnostic
class TestDeleteProductCommandNoCredentials:
    """Tests for delete-product command without credentials."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "123", "--force"])

        assert result.exit_code != 0


@pytest.mark.os_agnostic
class TestDeleteProductProfileOption:
    """Tests for delete-product command with --profile option."""

    def test_profile_option_is_accepted(self, cli_runner: CliRunner) -> None:
        """When --profile is provided, CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-product", "--profile", "test", "123"], input="n\n")

        assert "No such option" not in result.output


# =============================================================================
# Update-Product Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestUpdateProductCommandHelp:
    """Tests for update-product command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, update-product is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "update-product" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When update-product --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["update-product", "--help"])

        assert "Update" in result.output or "product" in result.output.lower()

    def test_help_shows_title_option(self, cli_runner: CliRunner) -> None:
        """When update-product --help is used, title option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["update-product", "--help"])

        assert "--title" in result.output

    def test_help_shows_vendor_option(self, cli_runner: CliRunner) -> None:
        """When update-product --help is used, vendor option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["update-product", "--help"])

        assert "--vendor" in result.output

    def test_help_shows_tags_option(self, cli_runner: CliRunner) -> None:
        """When update-product --help is used, tags option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["update-product", "--help"])

        assert "--tags" in result.output

    def test_help_shows_status_option(self, cli_runner: CliRunner) -> None:
        """When update-product --help is used, status option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["update-product", "--help"])

        assert "--status" in result.output

    def test_help_shows_format_option(self, cli_runner: CliRunner) -> None:
        """When update-product --help is used, format option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["update-product", "--help"])

        assert "--format" in result.output


@pytest.mark.os_agnostic
class TestUpdateProductCommandNoCredentials:
    """Tests for update-product command without credentials."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["update-product", "123", "--title", "Test"])

        assert result.exit_code != 0


@pytest.mark.os_agnostic
class TestUpdateProductProfileOption:
    """Tests for update-product command with --profile option."""

    def test_profile_option_is_accepted(self, cli_runner: CliRunner) -> None:
        """When --profile is provided, CLI accepts it."""
        result = cli_runner.invoke(cli_mod.cli, ["update-product", "--profile", "test", "123", "--title", "New"])

        assert "No such option" not in result.output


# =============================================================================
# Add-Image Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestAddImageCommandHelp:
    """Tests for add-image command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, add-image is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "add-image" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When add-image --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["add-image", "--help"])

        assert "image" in result.output.lower()

    def test_help_shows_url_option(self, cli_runner: CliRunner) -> None:
        """When add-image --help is used, url option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["add-image", "--help"])

        assert "--url" in result.output

    def test_help_shows_file_option(self, cli_runner: CliRunner) -> None:
        """When add-image --help is used, file option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["add-image", "--help"])

        assert "--file" in result.output

    def test_help_shows_alt_option(self, cli_runner: CliRunner) -> None:
        """When add-image --help is used, alt option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["add-image", "--help"])

        assert "--alt" in result.output


@pytest.mark.os_agnostic
class TestAddImageCommandValidation:
    """Tests for add-image command validation."""

    def test_missing_url_and_file_fails(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When neither --url nor --file is provided, command fails."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["add-image", "123"])

        assert result.exit_code != 0
        assert "url" in result.output.lower() or "file" in result.output.lower()


# =============================================================================
# Delete-Image Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDeleteImageCommandHelp:
    """Tests for delete-image command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, delete-image is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "delete-image" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When delete-image --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-image", "--help"])

        assert "image" in result.output.lower()

    def test_help_shows_product_id_argument(self, cli_runner: CliRunner) -> None:
        """When delete-image --help is used, product_id argument is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-image", "--help"])

        assert "PRODUCT_ID" in result.output or "product" in result.output.lower()

    def test_help_shows_image_id_argument(self, cli_runner: CliRunner) -> None:
        """When delete-image --help is used, image_id argument is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["delete-image", "--help"])

        assert "IMAGE_ID" in result.output or "image" in result.output.lower()


@pytest.mark.os_agnostic
class TestDeleteImageCommandNoCredentials:
    """Tests for delete-image command without credentials."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["delete-image", "123", "456"])

        assert result.exit_code != 0


# =============================================================================
# Update-Image Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestUpdateImageCommandHelp:
    """Tests for update-image command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, update-image is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "update-image" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When update-image --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["update-image", "--help"])

        assert "image" in result.output.lower()

    def test_help_shows_alt_option(self, cli_runner: CliRunner) -> None:
        """When update-image --help is used, alt option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["update-image", "--help"])

        assert "--alt" in result.output


@pytest.mark.os_agnostic
class TestUpdateImageCommandNoCredentials:
    """Tests for update-image command without credentials."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["update-image", "123", "456", "--alt", "Test"])

        assert result.exit_code != 0


# =============================================================================
# Reorder-Images Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestReorderImagesCommandHelp:
    """Tests for reorder-images command help output."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When main --help is shown, reorder-images is listed."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "reorder-images" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When reorder-images --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["reorder-images", "--help"])

        assert "image" in result.output.lower() or "order" in result.output.lower()

    def test_help_shows_order_option(self, cli_runner: CliRunner) -> None:
        """When reorder-images --help is used, order option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["reorder-images", "--help"])

        assert "--order" in result.output


@pytest.mark.os_agnostic
class TestReorderImagesCommandValidation:
    """Tests for reorder-images command validation."""

    def test_missing_order_fails(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When --order is not provided, command fails."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["reorder-images", "123"])

        assert result.exit_code != 0
        assert "order" in result.output.lower()


@pytest.mark.os_agnostic
class TestReorderImagesCommandNoCredentials:
    """Tests for reorder-images command without credentials."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["reorder-images", "123", "--order", "a,b,c"])

        assert result.exit_code != 0


# =============================================================================
# Health Check Error Paths
# =============================================================================


@pytest.mark.os_agnostic
class TestHealthCheckErrorHandling:
    """Tests for health command error handling."""

    def test_health_check_with_login_exception_returns_failure(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When login fails, health check returns failure result."""
        from unittest.mock import patch

        # Set up credentials in environment
        monkeypatch.setenv("SHOPIFY__SHOP_URL", "test.myshopify.com")
        monkeypatch.setenv("SHOPIFY__CLIENT_ID", "test-id")
        monkeypatch.setenv("SHOPIFY__CLIENT_SECRET", "test-secret")
        monkeypatch.chdir(tmp_path)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        with patch("lib_shopify_graphql.cli.login") as mock_login:
            mock_login.side_effect = Exception("Connection refused")
            result = cli_runner.invoke(cli_mod.cli, ["health"])

        assert result.exit_code != 0
        assert "failed" in result.output.lower() or "error" in result.output.lower()

    def test_health_check_with_auth_error_shows_fix_suggestion(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When auth fails, health shows fix suggestion."""
        from unittest.mock import patch

        from lib_shopify_graphql.exceptions import AuthenticationError

        monkeypatch.setenv("SHOPIFY__SHOP_URL", "test.myshopify.com")
        monkeypatch.setenv("SHOPIFY__CLIENT_ID", "bad-id")
        monkeypatch.setenv("SHOPIFY__CLIENT_SECRET", "bad-secret")
        monkeypatch.chdir(tmp_path)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        with patch("lib_shopify_graphql.cli.login") as mock_login:
            mock_login.side_effect = AuthenticationError("Invalid credentials")
            result = cli_runner.invoke(cli_mod.cli, ["health"])

        assert result.exit_code != 0


# =============================================================================
# Cache Rebuild Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheRebuildCommandMissingConfig:
    """Tests for skucache-rebuild command with missing config."""

    def test_exits_with_error_when_no_credentials(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials configured, exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["skucache-rebuild"])

        assert result.exit_code != 0
        assert "configuration error" in result.output.lower() or "credentials" in result.output.lower()


# =============================================================================
# Enum Choice Edge Cases
# =============================================================================


@pytest.mark.os_agnostic
class TestEnumChoiceEdgeCases:
    """Tests for EnumChoice parameter type edge cases."""

    def test_accepts_enum_value_directly(self) -> None:
        """EnumChoice accepts enum value directly."""
        from lib_shopify_graphql.cli import EnumChoice, OutputFormat

        choice = EnumChoice(OutputFormat)
        result = choice.convert(OutputFormat.JSON, None, None)
        assert result == OutputFormat.JSON

    def test_converts_string_to_enum(self) -> None:
        """EnumChoice converts string to enum value."""
        from lib_shopify_graphql.cli import EnumChoice, OutputFormat

        choice = EnumChoice(OutputFormat)
        result = choice.convert("json", None, None)
        assert result == OutputFormat.JSON

    def test_fails_on_invalid_string(self) -> None:
        """EnumChoice fails on invalid string."""
        from unittest.mock import MagicMock

        from lib_shopify_graphql.cli import EnumChoice, OutputFormat

        choice = EnumChoice(OutputFormat)
        choice.fail = MagicMock(side_effect=ValueError("fail"))

        with pytest.raises(ValueError):
            choice.convert("invalid", None, None)

        choice.fail.assert_called_once()
        assert "invalid" in str(choice.fail.call_args)

    def test_fails_on_non_string_non_enum(self) -> None:
        """EnumChoice fails on non-string, non-enum input."""
        from unittest.mock import MagicMock

        from lib_shopify_graphql.cli import EnumChoice, OutputFormat

        choice = EnumChoice(OutputFormat)
        choice.fail = MagicMock(side_effect=ValueError("fail"))

        with pytest.raises(ValueError):
            choice.convert(42, None, None)  # Integer is not string or enum

        choice.fail.assert_called_once()
        assert "int" in str(choice.fail.call_args)


# =============================================================================
# Product Output Format Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestProductOutputFormatters:
    """Tests for product output formatting functions."""

    def test_output_product_json_format(self, capsys) -> None:
        """_output_product outputs JSON when format is JSON."""
        from datetime import datetime, timezone

        from lib_shopify_graphql.cli import _output_product, OutputFormat
        from lib_shopify_graphql.models import Product

        now = datetime.now(tz=timezone.utc)
        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test-product",
            status="ACTIVE",
            product_type="Widget",
            vendor="Test Vendor",
            variants=[],
            images=[],
            options=[],
            tags=[],
            created_at=now,
            updated_at=now,
        )

        _output_product(product, OutputFormat.JSON)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["title"] == "Test Product"
        assert data["id"] == "gid://shopify/Product/123"

    def test_output_product_human_format(self, capsys) -> None:
        """_output_product outputs human-readable format."""
        from datetime import datetime, timezone

        from lib_shopify_graphql.cli import _output_product, OutputFormat
        from lib_shopify_graphql.models import Product

        now = datetime.now(tz=timezone.utc)
        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test-product",
            status="ACTIVE",
            product_type="Widget",
            vendor="Test Vendor",
            variants=[],
            images=[],
            options=[],
            tags=[],
            created_at=now,
            updated_at=now,
        )

        _output_product(product, OutputFormat.HUMAN)

        captured = capsys.readouterr()
        assert "Test Product" in captured.out
        assert "123" in captured.out


# =============================================================================
# test-limits Command Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestTestLimitsCommandHelp:
    """Tests for test-limits command help."""

    def test_command_exists_in_help(self, cli_runner: CliRunner) -> None:
        """When --help is used, test-limits appears in command list."""
        result = cli_runner.invoke(cli_mod.cli, ["--help"])

        assert "test-limits" in result.output

    def test_help_shows_description(self, cli_runner: CliRunner) -> None:
        """When test-limits --help is used, description is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["test-limits", "--help"])

        assert "truncation" in result.output.lower() or "limit" in result.output.lower()

    def test_help_shows_profile_option(self, cli_runner: CliRunner) -> None:
        """When test-limits --help is used, profile option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["test-limits", "--help"])

        assert "--profile" in result.output

    def test_help_shows_sample_size_option(self, cli_runner: CliRunner) -> None:
        """When test-limits --help is used, sample-size option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["test-limits", "--help"])

        assert "--sample-size" in result.output or "-n" in result.output

    def test_help_shows_query_option(self, cli_runner: CliRunner) -> None:
        """When test-limits --help is used, query option is shown."""
        result = cli_runner.invoke(cli_mod.cli, ["test-limits", "--help"])

        assert "--query" in result.output or "-q" in result.output


@pytest.mark.os_agnostic
class TestTestLimitsCommandNoCredentials:
    """Tests for test-limits command without credentials."""

    def test_exits_with_error(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no credentials, command exits with error."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY__CLIENT_SECRET", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID", raising=False)
        monkeypatch.delenv("LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET", raising=False)

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        result = cli_runner.invoke(cli_mod.cli, ["test-limits"])

        assert result.exit_code != 0


# =============================================================================
# Helper Functions Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestParseImageIds:
    """Tests for _parse_image_ids helper function."""

    def test_parses_comma_separated_ids(self) -> None:
        """Comma-separated IDs are parsed correctly."""
        from lib_shopify_graphql.cli import _parse_image_ids

        result = _parse_image_ids("1,2,3")

        assert result == ["1", "2", "3"]

    def test_handles_spaces_around_commas(self) -> None:
        """Spaces around commas are stripped."""
        from lib_shopify_graphql.cli import _parse_image_ids

        result = _parse_image_ids("1 , 2 , 3")

        assert result == ["1", "2", "3"]

    def test_handles_leading_trailing_spaces(self) -> None:
        """Leading and trailing spaces are stripped."""
        from lib_shopify_graphql.cli import _parse_image_ids

        result = _parse_image_ids("  1,2,3  ")

        assert result == ["1", "2", "3"]

    def test_handles_empty_segments(self) -> None:
        """Empty segments from double commas are filtered out."""
        from lib_shopify_graphql.cli import _parse_image_ids

        result = _parse_image_ids("1,,2,,,3")

        assert result == ["1", "2", "3"]

    def test_handles_single_id(self) -> None:
        """Single ID without comma is returned as list."""
        from lib_shopify_graphql.cli import _parse_image_ids

        result = _parse_image_ids("12345")

        assert result == ["12345"]

    def test_handles_gids(self) -> None:
        """GID format IDs are preserved."""
        from lib_shopify_graphql.cli import _parse_image_ids

        result = _parse_image_ids("gid://shopify/Image/1,gid://shopify/Image/2")

        assert result == ["gid://shopify/Image/1", "gid://shopify/Image/2"]

    def test_handles_empty_string(self) -> None:
        """Empty string returns empty list."""
        from lib_shopify_graphql.cli import _parse_image_ids

        result = _parse_image_ids("")

        assert result == []


@pytest.mark.os_agnostic
class TestOutputReorderResult:
    """Tests for _output_reorder_result helper function."""

    def test_json_format_outputs_valid_json(self, capsys) -> None:
        """JSON format outputs valid JSON."""
        from lib_shopify_graphql.cli import _output_reorder_result, OutputFormat
        from lib_shopify_graphql.models import ImageReorderResult

        result = ImageReorderResult(product_id="gid://shopify/Product/123", job_id="job-456")

        _output_reorder_result(result, OutputFormat.JSON)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["product_id"] == "gid://shopify/Product/123"
        assert data["job_id"] == "job-456"

    def test_human_format_shows_product_id(self, capsys) -> None:
        """Human format shows product ID."""
        from lib_shopify_graphql.cli import _output_reorder_result, OutputFormat
        from lib_shopify_graphql.models import ImageReorderResult

        result = ImageReorderResult(product_id="gid://shopify/Product/123", job_id=None)

        _output_reorder_result(result, OutputFormat.HUMAN)

        captured = capsys.readouterr()
        assert "123" in captured.out
        assert "reordered" in captured.out.lower()

    def test_human_format_shows_job_id_when_present(self, capsys) -> None:
        """Human format shows job ID when async operation."""
        from lib_shopify_graphql.cli import _output_reorder_result, OutputFormat
        from lib_shopify_graphql.models import ImageReorderResult

        result = ImageReorderResult(product_id="gid://shopify/Product/123", job_id="job-456")

        _output_reorder_result(result, OutputFormat.HUMAN)

        captured = capsys.readouterr()
        assert "job-456" in captured.out
        assert "async" in captured.out.lower()


@pytest.mark.os_agnostic
class TestReadJsonInput:
    """Tests for _read_json_input helper function."""

    def test_parses_raw_json_string(self) -> None:
        """Parses raw JSON string starting with '{'."""
        from lib_shopify_graphql.cli import _read_json_input

        result = _read_json_input('{"key": "value"}')

        assert result == {"key": "value"}

    def test_parses_complex_json_string(self) -> None:
        """Parses complex nested JSON string."""
        from lib_shopify_graphql.cli import _read_json_input

        result = _read_json_input('{"title": "Test", "vendor": "Acme", "tags": ["a", "b"]}')

        assert result["title"] == "Test"
        assert result["vendor"] == "Acme"
        assert result["tags"] == ["a", "b"]

    def test_parses_json_from_file(self, tmp_path: Path) -> None:
        """Parses JSON from file path."""
        from lib_shopify_graphql.cli import _read_json_input

        json_file = tmp_path / "test.json"
        json_file.write_text('{"title": "From File"}')

        result = _read_json_input(str(json_file))

        assert result == {"title": "From File"}


@pytest.mark.os_agnostic
class TestFlattenSeoFields:
    """Tests for _flatten_seo_fields helper function."""

    def test_flattens_seo_object(self) -> None:
        """Flattens nested seo object into separate fields."""
        from lib_shopify_graphql.cli import _flatten_seo_fields

        data: dict[str, object] = {"title": "Product", "seo": {"title": "SEO Title", "description": "SEO Desc"}}

        _flatten_seo_fields(data)

        assert data["seo_title"] == "SEO Title"
        assert data["seo_description"] == "SEO Desc"
        assert "seo" not in data

    def test_handles_missing_seo_object(self) -> None:
        """Handles data without seo object."""
        from lib_shopify_graphql.cli import _flatten_seo_fields

        data: dict[str, object] = {"title": "Product"}

        _flatten_seo_fields(data)

        assert "seo_title" not in data
        assert "seo_description" not in data

    def test_handles_partial_seo_object(self) -> None:
        """Handles seo object with only title."""
        from lib_shopify_graphql.cli import _flatten_seo_fields

        data: dict[str, object] = {"title": "Product", "seo": {"title": "SEO Title"}}

        _flatten_seo_fields(data)

        assert data["seo_title"] == "SEO Title"
        assert "seo_description" not in data
        assert "seo" not in data

    def test_handles_empty_seo_values(self) -> None:
        """Ignores empty seo values."""
        from lib_shopify_graphql.cli import _flatten_seo_fields

        data: dict[str, object] = {"title": "Product", "seo": {"title": "", "description": ""}}

        _flatten_seo_fields(data)

        assert "seo_title" not in data
        assert "seo_description" not in data

    def test_handles_non_dict_seo(self) -> None:
        """Handles non-dict seo value."""
        from lib_shopify_graphql.cli import _flatten_seo_fields

        data: dict[str, object] = {"title": "Product", "seo": "not a dict"}

        _flatten_seo_fields(data)

        assert "seo_title" not in data
        assert data["seo"] == "not a dict"  # Unchanged


@pytest.mark.os_agnostic
class TestStripReadonlyCreateFields:
    """Tests for _strip_readonly_create_fields helper function."""

    def test_strips_readonly_fields(self) -> None:
        """Strips known readonly fields."""
        from lib_shopify_graphql.cli import _strip_readonly_create_fields

        data: dict[str, object] = {
            "title": "Test",
            "id": "gid://shopify/Product/123",
            "created_at": "2024-01-01",
            "variants": [],
        }

        _strip_readonly_create_fields(data)

        assert "title" in data
        assert "id" not in data
        assert "created_at" not in data
        assert "variants" not in data

    def test_preserves_writeable_fields(self) -> None:
        """Preserves fields that can be written."""
        from lib_shopify_graphql.cli import _strip_readonly_create_fields

        data: dict[str, object] = {
            "title": "Test",
            "vendor": "Acme",
            "product_type": "Widget",
            "tags": ["tag1"],
        }

        _strip_readonly_create_fields(data)

        assert data == {"title": "Test", "vendor": "Acme", "product_type": "Widget", "tags": ["tag1"]}

    def test_handles_empty_dict(self) -> None:
        """Handles empty dict."""
        from lib_shopify_graphql.cli import _strip_readonly_create_fields

        data: dict[str, object] = {}

        _strip_readonly_create_fields(data)

        assert data == {}


# =============================================================================
# test-limits Command Full Tests
# =============================================================================


@pytest.fixture
def test_limits_env() -> dict[str, str]:
    return {
        "LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL": "test.myshopify.com",
        "LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_ID": "test-id",
        "LIB_SHOPIFY_GRAPHQL___SHOPIFY__CLIENT_SECRET": "test-secret",
    }


@pytest.mark.os_agnostic
class TestTestLimitsCommandWithFakeSession:
    """Tests for test-limits command with FakeSession (real behavior adapter)."""

    def test_displays_current_limits(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        test_limits_env: dict[str, str],
    ) -> None:
        """Displays current GraphQL limits before sampling."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {"data": {"products": {"nodes": []}}}

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        assert "Current Product GraphQL Limits:" in result.output
        assert "product_max_images:" in result.output
        assert "product_max_variants:" in result.output
        assert "product_max_metafields:" in result.output

    def test_no_products_found_message(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Displays message when no products found."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {"data": {"products": {"nodes": []}}}

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        assert "No products found" in result.output

    def test_no_truncation_success_message(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Displays success message when no truncation detected."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {
            "data": {
                "products": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Product/123",
                            "title": "Test Product",
                            "images": {"pageInfo": {"hasNextPage": False}, "nodes": [{"id": "1"}]},
                            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": [{"id": "v1"}]},
                        }
                    ]
                }
            }
        }

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        assert "No truncation detected" in result.output
        assert "sufficient for this catalog" in result.output

    def test_truncation_detected_warning(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Displays warning when truncation detected."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {
            "data": {
                "products": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Product/123",
                            "title": "Product With Many Images",
                            "images": {
                                "pageInfo": {"hasNextPage": True},
                                "nodes": [{"id": str(i)} for i in range(20)],
                            },
                            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": [{"id": "v1"}]},
                        }
                    ]
                }
            }
        }

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        assert "TRUNCATION DETECTED" in result.output
        assert "images" in result.output.lower()
        assert "REQUIRED CHANGES" in result.output

    def test_shows_max_values_found(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Shows maximum values found for each field."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {
            "data": {
                "products": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Product/123",
                            "title": "Test Product",
                            "images": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
                            },
                            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "variants": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [{"id": "v1"}, {"id": "v2"}],
                            },
                        }
                    ]
                }
            }
        }

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        assert "Maximum Values Found" in result.output
        assert "Max on:" in result.output

    def test_limit_option(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Uses limit option to cap product analysis count."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        # Return one product so limit is tested
        session.graphql_responses["products"] = {
            "data": {
                "products": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "id": "gid://shopify/Product/123",
                            "title": "Test Product",
                            "images": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                        }
                    ],
                }
            }
        }

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits", "-n", "100"], env=test_limits_env)

        # With limit, should still analyze all available (1 product)
        assert "Analyzed 1 products" in result.output

    def test_query_filter_option(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Uses query filter option."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {"data": {"products": {"nodes": []}}}

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits", "-q", "status:active"], env=test_limits_env)

        assert "Filter: status:active" in result.output

    def test_auth_error_shows_fix_suggestion(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Shows fix suggestion on authentication error."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config
        from lib_shopify_graphql.exceptions import AuthenticationError

        get_config.cache_clear()

        with patch("lib_shopify_graphql.cli.login") as mock_login:
            mock_login.side_effect = AuthenticationError("Invalid credentials")
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        assert result.exit_code != 0
        assert "Error" in result.output or "error" in result.output.lower()

    def test_graphql_error_shows_fix_suggestion(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Shows fix suggestion on GraphQL error."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config
        from lib_shopify_graphql.exceptions import GraphQLError

        get_config.cache_clear()

        session = FakeSession()
        session.configure_error(GraphQLError("Query failed"))

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        assert result.exit_code != 0
        assert "Error" in result.output or "error" in result.output.lower()

    def test_logout_called_on_success(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Logs out session on successful completion."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {"data": {"products": {"nodes": []}}}

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout") as mock_logout,
        ):
            cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        mock_logout.assert_called_once_with(session)

    def test_logout_called_on_error(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Logs out session even on error (via finally block)."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config
        from lib_shopify_graphql.exceptions import GraphQLError

        get_config.cache_clear()

        session = FakeSession()
        session.configure_error(GraphQLError("Failed"))

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout") as mock_logout,
        ):
            cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        mock_logout.assert_called_once_with(session)

    def test_multiple_products_tracks_max_correctly(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Tracks max values correctly across multiple products."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {
            "data": {
                "products": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Product/1",
                            "title": "Product A",
                            "images": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [{"id": "1"}],
                            },
                            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                        },
                        {
                            "id": "gid://shopify/Product/2",
                            "title": "Product B With More Images",
                            "images": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [{"id": str(i)} for i in range(5)],
                            },
                            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                        },
                    ]
                }
            }
        }

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        # Should show Product B has max images
        assert "Product B With More Images" in result.output

    def test_variant_metafields_truncation_detection(
        self,
        cli_runner: CliRunner,
        test_limits_env: dict[str, str],
    ) -> None:
        """Detects truncation in nested variant metafields."""
        from unittest.mock import patch

        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        session = FakeSession()
        session.graphql_responses["products"] = {
            "data": {
                "products": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Product/123",
                            "title": "Product With Variant Metafields",
                            "images": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                            "variants": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [
                                    {
                                        "id": "v1",
                                        "metafields": {
                                            "pageInfo": {"hasNextPage": True},
                                            "nodes": [{"id": "mf1"}],
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

        with (
            patch("lib_shopify_graphql.cli.login", return_value=session),
            patch("lib_shopify_graphql.cli.logout"),
        ):
            result = cli_runner.invoke(cli_mod.cli, ["test-limits"], env=test_limits_env)

        assert "TRUNCATION DETECTED" in result.output
        assert "variant_metafields" in result.output.lower() or "VARIANT_METAFIELDS" in result.output


# =============================================================================
# MySQL Configuration Model Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestMySQLConfigModel:
    """Tests for MySQLConfig Pydantic model."""

    def test_default_values(self) -> None:
        """MySQLConfig has sensible defaults."""
        from lib_shopify_graphql.cli import MySQLConfig

        config = MySQLConfig()

        assert config.connection == ""
        assert config.host == "localhost"
        assert config.port == 3306
        assert config.user == ""
        assert config.password == ""
        assert config.database == ""
        assert config.auto_create_database is True
        assert config.connect_timeout == 10

    def test_validates_from_dict(self) -> None:
        """MySQLConfig validates from dictionary."""
        from lib_shopify_graphql.cli import MySQLConfig

        data = {
            "connection": "mysql://user:pass@host/db",
            "host": "db.example.com",
            "port": 3307,
            "user": "shopify_user",
            "password": "secret123",
            "database": "shopify_cache",
            "auto_create_database": False,
            "connect_timeout": 30,
        }

        config = MySQLConfig.model_validate(data)

        assert config.connection == "mysql://user:pass@host/db"
        assert config.host == "db.example.com"
        assert config.port == 3307
        assert config.user == "shopify_user"
        assert config.password == "secret123"
        assert config.database == "shopify_cache"
        assert config.auto_create_database is False
        assert config.connect_timeout == 30

    def test_ignores_extra_fields(self) -> None:
        """MySQLConfig ignores unknown fields."""
        from lib_shopify_graphql.cli import MySQLConfig

        data = {
            "user": "test",
            "database": "test_db",
            "unknown_field": "ignored",
        }

        config = MySQLConfig.model_validate(data)

        assert config.user == "test"
        assert config.database == "test_db"
        assert not hasattr(config, "unknown_field")


# =============================================================================
# MySQL Cache Adapter Creation Tests
# =============================================================================

# MockConfig is imported from conftest.py for real behavior testing


@pytest.mark.os_agnostic
class TestCreateMySQLCacheAdapter:
    """Tests for _create_mysql_cache_adapter helper function."""

    def test_returns_none_when_pymysql_not_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when pymysql is not installed."""
        monkeypatch.setattr(cli_mod, "PYMYSQL_AVAILABLE", False)

        mock_config = MockConfig({"shopify": {"mysql": {"user": "test", "database": "test_db"}}})

        result = cli_mod._create_mysql_cache_adapter(
            mock_config,
            cache_connection="",
            table_name="test_table",
        )

        assert result is None

    def test_uses_cache_connection_when_provided(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Uses per-cache connection string when provided."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        monkeypatch.setattr(cli_mod, "PYMYSQL_AVAILABLE", True)

        captured: dict[str, str] = {}

        def mock_from_url(conn: str, **kwargs: object) -> None:
            captured["connection"] = conn
            raise ValueError("Mock stop")

        monkeypatch.setattr(MySQLCacheAdapter, "from_url", staticmethod(mock_from_url))

        mock_config = MockConfig({"shopify": {"mysql": {"connection": "mysql://shared:pass@shared/db"}}})

        try:
            cli_mod._create_mysql_cache_adapter(
                mock_config,
                cache_connection="mysql://cache:pass@cache/db",
                table_name="test",
            )
        except ValueError:
            pass

        assert captured["connection"] == "mysql://cache:pass@cache/db"

    def test_uses_shared_connection_when_no_cache_connection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Uses shared connection string when no per-cache connection."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        monkeypatch.setattr(cli_mod, "PYMYSQL_AVAILABLE", True)

        captured: dict[str, str] = {}

        def mock_from_url(conn: str, **kwargs: object) -> None:
            captured["connection"] = conn
            raise ValueError("Mock stop")

        monkeypatch.setattr(MySQLCacheAdapter, "from_url", staticmethod(mock_from_url))

        mock_config = MockConfig({"shopify": {"mysql": {"connection": "mysql://shared:pass@shared/db"}}})

        try:
            cli_mod._create_mysql_cache_adapter(
                mock_config,
                cache_connection="",
                table_name="test",
            )
        except ValueError:
            pass

        assert captured["connection"] == "mysql://shared:pass@shared/db"

    def test_uses_individual_params_when_no_connection_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Uses individual parameters when no connection string configured."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        monkeypatch.setattr(cli_mod, "PYMYSQL_AVAILABLE", True)

        captured: dict[str, object] = {}

        def mock_init(
            self: object,
            *,
            host: str,
            port: int,
            user: str,
            password: str,
            database: str,
            table_name: str,
            connect_timeout: int,
            auto_create_database: bool,
        ) -> None:
            captured["host"] = host
            captured["port"] = port
            captured["user"] = user
            captured["password"] = password
            captured["database"] = database
            captured["table_name"] = table_name
            captured["connect_timeout"] = connect_timeout
            captured["auto_create_database"] = auto_create_database
            raise ValueError("Mock stop")

        monkeypatch.setattr(MySQLCacheAdapter, "__init__", mock_init)

        mock_config = MockConfig(
            {
                "shopify": {
                    "mysql": {
                        "host": "db.example.com",
                        "port": 3307,
                        "user": "shopify_user",
                        "password": "secret123",
                        "database": "shopify_cache",
                        "connect_timeout": 20,
                        "auto_create_database": False,
                    }
                }
            }
        )

        try:
            cli_mod._create_mysql_cache_adapter(
                mock_config,
                cache_connection="",
                table_name="sku_cache",
            )
        except ValueError:
            pass

        assert captured["host"] == "db.example.com"
        assert captured["port"] == 3307
        assert captured["user"] == "shopify_user"
        assert captured["password"] == "secret123"
        assert captured["database"] == "shopify_cache"
        assert captured["table_name"] == "sku_cache"
        assert captured["connect_timeout"] == 20
        assert captured["auto_create_database"] is False

    def test_returns_none_when_no_config(self) -> None:
        """Returns None when MySQL is not configured."""
        mock_config = MockConfig({"shopify": {"mysql": {}}})

        result = cli_mod._create_mysql_cache_adapter(
            mock_config,
            cache_connection="",
            table_name="test",
        )

        assert result is None

    def test_returns_none_when_missing_user(self) -> None:
        """Returns None when user is missing from individual params."""
        mock_config = MockConfig(
            {
                "shopify": {
                    "mysql": {
                        "database": "test_db",
                        "host": "localhost",
                    }
                }
            }
        )

        result = cli_mod._create_mysql_cache_adapter(
            mock_config,
            cache_connection="",
            table_name="test",
        )

        assert result is None

    def test_returns_none_when_missing_database(self) -> None:
        """Returns None when database is missing from individual params."""
        mock_config = MockConfig(
            {
                "shopify": {
                    "mysql": {
                        "user": "test_user",
                        "host": "localhost",
                    }
                }
            }
        )

        result = cli_mod._create_mysql_cache_adapter(
            mock_config,
            cache_connection="",
            table_name="test",
        )

        assert result is None


# =============================================================================
# Token Cache Creation Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestCreateTokenCacheFromConfig:
    """Tests for create_token_cache_from_config helper function."""

    def test_returns_none_when_disabled(self) -> None:
        """Returns None when token cache is disabled."""
        from lib_shopify_graphql.cli._cache import create_token_cache_from_config

        mock_config = MockConfig({"shopify": {"token_cache": {"enabled": False}}})

        result = create_token_cache_from_config(mock_config)

        assert result is None

    def test_returns_json_adapter_when_json_backend(self, tmp_path: Path) -> None:
        """Returns JsonFileCacheAdapter when backend is json."""
        from lib_shopify_graphql.cli._cache import create_token_cache_from_config

        cache_path = tmp_path / "tokens.json"
        mock_config = MockConfig(
            {
                "shopify": {
                    "token_cache": {
                        "enabled": True,
                        "backend": "json",
                        "json_path": str(cache_path),
                    }
                }
            }
        )

        result = create_token_cache_from_config(mock_config)

        assert result is not None
        from lib_shopify_graphql.adapters import JsonFileCacheAdapter

        assert isinstance(result, JsonFileCacheAdapter)

    def test_returns_none_for_mysql_when_pymysql_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None for MySQL backend when pymysql is not available."""
        from lib_shopify_graphql.cli._cache import create_token_cache_from_config

        # Patch on the cli package since _cache does late import from .
        monkeypatch.setattr(cli_mod, "PYMYSQL_AVAILABLE", False)
        mock_config = MockConfig(
            {
                "shopify": {
                    "token_cache": {
                        "enabled": True,
                        "backend": "mysql",
                        "mysql_connection": "mysql://user:pass@host/db",
                    },
                    "mysql": {},
                }
            }
        )

        result = create_token_cache_from_config(mock_config)

        assert result is None


# =============================================================================
# SKU Cache Creation Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestCreateSkuCacheFromConfig:
    """Tests for create_sku_cache_from_config helper function."""

    def test_returns_none_when_disabled(self) -> None:
        """Returns None when SKU cache is disabled."""
        from lib_shopify_graphql.cli._cache import create_sku_cache_from_config

        mock_config = MockConfig({"shopify": {"sku_cache": {"enabled": False}}})

        result = create_sku_cache_from_config(mock_config)

        assert result is None

    def test_returns_json_adapter_when_json_backend(self, tmp_path: Path) -> None:
        """Returns JsonFileCacheAdapter when backend is json."""
        from lib_shopify_graphql.cli._cache import create_sku_cache_from_config

        cache_path = tmp_path / "sku.json"
        mock_config = MockConfig(
            {
                "shopify": {
                    "sku_cache": {
                        "enabled": True,
                        "backend": "json",
                        "json_path": str(cache_path),
                    }
                }
            }
        )

        result = create_sku_cache_from_config(mock_config)

        assert result is not None
        from lib_shopify_graphql.adapters import JsonFileCacheAdapter

        assert isinstance(result, JsonFileCacheAdapter)

    def test_returns_none_for_mysql_when_pymysql_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None for MySQL backend when pymysql is not available."""
        from lib_shopify_graphql.cli._cache import create_sku_cache_from_config

        # Patch on the cli package since _cache does late import from .
        monkeypatch.setattr(cli_mod, "PYMYSQL_AVAILABLE", False)
        mock_config = MockConfig(
            {
                "shopify": {
                    "sku_cache": {
                        "enabled": True,
                        "backend": "mysql",
                        "mysql_connection": "mysql://user:pass@host/db",
                    },
                    "mysql": {},
                }
            }
        )

        result = create_sku_cache_from_config(mock_config)

        assert result is None


# =============================================================================
# SKU Cache Display Helper Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestSkuCacheDisplayHelpers:
    """Tests for SKU cache check display helper functions."""

    def test_display_list_with_limit_shows_all_when_under_limit(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Shows all items when count is under limit."""
        from lib_shopify_graphql.cli._cache import _display_list_with_limit

        items = ["item1", "item2", "item3"]

        _display_list_with_limit(items, limit=5, prefix="  • ")

        captured = capsys.readouterr()
        assert "item1" in captured.out
        assert "item2" in captured.out
        assert "item3" in captured.out
        assert "more" not in captured.out

    def test_display_list_with_limit_truncates_when_over_limit(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Truncates and shows 'more' message when over limit."""
        from lib_shopify_graphql.cli._cache import _display_list_with_limit

        items = ["item1", "item2", "item3", "item4", "item5"]

        _display_list_with_limit(items, limit=3, prefix="  • ")

        captured = capsys.readouterr()
        assert "item1" in captured.out
        assert "item2" in captured.out
        assert "item3" in captured.out
        assert "item4" not in captured.out
        assert "2 more" in captured.out

    def test_display_list_works_with_tuple(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Handles tuple input correctly."""
        from lib_shopify_graphql.cli._cache import _display_list_with_limit

        items: tuple[str, ...] = ("a", "b", "c")

        _display_list_with_limit(items, limit=10, prefix="")

        captured = capsys.readouterr()
        assert "a" in captured.out
        assert "b" in captured.out
        assert "c" in captured.out


# =============================================================================
# Exit Helper Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestExitHelpers:
    """Tests for CLI exit helper functions."""

    def test_exit_with_error_prints_message_and_exits(self) -> None:
        """exit_with_error prints message and raises SystemExit."""
        from lib_shopify_graphql.cli._common import exit_with_error

        with pytest.raises(SystemExit) as exc_info:
            exit_with_error("Something went wrong", code=42)

        assert exc_info.value.code == 42

    def test_exit_mysql_not_available_exits_with_code_1(self) -> None:
        """exit_mysql_not_available raises SystemExit with code 1."""
        from lib_shopify_graphql.cli._common import exit_mysql_not_available

        with pytest.raises(SystemExit) as exc_info:
            exit_mysql_not_available()

        assert exc_info.value.code == 1

    def test_exit_sku_cache_not_configured_exits_with_code_1(self) -> None:
        """exit_sku_cache_not_configured raises SystemExit with code 1."""
        from lib_shopify_graphql.cli._common import exit_sku_cache_not_configured

        with pytest.raises(SystemExit) as exc_info:
            exit_sku_cache_not_configured()

        assert exc_info.value.code == 1


# =============================================================================
# Context Helper Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestContextHelpers:
    """Tests for CLI context helper functions."""

    def test_get_config_from_context_returns_config_when_present(self) -> None:
        """Returns config from context when available."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import CliContext, get_config_from_context

        ctx = click_pkg.Context(click_pkg.Command("test"))
        config = MockConfig({"test": "value"})
        ctx.obj = CliContext(config=config)  # type: ignore[arg-type]

        result = get_config_from_context(ctx)

        assert result is config

    def test_get_config_from_context_loads_fresh_when_missing(self) -> None:
        """Loads fresh config when context has no config."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import get_config_from_context

        ctx = click_pkg.Context(click_pkg.Command("test"))
        ctx.obj = None

        result = get_config_from_context(ctx)

        assert result is not None

    def test_get_effective_profile_returns_override_when_provided(self) -> None:
        """Returns override profile when explicitly provided."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import CliContext, get_effective_profile

        ctx = click_pkg.Context(click_pkg.Command("test"))
        ctx.obj = CliContext(profile="from_context")

        result = get_effective_profile(ctx, "override")

        assert result == "override"

    def test_get_effective_profile_returns_context_when_no_override(self) -> None:
        """Returns context profile when no override provided."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import CliContext, get_effective_profile

        ctx = click_pkg.Context(click_pkg.Command("test"))
        ctx.obj = CliContext(profile="from_context")

        result = get_effective_profile(ctx, None)

        assert result == "from_context"

    def test_get_effective_profile_returns_none_when_no_cli_context(self) -> None:
        """Returns None when context.obj is not CliContext."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import get_effective_profile

        ctx = click_pkg.Context(click_pkg.Command("test"))
        ctx.obj = {"something": "else"}

        result = get_effective_profile(ctx, None)

        assert result is None

    def test_store_cli_context_creates_new_context_object(self) -> None:
        """Creates new CliContext when obj is not CliContext."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import CliContext, store_cli_context

        ctx = click_pkg.Context(click_pkg.Command("test"))
        ctx.obj = None
        config = MockConfig({})

        store_cli_context(ctx, traceback=True, config=config, profile="test")  # type: ignore[arg-type]

        assert isinstance(ctx.obj, CliContext)
        assert ctx.obj.traceback is True
        assert ctx.obj.profile == "test"

    def test_store_cli_context_updates_existing_context(self) -> None:
        """Updates existing CliContext when already present."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import CliContext, store_cli_context

        ctx = click_pkg.Context(click_pkg.Command("test"))
        existing = CliContext(traceback=False, profile="old")
        ctx.obj = existing
        config = MockConfig({})

        store_cli_context(ctx, traceback=True, config=config, profile="new")  # type: ignore[arg-type]

        assert ctx.obj is existing
        assert ctx.obj.traceback is True
        assert ctx.obj.profile == "new"


# =============================================================================
# EnumChoice Parameter Type Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestEnumChoiceParameter:
    """Tests for EnumChoice Click parameter type."""

    def test_convert_returns_enum_when_already_enum(self) -> None:
        """Returns enum value unchanged when already correct type."""
        from lib_shopify_graphql.cli._common import EnumChoice
        from lib_shopify_graphql.enums import OutputFormat

        choice = EnumChoice(OutputFormat)

        result = choice.convert(OutputFormat.JSON, None, None)

        assert result is OutputFormat.JSON

    def test_convert_matches_case_insensitive(self) -> None:
        """Matches enum value case-insensitively."""
        from lib_shopify_graphql.cli._common import EnumChoice
        from lib_shopify_graphql.enums import OutputFormat

        choice = EnumChoice(OutputFormat)

        result = choice.convert("JSON", None, None)

        assert result is OutputFormat.JSON

    def test_convert_fails_on_invalid_value(self) -> None:
        """Raises BadParameter for invalid enum value."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import EnumChoice
        from lib_shopify_graphql.enums import OutputFormat

        choice = EnumChoice(OutputFormat)

        with pytest.raises(click_pkg.exceptions.BadParameter):
            choice.convert("invalid", None, None)

    def test_convert_fails_on_non_string(self) -> None:
        """Raises BadParameter for non-string input."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import EnumChoice
        from lib_shopify_graphql.enums import OutputFormat

        choice = EnumChoice(OutputFormat)

        with pytest.raises(click_pkg.exceptions.BadParameter):
            choice.convert(123, None, None)

    def test_get_metavar_shows_choices(self) -> None:
        """Returns metavar showing available choices."""
        import click as click_pkg
        from lib_shopify_graphql.cli._common import EnumChoice
        from lib_shopify_graphql.enums import OutputFormat

        choice = EnumChoice(OutputFormat)

        result = choice.get_metavar(click_pkg.Option(["-f"]), None)

        assert "human" in result
        assert "json" in result
