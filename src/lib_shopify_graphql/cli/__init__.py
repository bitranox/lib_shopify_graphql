"""CLI package for lib_shopify_graphql.

This package provides the command-line interface for Shopify GraphQL operations.

Modules:
    _common: Shared utilities, models, and context management
    _config: Configuration display and deployment commands
    _health: Health check command
    _cache: Cache management commands
    _products: Product CRUD commands
    _images: Image operation commands
    _test_limits: Test limits command for truncation analysis

The main entry point is the :func:`main` function which creates the CLI group
and registers all commands.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import lib_log_rich.runtime
import rich_click as click

from .. import __init__conf__
from ..adapters import PYMYSQL_AVAILABLE
from ..config import get_config
from ..enums import OutputFormat
from ..logging_setup import init_logging

# Import login/logout so tests can patch them on the cli module
from ..shopify_client import login, logout
from ._cache import (
    create_mysql_cache_adapter,
    create_sku_cache_from_config,
    register_cache_commands,
)
from ._common import (
    CLICK_CONTEXT_SETTINGS,
    TRACEBACK_SUMMARY_LIMIT,
    TRACEBACK_VERBOSE_LIMIT,
    CliContext,
    EnumChoice,
    MySQLConfig,
    TracebackState,
    apply_traceback_preferences,
    restore_traceback_state,
    run_cli,
    snapshot_traceback_state,
    store_cli_context,
)
from ._config import register_config_commands
from ._health import (
    HealthCheckResult,
    extract_shopify_credentials_from_config,
    get_credentials_or_exit,
    get_fix_suggestion,
    register_health_command,
)
from ._images import (
    _output_reorder_result,
    _parse_image_ids,
    register_image_commands,
)
from ._products import (
    _build_product_create_from_options,
    _flatten_seo_fields,
    _output_product,
    _parse_product_create_json,
    _read_json_input,
    _strip_readonly_create_fields,
    register_product_commands,
)
from ._test_limits import register_test_limits_command

logger = logging.getLogger(__name__)

# Internal function aliases for test access
_extract_shopify_credentials_from_config = extract_shopify_credentials_from_config
_get_fix_suggestion = get_fix_suggestion
_create_mysql_cache_adapter = create_mysql_cache_adapter


# =============================================================================
# CLI Root Group
# =============================================================================


@click.group(
    help=__init__conf__.title,
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.version_option(
    version=__init__conf__.version,
    prog_name=__init__conf__.shell_command,
    message=f"{__init__conf__.shell_command} version {__init__conf__.version}",
)
@click.option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help="Show full Python traceback on errors",
)
@click.option(
    "--profile",
    type=str,
    default=None,
    help="Load configuration from a named profile (e.g., 'production', 'test')",
)
@click.pass_context
def cli(ctx: click.Context, traceback: bool, profile: str | None) -> None:
    """Root command storing global flags and syncing shared traceback state.

    Loads configuration once with the profile and stores it in the Click context
    for all subcommands to access. Mirrors the traceback flag into
    ``lib_cli_exit_tools.config`` so downstream helpers observe the preference.
    """
    config = get_config(profile=profile)
    init_logging(config)
    store_cli_context(ctx, traceback=traceback, config=config, profile=profile)
    apply_traceback_preferences(traceback)

    if ctx.invoked_subcommand is None:
        # No subcommand: show help
        click.echo(ctx.get_help())


# =============================================================================
# Info Command
# =============================================================================


@cli.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_info() -> None:
    """Print resolved metadata so users can inspect installation details."""
    with lib_log_rich.runtime.bind(job_id="cli-info", extra={"command": "info"}):
        logger.info("Displaying package information")
        __init__conf__.print_info()


# =============================================================================
# Register Commands
# =============================================================================

# Register config commands (config, config-deploy)
register_config_commands(cli)

# Register health check command
register_health_command(cli)

# Register cache commands (tokencache-clear, skucache-clear, etc.)
register_cache_commands(cli, get_credentials_or_exit, get_fix_suggestion)

# Register test-limits command
register_test_limits_command(cli, get_credentials_or_exit, get_fix_suggestion)

# Register product commands (get-product, create-product, etc.)
register_product_commands(cli, get_credentials_or_exit, get_fix_suggestion, create_sku_cache_from_config)

# Register image commands (add-image, delete-image, etc.)
register_image_commands(cli, get_credentials_or_exit, get_fix_suggestion)


# =============================================================================
# Main Entry Point
# =============================================================================


def main(argv: Sequence[str] | None = None, *, restore_traceback: bool = True) -> int:
    """Execute the CLI with error handling and return the exit code.

    Provides the single entry point used by console scripts and
    ``python -m`` execution so that behaviour stays identical across transports.

    Args:
        argv: Optional sequence of CLI arguments. None uses sys.argv.
        restore_traceback: Whether to restore prior traceback configuration after execution.

    Returns:
        Exit code reported by the CLI run.
    """
    previous_state = snapshot_traceback_state()
    try:
        return run_cli(cli, argv)
    finally:
        if restore_traceback:
            restore_traceback_state(previous_state)
        if lib_log_rich.runtime.is_initialised():
            lib_log_rich.runtime.shutdown()


__all__ = [
    # Main CLI components
    "cli",
    "main",
    # Constants
    "CLICK_CONTEXT_SETTINGS",
    "TRACEBACK_SUMMARY_LIMIT",
    "TRACEBACK_VERBOSE_LIMIT",
    # Re-exported types and utilities
    "CliContext",
    "EnumChoice",
    "HealthCheckResult",
    "MySQLConfig",
    "OutputFormat",
    "TracebackState",
    "apply_traceback_preferences",
    "snapshot_traceback_state",
    "restore_traceback_state",
    # Adapter constants
    "PYMYSQL_AVAILABLE",
    # Session functions (for test patching)
    "login",
    "logout",
    # Internal functions (exported for tests)
    "_build_product_create_from_options",
    "_create_mysql_cache_adapter",
    "_extract_shopify_credentials_from_config",
    "_flatten_seo_fields",
    "_get_fix_suggestion",
    "_output_product",
    "_output_reorder_result",
    "_parse_image_ids",
    "_parse_product_create_json",
    "_read_json_input",
    "_strip_readonly_create_fields",
    # Click module (for test patching)
    "click",
]
