"""Common CLI utilities, models, and shared infrastructure.

This module contains shared components used across CLI commands:
- Configuration models (TokenCacheConfig, SKUCacheConfig, MySQLConfig)
- Click parameter types (EnumChoice)
- Context management (CliContext, TracebackState)
- Traceback utilities
- Output helpers
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Final, Generic, NoReturn, TypeVar

import lib_cli_exit_tools
import rich_click as click
from lib_layered_config import Config
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Sequence

from .. import __init__conf__
from ..config import get_config

E = TypeVar("E", bound=Enum)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Shared Click context flags so help output stays consistent across commands.
CLICK_CONTEXT_SETTINGS: Final[dict[str, list[str]]] = {"help_option_names": ["-h", "--help"]}
#: Character budget used when printing truncated tracebacks.
TRACEBACK_SUMMARY_LIMIT: Final[int] = 500
#: Character budget used when verbose tracebacks are enabled.
TRACEBACK_VERBOSE_LIMIT: Final[int] = 10_000

# =============================================================================
# Typed Configuration Models
# =============================================================================


class TokenCacheConfig(BaseModel):
    """Typed configuration for token cache settings.

    Validates and provides typed access to token cache configuration
    from lib_layered_config.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    backend: str = "json"
    json_path: str = ""
    mysql_connection: str = ""
    mysql_table: str = "token_cache"


