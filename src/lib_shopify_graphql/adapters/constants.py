"""Default constants for adapters.

This module centralizes all magic numbers and default values used
by cache adapters, token providers, and resolvers.

All values can be overridden via configuration (see defaultconfig.toml).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# =============================================================================
# Time Constants (in seconds)
# =============================================================================

#: Default token refresh margin - refresh this many seconds before expiration
#: This ensures tokens are refreshed before they expire, avoiding authentication failures
DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS: int = 300  # 5 minutes

#: Default token expiration if Shopify doesn't return expires_in
#: Shopify tokens are typically valid for 24 hours
DEFAULT_TOKEN_EXPIRES_IN_SECONDS: int = 86400  # 24 hours

#: Default SKU cache TTL - how long to cache SKU-to-GID mappings
#: SKU mappings rarely change, so a 30-day default is reasonable
DEFAULT_SKU_CACHE_TTL_SECONDS: int = 2592000  # 30 days

# =============================================================================
# Lock/Timeout Constants (in seconds)
# =============================================================================

#: Default filelock timeout for JSON cache operations
#: Increase for slow network shares
DEFAULT_LOCK_TIMEOUT_SECONDS: float = 10.0

#: Default retry count for cache lock acquisition
#: Used by JSON cache when lock times out
DEFAULT_CACHE_RETRY_COUNT: int = 3

#: Default MySQL connection timeout
DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS: int = 10

#: Default GraphQL request timeout
#: Set to 30 seconds as a balance between allowing complex queries
#: and preventing indefinite hangs
DEFAULT_GRAPHQL_TIMEOUT_SECONDS: float = 30.0

# =============================================================================
# Network Constants
# =============================================================================

#: Default MySQL port
DEFAULT_MYSQL_PORT: int = 3306

# =============================================================================
# Cache Table Names
# =============================================================================

#: Default table name for token cache in MySQL
DEFAULT_TOKEN_CACHE_TABLE: str = "token_cache"

#: Default table name for SKU cache in MySQL
DEFAULT_SKU_CACHE_TABLE: str = "sku_cache"

# =============================================================================
# Currency Constants
# =============================================================================

#: Default currency code (ISO 4217)
#: Used when currency is not specified in operations
DEFAULT_CURRENCY_CODE: str = "USD"

# =============================================================================
# Cache Path Constants
# =============================================================================

#: Application name for cache directory
CACHE_APP_NAME: str = "lib-shopify-graphql"


def get_default_cache_dir() -> Path:
    """Get the default cache directory for the current platform.

    Returns OS-appropriate cache directory following platform conventions:
        - Linux: ~/.cache/lib-shopify-graphql/
        - macOS: ~/Library/Caches/lib-shopify-graphql/
        - Windows: %LOCALAPPDATA%\\lib-shopify-graphql\\

    Returns:
        Path to the default cache directory.
    """
    import sys
    from pathlib import Path

    if sys.platform == "darwin":
        # macOS: ~/Library/Caches/lib-shopify-graphql/
        return Path.home() / "Library" / "Caches" / CACHE_APP_NAME
    elif sys.platform == "win32":
        # Windows: %LOCALAPPDATA%\lib-shopify-graphql\
        import os

        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            return Path(local_app_data) / CACHE_APP_NAME
        # Fallback if LOCALAPPDATA not set
        return Path.home() / "AppData" / "Local" / CACHE_APP_NAME
    else:
        # Linux/Unix: ~/.cache/lib-shopify-graphql/ (XDG spec)
        import os

        xdg_cache = os.environ.get("XDG_CACHE_HOME", "")
        if xdg_cache:
            return Path(xdg_cache) / CACHE_APP_NAME
        return Path.home() / ".cache" / CACHE_APP_NAME


def get_default_token_cache_path() -> Path:
    """Get the default path for token cache file.

    Returns:
        Path to the default token cache JSON file.
    """
    return get_default_cache_dir() / "token_cache.json"


def get_default_sku_cache_path() -> Path:
    """Get the default path for SKU cache file.

    Returns:
        Path to the default SKU cache JSON file.
    """
    return get_default_cache_dir() / "sku_cache.json"


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Time constants
    "DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS",
    "DEFAULT_TOKEN_EXPIRES_IN_SECONDS",
    "DEFAULT_SKU_CACHE_TTL_SECONDS",
    # Lock/timeout constants
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_CACHE_RETRY_COUNT",
    "DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS",
    "DEFAULT_GRAPHQL_TIMEOUT_SECONDS",
    # Network constants
    "DEFAULT_MYSQL_PORT",
    # Cache table names
    "DEFAULT_TOKEN_CACHE_TABLE",
    "DEFAULT_SKU_CACHE_TABLE",
    # Currency
    "DEFAULT_CURRENCY_CODE",
    # Cache paths
    "CACHE_APP_NAME",
    "get_default_cache_dir",
    "get_default_token_cache_path",
    "get_default_sku_cache_path",
]
