"""Configuration display functionality for CLI config command.

Provides the business logic for displaying merged configuration from all
sources in human-readable or JSON format. Keeps CLI layer thin by handling
all formatting and display logic here.

Contents:
    * :func:`display_config` - displays configuration in requested format

System Role:
    Lives in the behaviors layer. The CLI command delegates to this module for
    all configuration display logic, keeping presentation concerns separate from
    command-line argument parsing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn, cast

import click
import orjson

from .enums import OutputFormat

if TYPE_CHECKING:
    from lib_layered_config import Config


def _exit_section_not_found(section: str) -> NoReturn:
    """Report a missing/empty section and exit with a non-zero status."""
    click.echo(f"Section '{section}' not found or empty", err=True)
    raise SystemExit(1)


def _format_toml_value(value: Any) -> str:
    """Render a single value the way the TOML-like human display expects."""
    if isinstance(value, (list, dict)):
        return orjson.dumps(value).decode()
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def _echo_toml_section(name: str, section_data: dict[str, Any]) -> None:
    """Echo one `[name]` section header followed by its key = value lines."""
    click.echo(f"\n[{name}]")
    for key, value in section_data.items():
        click.echo(f"  {key} = {_format_toml_value(value)}")


def _display_json(config: Config, section: str | None) -> None:
    """Display the config (or one section of it) as JSON."""
    if section is None:
        # Use lib_layered_config's built-in to_json method
        click.echo(config.to_json(indent=2))
        return

    section_data = config.get(section, default={})
    if not section_data:
        _exit_section_not_found(section)
    click.echo(orjson.dumps({section: section_data}, option=orjson.OPT_INDENT_2).decode())


def _display_human(config: Config, section: str | None) -> None:
    """Display the config (or one section of it) as TOML-like text."""
    if section is not None:
        section_data = config.get(section, default={})
        if not section_data:
            _exit_section_not_found(section)
        _echo_toml_section(section, section_data)
        return

    # Show all configuration
    data: dict[str, Any] = config.as_dict()
    for section_name, section_data in data.items():
        if isinstance(section_data, dict):
            _echo_toml_section(section_name, cast("dict[str, Any]", section_data))
        else:
            click.echo(f"\n[{section_name}]")
            click.echo(f"  {section_data}")


def display_config(
    config: Config,
    *,
    format: OutputFormat = OutputFormat.HUMAN,  # noqa: A002 - public API: "format" mirrors the CLI --format option, keyword-only
    section: str | None = None,
) -> None:
    """Display the provided configuration in the requested format.

    Users need visibility into the effective configuration loaded from
    defaults, app configs, host configs, user configs, .env files, and
    environment variables. Outputs the provided Config object in the
    requested format.

    Args:
        config: Already-loaded layered configuration object to display.
        format: Output format: OutputFormat.HUMAN for TOML-like display or
            OutputFormat.JSON for JSON. Defaults to OutputFormat.HUMAN.
        section: Optional section name to display only that section. When None,
            displays all configuration.

    Side Effects:
        Writes formatted configuration to stdout via click.echo().
        Raises SystemExit(1) if requested section doesn't exist.

    Note:
        The human-readable format mimics TOML syntax for consistency with the
        configuration file format. JSON format provides machine-readable output
        suitable for parsing by other tools.

    Example:
        >>> from lib_shopify_graphql.config import get_config
        >>> config = get_config()  # doctest: +SKIP
        >>> display_config(config)  # doctest: +SKIP
        [lib_log_rich]
          service = "lib_shopify_graphql"
          environment = "prod"

        >>> display_config(config, format=OutputFormat.JSON)  # doctest: +SKIP
        {
          "lib_log_rich": {
            "service": "lib_shopify_graphql",
            "environment": "prod"
          }
        }
    """
    if format == OutputFormat.JSON:
        _display_json(config, section)
    else:
        _display_human(config, section)


__all__ = [
    "display_config",
]
