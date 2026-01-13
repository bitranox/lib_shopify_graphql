"""Configuration management CLI commands.

This module provides CLI commands for displaying and deploying configuration:
- config: Display current merged configuration
- config-deploy: Deploy default configuration to system/user directories
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NoReturn

import lib_log_rich.runtime
import rich_click as click

from ..config_deploy import deploy_configuration
from ..config_show import display_config
from ..enums import DeployTarget, OutputFormat
from ._common import (
    CLICK_CONTEXT_SETTINGS,
    EnumChoice,
    get_effective_config_and_profile,
    get_effective_profile,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Deployment Helpers
# =============================================================================


def _report_deployment_result(deployed_paths: list[Path], effective_profile: str | None) -> None:
    """Report deployment result to user."""
    if deployed_paths:
        profile_msg = f" (profile: {effective_profile})" if effective_profile else ""
        click.echo(f"\nConfiguration deployed successfully{profile_msg}:")
        for path in deployed_paths:
            click.echo(f"  ✓ {path}")
    else:
        click.echo("\nNo files were created (all target files already exist).")
        click.echo("Use --force to overwrite existing configuration files.")


def _handle_deploy_permission_error(exc: PermissionError) -> NoReturn:
    """Handle permission error during deployment."""
    logger.error("Permission denied when deploying configuration", extra={"error": str(exc)})
    click.echo(f"\nError: Permission denied. {exc}", err=True)
    click.echo("Hint: System-wide deployment (--target app/host) may require sudo.", err=True)
    raise SystemExit(1)


def _handle_deploy_error(exc: Exception) -> NoReturn:
    """Handle generic error during deployment."""
    logger.error("Failed to deploy configuration", extra={"error": str(exc), "error_type": type(exc).__name__})
    click.echo(f"\nError: Failed to deploy configuration: {exc}", err=True)
    raise SystemExit(1)


def _execute_deployment(targets: tuple[DeployTarget, ...], force: bool, effective_profile: str | None) -> None:
    """Execute deployment with error handling (reduces nesting in cli_config_deploy)."""
    try:
        deployed_paths = deploy_configuration(targets=targets, force=force, profile=effective_profile)
        _report_deployment_result(deployed_paths, effective_profile)
    except PermissionError as exc:
        _handle_deploy_permission_error(exc)
    except Exception as exc:
        _handle_deploy_error(exc)


# =============================================================================
# CLI Commands
# =============================================================================


def register_config_commands(cli_group: click.Group) -> None:
    """Register configuration management commands on the CLI group.

    Args:
        cli_group: The Click group to register commands on.
    """

    @cli_group.command("config", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.HUMAN,
        help="Output format (human-readable or JSON)",
    )
    @click.option(
        "--section",
        type=str,
        default=None,
        help="Show only a specific configuration section (e.g., 'lib_log_rich')",
    )
    @click.option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command (e.g., 'production', 'test')",
    )
    @click.pass_context
    def cli_config(ctx: click.Context, output_format: OutputFormat, section: str | None, profile: str | None) -> None:
        """Display the current merged configuration from all sources.

        Shows configuration loaded from:
        - Default config (built-in)
        - Application config (/etc/xdg/lib-shopify-graphql/config.toml)
        - User config (~/.config/lib-shopify-graphql/config.toml)
        - .env files
        - Environment variables (LIB_SHOPIFY_GRAPHQL_*)

        Precedence: defaults → app → host → user → dotenv → env

        When --profile is specified (at root or here), configuration is loaded from
        profile-specific subdirectories (e.g., ~/.config/slug/profile/<name>/config.toml).
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "config", "format": output_format.value, "profile": effective_profile}
        with lib_log_rich.runtime.bind(job_id="cli-config", extra=extra):
            if output_format != OutputFormat.JSON:
                logger.info(f"Displaying configuration: format='{output_format.value}', section='{section}', profile='{effective_profile}'")
            display_config(config, format=output_format, section=section)

    @cli_group.command("config-deploy", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.option(
        "--target",
        "targets",
        type=EnumChoice(DeployTarget),
        multiple=True,
        required=True,
        help="Target configuration layer(s) to deploy to (can specify multiple)",
    )
    @click.option(
        "--force",
        is_flag=True,
        default=False,
        help="Overwrite existing configuration files",
    )
    @click.option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command (e.g., 'production', 'test')",
    )
    @click.pass_context
    def cli_config_deploy(ctx: click.Context, targets: tuple[DeployTarget, ...], force: bool, profile: str | None) -> None:
        r"""Deploy default configuration to system or user directories.

        Creates configuration files in platform-specific locations:

        \b
        - app:  System-wide application config (requires privileges)
        - host: System-wide host config (requires privileges)
        - user: User-specific config (~/.config on Linux)

        By default, existing files are not overwritten. Use --force to overwrite.

        When --profile is specified (at root or here), configuration is deployed to
        profile-specific subdirectories (e.g., ~/.config/slug/profile/<name>/config.toml).

        Examples:
            \b
            # Deploy to user config directory
            $ lib-shopify-graphql config-deploy --target user

            \b
            # Deploy to both app and user directories
            $ lib-shopify-graphql config-deploy --target app --target user

            \b
            # Force overwrite existing config
            $ lib-shopify-graphql config-deploy --target user --force

            \b
            # Deploy to production profile
            $ lib-shopify-graphql config-deploy --target user --profile production
        """
        effective_profile = get_effective_profile(ctx, profile)
        target_values = tuple(t.value for t in targets)
        extra = {"command": "config-deploy", "targets": target_values, "force": force, "profile": effective_profile}
        with lib_log_rich.runtime.bind(job_id="cli-config-deploy", extra=extra):
            logger.info(f"Deploying configuration: targets={target_values}, force={force}, profile='{effective_profile}'")
            _execute_deployment(targets, force, effective_profile)


__all__ = [
    "register_config_commands",
]
