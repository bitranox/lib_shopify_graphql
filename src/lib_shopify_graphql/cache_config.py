"""Typed configuration sections for the token cache, the SKU cache and the shared MySQL connection.

Lives outside the CLI so the composition root can validate the same sections the CLI reads: a
value from lib_layered_config is checked once, at the boundary, and the rest of the code reads
typed fields.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["CacheBackendConfig", "MySQLConfig", "SKUCacheConfig", "TokenCacheConfig"]


class CacheBackendConfig(BaseModel):
    """The settings every cache section shares: which backend, and where it keeps its data.

    ``mysql_table`` has no default here because each cache names its own table.
    """

    # lib_layered_config reads an unquoted all-digit value as an int, and a str field refuses an int.
    # The conversion is lossless, so turning it back into text restores what the operator wrote.
    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    backend: str = "json"
    json_path: str = ""
    mysql_connection: str = ""
    mysql_table: str = ""


class TokenCacheConfig(CacheBackendConfig):
    """Typed configuration for token cache settings.

    Validates and provides typed access to token cache configuration
    from lib_layered_config.
    """

    enabled: bool = False
    mysql_table: str = "token_cache"


class SKUCacheConfig(CacheBackendConfig):
    """Typed configuration for SKU cache settings.

    Validates and provides typed access to SKU cache configuration
    from lib_layered_config.
    """

    enabled: bool = True
    mysql_table: str = "sku_cache"


class MySQLConfig(BaseModel):
    """Typed configuration for shared MySQL settings.

    Validates and provides typed access to [shopify.mysql] configuration.
    Used when individual MySQL parameters are preferred over a connection string.
    """

    # lib_layered_config reads an unquoted all-digit value as an int, and a str field refuses an int.
    # The conversion is lossless, so turning it back into text restores what the operator wrote.
    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

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
