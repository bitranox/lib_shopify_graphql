"""Configuration management using lib_layered_config.

Provides a centralized configuration loader that merges defaults, application
configs, host configs, user configs, .env files, and environment variables
following a deterministic precedence order.

This module contains:
    - :func:`get_config`: loads configuration with lib_layered_config.
    - :func:`get_default_config_path`: returns path to bundled default config.

Configuration identifiers (vendor, app, slug) are imported from
:mod:`lib_shopify_graphql.__init__conf__` as LAYEREDCONF_* constants.

Note:
    Acts as the configuration adapter layer, bridging lib_layered_config with the
    application's runtime needs while keeping domain logic decoupled from
    configuration mechanics.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lib_layered_config import Config, read_config

from . import __init__conf__


def get_default_config_path() -> Path:
    """Return the path to the bundled default configuration file.

    The default configuration ships with the package and needs to be
    locatable at runtime regardless of how the package is installed.
    Uses __file__ to locate the defaultconfig.toml file relative to this
    module.

    Returns:
        Absolute path to defaultconfig.toml.

    Example:
        >>> path = get_default_config_path()
        >>> path.name
        'defaultconfig.toml'
        >>> path.exists()
        True
    """
    return Path(__file__).parent / "defaultconfig.toml"


# Cache configuration to avoid redundant file I/O and parsing.
# Trade-offs:
#   ✅ Future-proof if config is read from multiple places
#   ✅ Near-zero overhead (single cache entry)
#   ❌ Prevents dynamic config reloading (if ever needed)
#   ❌ start_dir/profile parameter variations would bypass cache
@lru_cache(maxsize=4)
def get_config(*, profile: str | None = None, start_dir: str | None = None) -> Config:
    """Load layered configuration with application defaults.

    Centralizes configuration loading so all entry points use the same
    precedence rules and default values without duplicating the discovery
    logic. Uses lru_cache to avoid redundant file reads when called from
    multiple modules.

    Loads configuration from multiple sources in precedence order:
    defaults → app → host → user → dotenv → env

    The vendor, app, and slug identifiers determine platform-specific paths:
        - Linux: Uses XDG directories with slug
        - macOS: Uses Library/Application Support with vendor/app
        - Windows: Uses ProgramData/AppData with vendor/app

    When a profile is specified, configuration is loaded from profile-specific
    subdirectories (e.g., ~/.config/slug/profile/<name>/config.toml).

    Args:
        profile: Optional profile name for environment isolation. When specified,
            a ``profile/<name>/`` subdirectory is inserted into all configuration
            paths. Valid names: alphanumeric, hyphens, underscores. Examples:
            'test', 'production', 'staging-v2'. Defaults to None (no profile).
        start_dir: Optional directory that seeds .env discovery. Defaults to
            current working directory when None.

    Returns:
        Immutable configuration object with provenance tracking.

    Note:
        This function is cached (maxsize=4). The first call loads and parses all
        configuration files; subsequent calls with the same parameters return the
        cached Config instance immediately.

    Example:
        >>> config = get_config()
        >>> isinstance(config.as_dict(), dict)
        True
        >>> config.get("nonexistent", default="fallback")
        'fallback'

        >>> # Load production profile
        >>> prod_config = get_config(profile="production")  # doctest: +SKIP

    See Also:
        lib_layered_config.read_config: Underlying configuration loader.
    """
    return read_config(
        vendor=__init__conf__.LAYEREDCONF_VENDOR,
        app=__init__conf__.LAYEREDCONF_APP,
        slug=__init__conf__.LAYEREDCONF_SLUG,
        profile=profile,
        default_file=get_default_config_path(),
        start_dir=start_dir,
    )


__all__ = [
    "get_config",
    "get_default_config_path",
]
