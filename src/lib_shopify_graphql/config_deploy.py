"""Configuration deployment functionality for CLI config-deploy command.

Provides the business logic for deploying default configuration to application,
host, or user configuration locations. Uses lib_layered_config's deploy_config
function to copy the bundled defaultconfig.toml to requested target layers.

This module contains:
    - :func:`deploy_configuration`: deploys configuration to specified targets.

Note:
    Lives in the behaviors layer. The CLI command delegates to this module for
    all configuration deployment logic, keeping the CLI layer focused on argument
    parsing and user interaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from lib_layered_config import deploy_config

from . import __init__conf__
from .config import get_default_config_path
from .enums import DeployTarget


def deploy_configuration(
    *,
    targets: Sequence[DeployTarget],
    force: bool = False,
    profile: str | None = None,
) -> list[Path]:
    r"""Deploy default configuration to specified target layers.

    Uses lib_layered_config.deploy_config() to copy the bundled
    defaultconfig.toml to requested target layers (app, host, user).
    Returns the list of created configuration file paths.

    Args:
        targets: Sequence of DeployTarget enum values specifying target layers.
            Valid values: DeployTarget.APP, DeployTarget.HOST, DeployTarget.USER.
            Multiple targets can be specified to deploy to several locations at once.
        force: If True, overwrite existing configuration files. If False
            (default), skip files that already exist.
        profile: Optional profile name for environment isolation. When specified,
            configuration is deployed to profile-specific subdirectories
            (e.g., ~/.config/slug/profile/<name>/config.toml).

    Returns:
        List of paths where configuration files were created or would be
        created. Empty list if all target files already exist and force=False.

    Raises:
        PermissionError: When deploying to app/host without sufficient
            privileges.
        ValueError: When invalid target names are provided.

    Note:
        Creates configuration files in platform-specific directories:
            - app: System-wide application config (requires privileges)
            - host: System-wide host config (requires privileges)
            - user: User-specific config (current user's home directory)

        Platform-specific paths (without profile):
            - Linux (app): /etc/xdg/{slug}/config.toml
            - Linux (host): /etc/xdg/{slug}/config.toml
            - Linux (user): ~/.config/{slug}/config.toml
            - macOS (app): /Library/Application Support/{vendor}/{app}/config.toml
            - macOS (user): ~/Library/Application Support/{vendor}/{app}/config.toml
            - Windows (app): C:\\ProgramData\\{vendor}\\{app}\\config.toml
            - Windows (user): %APPDATA%\\{vendor}\\{app}\\config.toml

        Platform-specific paths (with profile='production'):
            - Linux (user): ~/.config/{slug}/profile/production/config.toml
            - etc.

    Example:
        >>> paths = deploy_configuration(targets=[DeployTarget.USER])  # doctest: +SKIP
        >>> len(paths) > 0  # doctest: +SKIP
        True
        >>> paths[0].exists()  # doctest: +SKIP
        True

        >>> # Deploy to production profile
        >>> paths = deploy_configuration(  # doctest: +SKIP
        ...     targets=[DeployTarget.USER],
        ...     profile="production"
        ... )
    """
    source = get_default_config_path()

    # Convert enum values to strings for lib_layered_config
    target_strings = [t.value for t in targets]

    deploy_results = deploy_config(
        source=source,
        vendor=__init__conf__.LAYEREDCONF_VENDOR,
        app=__init__conf__.LAYEREDCONF_APP,
        slug=__init__conf__.LAYEREDCONF_SLUG,
        profile=profile,
        targets=target_strings,
        force=force,
    )

    # Extract destination paths from deploy results
    return [result.destination for result in deploy_results]


__all__ = [
    "deploy_configuration",
]
