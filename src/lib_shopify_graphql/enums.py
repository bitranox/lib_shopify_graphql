"""Configuration and infrastructure enums (CLI, caching, deployment).

This module contains enums for application configuration and infrastructure:
    - :class:`OutputFormat`: Output format options (human-readable vs JSON).
    - :class:`DeployTarget`: Configuration deployment target layers.
    - :class:`CacheBackend`: Cache storage backend types.

Note:
    This module is SEPARATE from ``models/_enums.py`` which contains
    **Shopify domain enums** (ProductStatus, InventoryPolicy, MetafieldType, etc.).

    Use this module for configuration/infrastructure concerns.
    Use ``models._enums`` (or import from ``models``) for Shopify API types.
"""

from __future__ import annotations

from ._compat import StrEnum


class OutputFormat(StrEnum):
    """Output format options for configuration display.

    Determines how configuration data is rendered to the user.

    Attributes:
        HUMAN: Human-readable TOML-like format for interactive use.
        JSON: Machine-readable JSON format for scripting and automation.
    """

    HUMAN = "human"
    JSON = "json"


class DeployTarget(StrEnum):
    """Configuration deployment target layers.

    Specifies where configuration files should be deployed in the
    platform-specific directory hierarchy.

    Attributes:
        APP: System-wide application config (requires elevated privileges).
        HOST: System-wide host-specific config (requires elevated privileges).
        USER: User-specific config in the current user's home directory.
    """

    APP = "app"
    HOST = "host"
    USER = "user"


class CacheBackend(StrEnum):
    """Cache storage backend types.

    Specifies the storage backend for token and SKU caching.

    Attributes:
        JSON: JSON file-based cache storage.
        MYSQL: MySQL database cache storage.
    """

    JSON = "json"
    MYSQL = "mysql"


__all__ = [
    "CacheBackend",
    "DeployTarget",
    "OutputFormat",
]
