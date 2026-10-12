"""Composition root for wiring adapters to ports.

This module provides factory functions for creating configured
instances with production adapters. For testing, inject fake
implementations of the ports directly.

Usage:
    # Production usage (uses defaults from composition)
    from lib_shopify_graphql import login
    session = login(credentials)

    # Custom adapter injection (testing/customization)
    from lib_shopify_graphql import login
    from lib_shopify_graphql.composition import create_adapters

    adapters = create_adapters()  # or provide custom implementations
    session = login(credentials, **adapters)

    # With SKU caching
    from lib_shopify_graphql.composition import create_sku_resolver
    from pathlib import Path

    sku_resolver = create_sku_resolver(cache_path=Path("/tmp/sku_cache.json"))
    update_variant(session, "ABC-123", update, sku_resolver=sku_resolver)

    # Auto-resolved from config (when caches are enabled)
    # Functions automatically use caches if enabled in config
    update_variant(session, "ABC-123", update)  # Auto-uses SKU cache if enabled
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from .adapters import (
    PYMYSQL_AVAILABLE,
    CachedSKUResolver,
    CachedTokenProvider,
    JsonFileCacheAdapter,
    LocationResolver,
    MySQLCacheAdapter,
    ShopifyGraphQLClient,
    ShopifySessionManager,
    ShopifyTokenProvider,
    get_default_sku_cache_path,
    get_default_token_cache_path,
)
from .adapters.constants import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_SKU_CACHE_TTL_SECONDS,
    DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS,
)
from .cache_config import CacheBackendConfig, MySQLConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from .application.ports import (
        CachePort,
        GraphQLClientPort,
        LocationResolverPort,
        SessionManagerPort,
        SKUResolverPort,
        TokenProviderPort,
    )

logger = logging.getLogger(__name__)


class AdapterBundle(TypedDict):
    """Bundle of adapter instances for dependency injection."""

    token_provider: TokenProviderPort
    session_manager: SessionManagerPort
    graphql_client: GraphQLClientPort


def create_adapters(
    *,
    token_provider: TokenProviderPort | None = None,
    session_manager: SessionManagerPort | None = None,
    graphql_client: GraphQLClientPort | None = None,
) -> AdapterBundle:
    """Create a bundle of adapters for Shopify operations.

    Uses default Shopify SDK adapters unless custom implementations
    are provided. This is the composition root - the place where
    concrete implementations are bound to abstract ports.

    Args:
        token_provider: Custom token provider, or None for default.
        session_manager: Custom session manager, or None for default.
        graphql_client: Custom GraphQL client, or None for default.

    Returns:
        AdapterBundle with all adapters ready for injection.

    Example:
        # Using defaults
        adapters = create_adapters()
        session = login(credentials, **adapters)

        # Using custom token provider for testing
        adapters = create_adapters(token_provider=FakeTokenProvider())
        session = login(credentials, **adapters)
    """
    return AdapterBundle(
        token_provider=token_provider or ShopifyTokenProvider(),
        session_manager=session_manager or ShopifySessionManager(),
        graphql_client=graphql_client or ShopifyGraphQLClient(),
    )


# Singleton default adapters for convenience
_default_adapters: AdapterBundle | None = None


def get_default_adapters() -> AdapterBundle:
    """Get the default adapter bundle (singleton).

    Returns:
        The default AdapterBundle with Shopify SDK implementations.
    """
    global _default_adapters  # noqa: PLW0603 - module-level singleton cache, composition-root pattern
    if _default_adapters is None:
        _default_adapters = create_adapters()
    return _default_adapters


def create_json_cache(
    cache_path: Path,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> CachePort:
    """Create a JSON file cache adapter.

    Args:
        cache_path: Path to the JSON cache file.
        lock_timeout: Maximum seconds to wait for lock.
            Defaults to DEFAULT_LOCK_TIMEOUT_SECONDS.

    Returns:
        CachePort implementation using JSON file storage.

    Example:
        cache = create_json_cache(Path("/tmp/sku_cache.json"))
    """
    return JsonFileCacheAdapter(cache_path, lock_timeout)


def create_sku_resolver(
    *,
    cache: CachePort | None = None,
    cache_path: Path | None = None,
    graphql_client: GraphQLClientPort | None = None,
    cache_ttl: int = DEFAULT_SKU_CACHE_TTL_SECONDS,
) -> SKUResolverPort:
    """Create a cached SKU resolver.

    Args:
        cache: Custom cache implementation.
        cache_path: Path for JSON cache (creates JsonFileCacheAdapter).
        graphql_client: Custom GraphQL client (uses default if None).
        cache_ttl: Cache TTL in seconds. Defaults to DEFAULT_SKU_CACHE_TTL_SECONDS.

    Returns:
        SKUResolverPort implementation with caching.

    Example:
        resolver = create_sku_resolver(cache_path=Path("/tmp/sku_cache.json"))
        gid = resolver.resolve("ABC-123", "mystore.myshopify.com")
    """
    if cache is None:
        if cache_path is None:
            msg = "Either cache or cache_path must be provided"
            raise ValueError(msg)
        cache = JsonFileCacheAdapter(cache_path)

    gc = graphql_client or ShopifyGraphQLClient()
    return CachedSKUResolver(cache, gc, cache_ttl)


def create_location_resolver(
    *,
    graphql_client: GraphQLClientPort | None = None,
    default_location_id: str | None = None,
) -> LocationResolverPort:
    """Create a location resolver with fallback chain.

    Args:
        graphql_client: Custom GraphQL client (uses default if None).
        default_location_id: Default location GID from configuration.

    Returns:
        LocationResolverPort implementation with fallback.

    Example:
        resolver = create_location_resolver(
            default_location_id="gid://shopify/Location/123"
        )
        location_gid = resolver.resolve()
    """
    gc = graphql_client or ShopifyGraphQLClient()
    return LocationResolver(gc, default_location_id)


def create_cached_token_provider(
    *,
    cache: CachePort | None = None,
    cache_path: Path | None = None,
    delegate: TokenProviderPort | None = None,
    refresh_margin: int = DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS,
) -> TokenProviderPort:
    """Create a cached token provider.

    Wraps a token provider with caching to reduce OAuth requests.
    Tokens are cached until near expiration (with safety margin).

    Args:
        cache: Custom cache implementation.
        cache_path: Path for JSON cache (creates JsonFileCacheAdapter).
        delegate: Underlying token provider (uses ShopifyTokenProvider if None).
        refresh_margin: Seconds before expiration to refresh.
            Defaults to DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS.

    Returns:
        TokenProviderPort implementation with caching.

    Raises:
        ValueError: If neither cache nor cache_path is provided.

    Example:
        provider = create_cached_token_provider(
            cache_path=Path("/tmp/token_cache.json")
        )
        adapters = create_adapters(token_provider=provider)
        session = login(credentials, **adapters)
    """
    if cache is None:
        if cache_path is None:
            msg = "Either cache or cache_path must be provided"
            raise ValueError(msg)
        cache = JsonFileCacheAdapter(cache_path)

    tp = delegate or ShopifyTokenProvider()
    return CachedTokenProvider(cache, tp, refresh_margin)


# =============================================================================
# Config-Driven Cache Helpers (Private)
# =============================================================================

# Singleton state for default resolvers/providers
_default_sku_resolver: SKUResolverPort | None = None
_sku_resolver_checked: bool = False
_default_token_provider: TokenProviderPort | None = None
_token_provider_checked: bool = False


@dataclass(frozen=True, slots=True)
class _MySQLCacheSpec:
    """Everything the MySQL cache adapter is built from, already validated and typed.

    ``connection`` is non-empty when a URL was configured; the individual fields are used otherwise.
    """

    table_name: str
    connect_timeout: int
    auto_create_database: bool
    connection: str
    host: str
    port: int
    user: str
    password: str
    database: str


def _mysql_cache_spec(
    cache_section: Mapping[str, Any],
    mysql_section: Mapping[str, Any],
    *,
    default_table: str,
) -> _MySQLCacheSpec | None:
    """Validate the cache and shared MySQL sections and decide how to connect.

    Priority: per-cache connection URL, then the shared URL, then the individual parameters.
    The sections are checked here, at the boundary, so a digit-only password or user that
    lib_layered_config delivered as an int reaches the adapter as text.

    Args:
        cache_section: The ``[shopify.sku_cache]`` or ``[shopify.token_cache]`` section.
        mysql_section: The shared ``[shopify.mysql]`` section.
        default_table: Table name used when the cache section names none.

    Returns:
        The connection spec, or None when neither a URL nor user plus database is configured.

    Raises:
        pydantic.ValidationError: A section holds a value of the wrong type.
    """
    cache = CacheBackendConfig.model_validate({"mysql_table": default_table, **cache_section})
    mysql = MySQLConfig.model_validate(mysql_section)
    connection = cache.mysql_connection or mysql.connection
    if not connection and not (mysql.user and mysql.database):
        return None
    return _MySQLCacheSpec(
        table_name=cache.mysql_table,
        connect_timeout=mysql.connect_timeout,
        auto_create_database=mysql.auto_create_database,
        connection=connection,
        host=mysql.host,
        port=mysql.port,
        user=mysql.user,
        password=mysql.password,
        database=mysql.database,
    )


def _mysql_cache_from_spec(spec: _MySQLCacheSpec) -> MySQLCacheAdapter:
    if spec.connection:
        return MySQLCacheAdapter.from_url(
            spec.connection,
            table_name=spec.table_name,
            connect_timeout=spec.connect_timeout,
            auto_create_database=spec.auto_create_database,
        )
    return MySQLCacheAdapter(
        host=spec.host,
        port=spec.port,
        user=spec.user,
        password=spec.password,
        database=spec.database,
        table_name=spec.table_name,
        connect_timeout=spec.connect_timeout,
        auto_create_database=spec.auto_create_database,
    )


def _create_cache_from_config(
    config: dict[str, Any],
    default_path_func: Callable[[], Path],
    default_table: str,
    cache_type: str,
    mysql_config: dict[str, Any] | None = None,
) -> CachePort | None:
    """Create cache adapter from config dict.

    Args:
        config: Cache configuration dict.
        default_path_func: Function to get default cache path.
        default_table: Default MySQL table name.
        cache_type: Cache type for logging (e.g., "SKU cache", "token cache").
        mysql_config: Optional shared MySQL config (from [shopify.mysql] section).

    Returns:
        CachePort implementation, or None if creation fails.
    """
    backend = config.get("backend", "json")

    if backend == "json":
        json_path = CacheBackendConfig.model_validate(config).json_path
        cache_path = Path(json_path) if json_path else default_path_func()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        return JsonFileCacheAdapter(cache_path)

    if backend == "mysql":
        if not PYMYSQL_AVAILABLE:
            logger.warning("MySQL backend requested but pymysql not installed")
            return None

        spec = _mysql_cache_spec(config, mysql_config or {}, default_table=default_table)
        if spec is not None:
            return _mysql_cache_from_spec(spec)

        logger.warning(
            "MySQL backend requested for %s but not configured. Set shopify.mysql.connection or shopify.mysql.user + shopify.mysql.database", cache_type
        )
        return None

    logger.warning("Unknown %s backend '%s', expected 'json' or 'mysql'", cache_type, backend)
    return None


def _create_sku_cache_from_config(
    config: dict[str, Any],
    mysql_config: dict[str, Any] | None = None,
) -> CachePort | None:
    """Create SKU cache from config dict."""
    return _create_cache_from_config(config, get_default_sku_cache_path, "sku_cache", "SKU cache", mysql_config)


def _create_token_cache_from_config(
    config: dict[str, Any],
    mysql_config: dict[str, Any] | None = None,
) -> CachePort | None:
    """Create token cache from config dict."""
    return _create_cache_from_config(config, get_default_token_cache_path, "token_cache", "token cache", mysql_config)


# =============================================================================
# Config-Driven Default Resolvers/Providers (Public)
# =============================================================================


def get_default_sku_resolver(
    graphql_client: GraphQLClientPort | None = None,
) -> SKUResolverPort | None:
    """Get the default SKU resolver from configuration (singleton).

    Returns None if SKU cache is not enabled in config.
    Logs INFO recommendation if cache is disabled.

    Args:
        graphql_client: GraphQL client to use. If None, uses default.

    Returns:
        SKUResolverPort if cache is enabled and configured, None otherwise.

    Example:
        resolver = get_default_sku_resolver()
        if resolver:
            gid = resolver.resolve("ABC-123", "mystore.myshopify.com")
    """
    global _default_sku_resolver, _sku_resolver_checked  # noqa: PLW0603 - module-level singleton cache, composition-root pattern

    if _sku_resolver_checked:
        return _default_sku_resolver

    _sku_resolver_checked = True

    try:
        # Late import: re-read on each call so tests can monkeypatch config.get_config
        from .config import get_config  # noqa: PLC0415 - see comment above

        config = get_config()
        shopify_config = config.get("shopify", {})
        sku_cache_config = shopify_config.get("sku_cache", {})
        mysql_config = shopify_config.get("mysql", {})

        if not sku_cache_config.get("enabled", False):
            logger.info("SKU cache is disabled. Enable [shopify.sku_cache] in config for faster SKU lookups and cache invalidation on delete.")
            return None

        cache = _create_sku_cache_from_config(sku_cache_config, mysql_config)
        if cache is None:
            return None

        gc = graphql_client
        if gc is None:
            adapters = get_default_adapters()
            gc = adapters["graphql_client"]

        cache_ttl = sku_cache_config.get("cache_ttl", DEFAULT_SKU_CACHE_TTL_SECONDS)
        _default_sku_resolver = CachedSKUResolver(cache, gc, cache_ttl)
        logger.info("SKU cache enabled, using auto-resolved SKU resolver")
        return _default_sku_resolver

    except Exception as exc:
        logger.warning("Failed to create default SKU resolver: %s", exc)
        return None


def get_default_token_provider() -> TokenProviderPort:
    """Get the default token provider from configuration (singleton).

    Returns CachedTokenProvider if token cache is enabled, otherwise base provider.
    Logs INFO recommendation if cache is disabled.

    Returns:
        TokenProviderPort - cached if enabled, base provider otherwise.

    Example:
        provider = get_default_token_provider()
        token, expires = provider.obtain_token(shop_url, client_id, client_secret)
    """
    global _default_token_provider, _token_provider_checked  # noqa: PLW0603 - module-level singleton cache, composition-root pattern

    if _token_provider_checked and _default_token_provider is not None:
        return _default_token_provider

    _token_provider_checked = True
    base_provider = ShopifyTokenProvider()

    try:
        # Late import: re-read on each call so tests can monkeypatch config.get_config
        from .config import get_config  # noqa: PLC0415 - see comment above

        config = get_config()
        shopify_config = config.get("shopify", {})
        token_cache_config = shopify_config.get("token_cache", {})
        mysql_config = shopify_config.get("mysql", {})

        if not token_cache_config.get("enabled", False):
            logger.info("Token cache is disabled. Enable [shopify.token_cache] in config to reduce OAuth handshakes and improve login performance.")
            _default_token_provider = base_provider
            return base_provider

        cache = _create_token_cache_from_config(token_cache_config, mysql_config)
        if cache is None:
            _default_token_provider = base_provider
            return base_provider

        refresh_margin = token_cache_config.get("refresh_margin", DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS)
        _default_token_provider = CachedTokenProvider(cache, base_provider, refresh_margin)
        logger.info("Token cache enabled, using auto-resolved cached token provider")
        return _default_token_provider

    except Exception as exc:
        logger.warning("Failed to create cached token provider: %s", exc)
        _default_token_provider = base_provider
        return base_provider


def reset_default_resolvers() -> None:
    """Reset the singleton default resolvers/providers.

    Call this to force re-reading configuration on next access.
    Useful after configuration changes or in tests.
    """
    global _default_sku_resolver, _sku_resolver_checked  # noqa: PLW0603 - module-level singleton cache, composition-root pattern
    global _default_token_provider, _token_provider_checked  # noqa: PLW0603 - module-level singleton cache, composition-root pattern
    _default_sku_resolver = None
    _sku_resolver_checked = False
    _default_token_provider = None
    _token_provider_checked = False


__all__ = [
    "AdapterBundle",
    "create_adapters",
    "create_cached_token_provider",
    "create_json_cache",
    "create_location_resolver",
    "create_sku_resolver",
    "get_default_adapters",
    "get_default_sku_resolver",
    "get_default_token_provider",
    "reset_default_resolvers",
]
