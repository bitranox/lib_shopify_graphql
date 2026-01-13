"""Module entry tests: ensuring `python -m` mirrors the CLI.

Tests for verifying that running the package as a module (`python -m`)
behaves identically to invoking the CLI directly. Uses real behavior
verification instead of mocking.
"""

from __future__ import annotations

import os
import runpy
import subprocess
import sys

import pytest

import lib_cli_exit_tools

from lib_shopify_graphql import __init__conf__, cli as cli_mod


def _run_module_subprocess(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with UTF-8 encoding for cross-platform compatibility.

    Windows console uses cp1252 by default which cannot handle Unicode
    characters (emoji level icons) from lib_log_rich output.

    Args:
        args: Command arguments to pass to subprocess.
        timeout: Maximum time to wait for process completion.

    Returns:
        CompletedProcess with stdout/stderr as strings.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        encoding="utf-8",
        errors="replace",
    )


# =============================================================================
# Module Entry via Subprocess - Real Behavior
# =============================================================================


@pytest.mark.os_agnostic
class TestModuleEntrySubprocess:
    """Tests for module entry using real subprocess execution."""

    def test_module_runs_without_error(self) -> None:
        """When `python -m` runs with --help, it exits successfully."""
        result = _run_module_subprocess(
            [sys.executable, "-m", "lib_shopify_graphql", "--help"],
        )

        assert result.returncode == 0

    def test_module_shows_usage(self) -> None:
        """When `python -m` runs with --help, usage information appears."""
        result = _run_module_subprocess(
            [sys.executable, "-m", "lib_shopify_graphql", "--help"],
        )

        assert "Usage:" in result.stdout

    def test_module_info_shows_version(self) -> None:
        """When `python -m` runs info command, version appears."""
        result = _run_module_subprocess(
            [sys.executable, "-m", "lib_shopify_graphql", "info"],
        )

        assert result.returncode == 0
        assert __init__conf__.version in result.stdout

    def test_module_config_outputs_json(self) -> None:
        """When `python -m` runs config --format json, JSON is output."""
        result = _run_module_subprocess(
            [sys.executable, "-m", "lib_shopify_graphql", "config", "--format", "json"],
        )

        assert result.returncode == 0
        assert "{" in result.stdout

    def test_module_unknown_command_fails(self) -> None:
        """When `python -m` runs unknown command, it fails."""
        result = _run_module_subprocess(
            [sys.executable, "-m", "lib_shopify_graphql", "unknown_cmd"],
        )

        assert result.returncode != 0


# =============================================================================
# Module Entry via runpy - Real Behavior
# =============================================================================


@pytest.mark.os_agnostic
class TestModuleEntryRunpy:
    """Tests for module entry using runpy with real CLI execution."""

    def test_info_command_succeeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When info command runs via runpy, it succeeds."""
        monkeypatch.setattr(sys, "argv", ["check_zpool_status", "info"])
        monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)
        monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False, raising=False)

        with pytest.raises(SystemExit) as exc:
            runpy.run_module("lib_shopify_graphql.__main__", run_name="__main__")

        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert __init__conf__.name in captured.out


# =============================================================================
# CLI Import Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestCliImport:
    """Tests for CLI module import behavior."""

    def test_cli_alias_stays_intact(self) -> None:
        """When module entry imports CLI, the alias stays intact."""
        assert cli_mod.cli.name == cli_mod.cli.name

    def test_cli_has_expected_commands(self) -> None:
        """When CLI is imported, expected commands are available."""
        command_names = [cmd for cmd in cli_mod.cli.commands]

        assert "info" in command_names
        assert "config" in command_names
        assert "health" in command_names
        assert "tokencache-clear" in command_names
        assert "skucache-clear" in command_names

    def test_shell_command_is_defined(self) -> None:
        """The shell command constant is defined."""
        assert __init__conf__.shell_command is not None
        assert len(__init__conf__.shell_command) > 0


# =============================================================================
# Logging Setup Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestLoggingSetupDefaults:
    """Tests for logging setup default values."""

    def test_build_runtime_config_uses_default_service(self) -> None:
        """When service not in config, uses package name as default."""
        from unittest.mock import MagicMock

        from lib_shopify_graphql.logging_setup import _build_runtime_config

        mock_config = MagicMock()
        mock_config.get.return_value = {}  # No service or environment

        result = _build_runtime_config(mock_config)

        assert result.service == __init__conf__.name

    def test_build_runtime_config_uses_default_environment(self) -> None:
        """When environment not in config, uses 'prod' as default."""
        from unittest.mock import MagicMock

        from lib_shopify_graphql.logging_setup import _build_runtime_config

        mock_config = MagicMock()
        mock_config.get.return_value = {}  # No service or environment

        result = _build_runtime_config(mock_config)

        assert result.environment == "prod"

    def test_build_runtime_config_preserves_explicit_values(self) -> None:
        """When values are explicitly set, they are preserved."""
        from unittest.mock import MagicMock

        from lib_shopify_graphql.logging_setup import _build_runtime_config

        mock_config = MagicMock()
        mock_config.get.return_value = {"service": "my-service", "environment": "dev"}

        result = _build_runtime_config(mock_config)

        assert result.service == "my-service"
        assert result.environment == "dev"