class SKUCacheConfig(BaseModel):
    """Typed configuration for SKU cache settings.

    Validates and provides typed access to SKU cache configuration
    from lib_layered_config.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    backend: str = "json"
    json_path: str = ""
    mysql_connection: str = ""
    mysql_table: str = "sku_cache"


class MySQLConfig(BaseModel):
    """Typed configuration for shared MySQL settings.

    Validates and provides typed access to [shopify.mysql] configuration.
    Used when individual MySQL parameters are preferred over a connection string.
    """

    model_config = ConfigDict(extra="ignore")

    # Connection string (takes precedence if set)
    connection: str = ""

    # Individual parameters (used when connection is empty)
    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = ""

    # Common settings
    auto_create_database: bool = True
    connect_timeout: int = 10


# =============================================================================
# Click Parameter Types
# =============================================================================


class EnumChoice(click.ParamType, Generic[E]):
    """Click parameter type that converts strings to enum values at the boundary.

    This ensures string-to-enum conversion happens at the CLI edge,
    following data architecture rules.

    Attributes:
        enum_type: The enum class to convert values to.
        name: Display name for the parameter type.
    """

    def __init__(self, enum_type: type[E]) -> None:
        """Initialize with the enum type to convert to.

        Args:
            enum_type: Enum class to convert string values to.
        """
        self.enum_type = enum_type
        self.name = enum_type.__name__

    def get_metavar(self, param: click.Parameter, ctx: click.Context | None = None) -> str:  # noqa: ARG002
        """Return the metavar for help display."""
        choices = [str(e.value) for e in self.enum_type]
        return "[" + "|".join(choices) + "]"

    def convert(
        self,
        value: object,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> E:
        """Convert string value to enum at the CLI boundary.

        Args:
            value: String from command line or enum value.
            param: Click parameter (for error reporting).
            ctx: Click context (for error reporting).

        Returns:
            Enum value of the appropriate type.
        """
        if isinstance(value, self.enum_type):
            return value  # type: ignore[return-value]

        if not isinstance(value, str):
            self.fail(f"Expected string or {self.enum_type.__name__}, got {type(value).__name__}", param, ctx)

        # Case-insensitive matching: try exact match first, then case variations
        for enum_member in self.enum_type:
            if value == enum_member.value or value.lower() == enum_member.value.lower():
                return enum_member  # type: ignore[return-value]

        choices = ", ".join(str(e.value) for e in self.enum_type)
        self.fail(f"'{value}' is not a valid choice. Choose from: {choices}", param, ctx)


# =============================================================================
# Context and State Management
# =============================================================================


@dataclass(frozen=True, slots=True)
class TracebackState:
    """Immutable snapshot of traceback configuration.

    Attributes:
        traceback_enabled: Whether verbose tracebacks are active.
        force_color: Whether color output is forced for tracebacks.
    """

    traceback_enabled: bool
    force_color: bool


@dataclass(slots=True)
class CliContext:
    """Typed context object for Click commands.

    Replaces untyped dict-based context with a structured dataclass,
    providing type safety for CLI state management.

    Attributes:
        traceback: Whether verbose tracebacks were requested.
        profile: Configuration profile name for environment isolation.
        config: Loaded layered configuration object for all subcommands.
    """

    traceback: bool = False
    profile: str | None = None
    config: Config | None = field(default=None)


# =============================================================================
# Traceback Utilities
# =============================================================================


def apply_traceback_preferences(enabled: bool) -> None:
    """Synchronise shared traceback flags with the requested preference.

    ``lib_cli_exit_tools`` inspects global flags to decide whether tracebacks
    should be truncated and whether colour should be forced. Updating both
    attributes together ensures the ``--traceback`` flag behaves the same for
    console scripts and ``python -m`` execution.

    Args:
        enabled: ``True`` enables full tracebacks with colour. ``False`` restores
            the compact summary mode.
    """
    lib_cli_exit_tools.config.traceback = bool(enabled)
    lib_cli_exit_tools.config.traceback_force_color = bool(enabled)


def snapshot_traceback_state() -> TracebackState:
    """Capture the current traceback configuration for later restoration.

    Returns:
        TracebackState dataclass with current configuration.
    """
    return TracebackState(
        traceback_enabled=bool(getattr(lib_cli_exit_tools.config, "traceback", False)),
        force_color=bool(getattr(lib_cli_exit_tools.config, "traceback_force_color", False)),
    )


def restore_traceback_state(state: TracebackState) -> None:
    """Reapply a previously captured traceback configuration.

    Args:
        state: TracebackState dataclass returned by :func:`snapshot_traceback_state`.
    """
    lib_cli_exit_tools.config.traceback = state.traceback_enabled
    lib_cli_exit_tools.config.traceback_force_color = state.force_color


# =============================================================================
# Context Helpers
# =============================================================================


def store_cli_context(
    ctx: click.Context,
    *,
    traceback: bool,
    config: Config,
    profile: str | None = None,
) -> None:
    """Store CLI state in the Click context for subcommand access.

    Args:
        ctx: Click context associated with the current invocation.
        traceback: Whether verbose tracebacks were requested.
        config: Loaded layered configuration object for all subcommands.
        profile: Optional configuration profile name for environment isolation.
    """
    if isinstance(ctx.obj, CliContext):
        ctx.obj.traceback = traceback
        ctx.obj.profile = profile
        ctx.obj.config = config
    else:
        ctx.obj = CliContext(traceback=traceback, profile=profile, config=config)


def get_effective_profile(ctx: click.Context, profile: str | None) -> str | None:
    """Resolve effective profile from override or context."""
    if profile:
        return profile
    return ctx.obj.profile if isinstance(ctx.obj, CliContext) else None


def get_effective_config_and_profile(ctx: click.Context, profile: str | None) -> tuple[Config, str | None]:
    """Resolve config and effective profile from context or reload if overridden."""
    if profile:
        return get_config(profile=profile), profile
    if isinstance(ctx.obj, CliContext) and ctx.obj.config is not None:
        return ctx.obj.config, ctx.obj.profile
    return get_config(), None


def get_config_from_context(ctx: click.Context) -> Config:
    """Get configuration from Click context, with fallback to loading fresh config."""
    if isinstance(ctx.obj, CliContext) and ctx.obj.config is not None:
        return ctx.obj.config
    return get_config()


# =============================================================================
# CLI Execution
# =============================================================================


def run_cli(cli_group: click.Group, argv: Sequence[str] | None) -> int:
    """Execute the CLI via lib_cli_exit_tools with exception handling.

    Args:
        cli_group: The root Click group to execute.
        argv: Optional sequence of CLI arguments. None uses sys.argv.

    Returns:
        Exit code produced by the command.
    """
    try:
        return lib_cli_exit_tools.run_cli(
            cli_group,
            argv=list(argv) if argv is not None else None,
            prog_name=__init__conf__.shell_command,
        )
    except BaseException as exc:  # noqa: BLE001 - handled by shared printers
        tracebacks_enabled = bool(getattr(lib_cli_exit_tools.config, "traceback", False))
        apply_traceback_preferences(tracebacks_enabled)
        length_limit = TRACEBACK_VERBOSE_LIMIT if tracebacks_enabled else TRACEBACK_SUMMARY_LIMIT
        lib_cli_exit_tools.print_exception_message(trace_back=tracebacks_enabled, length_limit=length_limit)
        return lib_cli_exit_tools.get_system_exit_code(exc)


# =============================================================================
# Exit Helpers
# =============================================================================


def exit_with_error(message: str, code: int = 1) -> NoReturn:
    """Print error message and exit with the given code."""
    click.echo(f"Error: {message}", err=True)
    raise SystemExit(code)


def exit_mysql_not_available() -> NoReturn:
    """Exit with error message about PyMySQL not being installed."""
    click.echo("Error: PyMySQL is not installed. Install with: pip install lib_shopify_graphql[mysql]", err=True)
    raise SystemExit(1)


def exit_sku_cache_not_configured() -> NoReturn:
    """Exit with error message about SKU cache not being configured."""
    click.echo("Error: SKU cache is not configured.", err=True)
    click.echo("", err=True)
    click.echo("Configure SKU cache in your configuration file:", err=True)
    click.echo("", err=True)
    click.echo("  [shopify.sku_cache]", err=True)
    click.echo("  enabled = true", err=True)
    click.echo('  backend = "json"  # or "mysql"', err=True)
    click.echo('  json_path = "/path/to/sku_cache.json"', err=True)
    raise SystemExit(1)


__all__ = [
    # Constants
    "CLICK_CONTEXT_SETTINGS",
    "TRACEBACK_SUMMARY_LIMIT",
    "TRACEBACK_VERBOSE_LIMIT",
    # Config models
    "TokenCacheConfig",
    "SKUCacheConfig",
    "MySQLConfig",
    # Click types
    "EnumChoice",
    # State classes
    "TracebackState",
    "CliContext",
    # Traceback functions
    "apply_traceback_preferences",
    "snapshot_traceback_state",
    "restore_traceback_state",
    # Context helpers
    "store_cli_context",
    "get_effective_profile",
    "get_effective_config_and_profile",
    "get_config_from_context",
    # CLI execution
    "run_cli",
    # Exit helpers
    "exit_with_error",
    "exit_mysql_not_available",
    "exit_sku_cache_not_configured",
]
