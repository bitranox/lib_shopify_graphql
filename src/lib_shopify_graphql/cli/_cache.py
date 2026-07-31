"""Cache management CLI commands.

This module provides CLI commands for managing token and SKU caches:
- tokencache-clear: Clear OAuth token cache
- skucache-clear: Clear SKU-to-GID mapping cache
- cache-clear-all: Clear all caches
- skucache-rebuild: Rebuild SKU cache from Shopify
- skucache-check: Check cache consistency
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import lib_log_rich.runtime
import rich_click as click

from .. import safe_console
from ..adapters import (
    CachedSKUResolver,
    JsonFileCacheAdapter,
    MySQLCacheAdapter,
    get_default_sku_cache_path,
    get_default_token_cache_path,
)
from ..enums import CacheBackend
from ..exceptions import AuthenticationError, GraphQLError
from ..shopify_client import (
    cache_clear_all,
    skucache_check,
    skucache_clear,
    skucache_rebuild,
    tokencache_clear,
)
from ._common import (
    CLICK_CONTEXT_SETTINGS,
    MySQLConfig,
    SKUCacheConfig,
    TokenCacheConfig,
    exit_sku_cache_not_configured,
    get_effective_config_and_profile,
    shopify_session,
)
from .typed_click import option

if TYPE_CHECKING:
    from lib_layered_config import Config

    from ..application.ports import CachePort

logger = logging.getLogger(__name__)

#: Maximum number of mismatched cache entries to print in detail before summarizing the rest.
_MISMATCH_DISPLAY_LIMIT = 10


# =============================================================================
# Cache Creation Helpers
# =============================================================================


def create_mysql_cache_adapter(
    config: Config,
    *,
    cache_connection: str,
    table_name: str,
) -> MySQLCacheAdapter | None:
    """Create MySQL cache adapter from configuration.

    Supports two configuration methods:
    1. Connection string (takes precedence): mysql://user:password@host:port/database
    2. Individual parameters: host, port, user, password, database

    Args:
        config: Loaded layered configuration.
        cache_connection: Per-cache connection string (from token_cache or sku_cache section).
        table_name: Name of the cache table.

    Returns:
        MySQLCacheAdapter instance or None if MySQL is not configured.
    """
    # Late import to allow tests to patch cli.PYMYSQL_AVAILABLE
    from . import PYMYSQL_AVAILABLE  # noqa: PLC0415 - re-read on each call so monkeypatching cli.PYMYSQL_AVAILABLE takes effect

    if not PYMYSQL_AVAILABLE:
        logger.warning("MySQL backend requested but pymysql is not installed")
        return None

    # Load shared MySQL configuration
    raw_mysql_cfg = config.get("shopify.mysql", default={})
    mysql_cfg = MySQLConfig.model_validate(raw_mysql_cfg)

    # Priority: per-cache connection > shared connection > individual params
    connection = cache_connection or mysql_cfg.connection

    if connection:
        # Use connection string
        return MySQLCacheAdapter.from_url(
            connection,
            table_name=table_name,
            connect_timeout=mysql_cfg.connect_timeout,
            auto_create_database=mysql_cfg.auto_create_database,
        )

    # Check if individual parameters are configured
    if mysql_cfg.user and mysql_cfg.database:
        # Use individual parameters
        return MySQLCacheAdapter(
            host=mysql_cfg.host,
            port=mysql_cfg.port,
            user=mysql_cfg.user,
            password=mysql_cfg.password,
            database=mysql_cfg.database,
            table_name=table_name,
            connect_timeout=mysql_cfg.connect_timeout,
            auto_create_database=mysql_cfg.auto_create_database,
        )

    # No MySQL configuration available
    logger.warning("MySQL backend requested but not configured. Set shopify.mysql.connection or shopify.mysql.user + shopify.mysql.database")
    return None


def create_token_cache_from_config(config: Config) -> CachePort | None:
    """Create token cache adapter from config settings.

    Args:
        config: Loaded layered configuration.

    Returns:
        CachePort instance or None if token caching is not configured.
    """
    raw_cfg = config.get("shopify.token_cache", default={})
    cfg = TokenCacheConfig.model_validate(raw_cfg)

    if not cfg.enabled:
        return None

    backend = CacheBackend(cfg.backend)

    if backend == CacheBackend.JSON:
        # Use default path if not specified
        cache_path = Path(cfg.json_path) if cfg.json_path else get_default_token_cache_path()
        return JsonFileCacheAdapter(cache_path)

    if backend == CacheBackend.MYSQL:
        return create_mysql_cache_adapter(
            config,
            cache_connection=cfg.mysql_connection,
            table_name=cfg.mysql_table,
        )

    return None


def create_sku_cache_from_config(config: Config) -> CachePort | None:
    """Create SKU cache adapter from config settings.

    Args:
        config: Loaded layered configuration.

    Returns:
        CachePort instance or None if SKU caching is not configured.
    """
    raw_cfg = config.get("shopify.sku_cache", default={})
    cfg = SKUCacheConfig.model_validate(raw_cfg)

    if not cfg.enabled:
        return None

    backend = CacheBackend(cfg.backend)

    if backend == CacheBackend.JSON:
        # Use default path if not specified
        cache_path = Path(cfg.json_path) if cfg.json_path else get_default_sku_cache_path()
        return JsonFileCacheAdapter(cache_path)

    if backend == CacheBackend.MYSQL:
        return create_mysql_cache_adapter(
            config,
            cache_connection=cfg.mysql_connection,
            table_name=cfg.mysql_table,
        )

    return None


# =============================================================================
# SKU Cache Check Display Helpers
# =============================================================================


def _display_skucache_summary(result: Any, shop_url: str) -> None:
    """Display SKU cache check summary."""
    safe_console.echo("")
    safe_console.echo("SKU Cache Consistency Check")
    safe_console.echo("━" * 30)
    safe_console.echo(f"Shop: {shop_url}")
    safe_console.echo("")
    safe_console.echo(f"Cached entries:  {result.total_cached}")
    safe_console.echo(f"Shopify entries: {result.total_shopify}")
    safe_console.echo("")
    safe_console.echo("Summary:")
    safe_console.echo(f"  ✓ Valid:      {result.valid}")
    safe_console.echo(f"  ⚠ Stale:      {len(result.stale)}  (in cache but not in Shopify)")
    safe_console.echo(f"  ⚠ Missing:    {len(result.missing)}  (in Shopify but not in cache)")
    safe_console.echo(f"  ✗ Mismatched: {len(result.mismatched)}")


def _display_list_with_limit(items: tuple[str, ...] | list[str], limit: int, prefix: str = "") -> None:
    """Display a list with truncation after limit items."""
    for item in items[:limit]:
        safe_console.echo(f"{prefix}{item}")
    if len(items) > limit:
        safe_console.echo(f"  ... and {len(items) - limit} more")


def _display_skucache_details(result: Any) -> None:
    """Display detailed SKU cache inconsistencies."""
    if result.stale:
        safe_console.echo("")
        safe_console.echo("Stale entries (cached but no longer in Shopify):")
        _display_list_with_limit(result.stale, limit=20, prefix="  • ")

    if result.missing:
        safe_console.echo("")
        safe_console.echo("Missing entries (in Shopify but not cached):")
        _display_list_with_limit(result.missing, limit=20, prefix="  • ")

    if result.mismatched:
        safe_console.echo("")
        safe_console.echo("Mismatched entries (different GIDs):")
        for mismatch in result.mismatched[:_MISMATCH_DISPLAY_LIMIT]:
            safe_console.echo(f"  • {mismatch.sku}")
            safe_console.echo(f"      Cached:  {mismatch.cached_variant_gid}")
            safe_console.echo(f"      Actual:  {mismatch.actual_variant_gid}")
        if len(result.mismatched) > _MISMATCH_DISPLAY_LIMIT:
            safe_console.echo(f"  ... and {len(result.mismatched) - _MISMATCH_DISPLAY_LIMIT} more")


# =============================================================================
# CLI Commands
# =============================================================================


def register_cache_commands(
    cli_group: click.Group,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Register cache management commands on the CLI group.

    Args:
        cli_group: The Click group to register commands on.
        get_credentials_or_exit: Function to get credentials from config.
        get_fix_suggestion: Function to get fix suggestions for errors.
    """

    @cli_group.command("tokencache-clear", context_settings=CLICK_CONTEXT_SETTINGS)
    @option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command (e.g., 'production', 'test')",
    )
    @click.pass_context
    def cli_tokencache_clear(ctx: click.Context, profile: str | None) -> None:
        r"""Clear cached OAuth access tokens.

        Forces re-authentication on next login. Use this command after
        rotating client credentials or to troubleshoot authentication issues.

        Token caching must be enabled in configuration:

        \b
        [shopify.token_cache]
        enabled = true
        backend = "json"
        json_path = "/path/to/token_cache.json"

        Examples:
            \b
            # Clear token cache for default profile
            $ lib-shopify-graphql tokencache-clear

            \b
            # Clear token cache for production profile
            $ lib-shopify-graphql tokencache-clear --profile production
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "tokencache-clear", "profile": effective_profile}

        with lib_log_rich.runtime.bind(job_id="cli-tokencache-clear", extra=extra):
            cache = create_token_cache_from_config(config)
            if cache is None:
                safe_console.echo("Token caching is not configured.", err=True)
                safe_console.echo("Enable it in your config:", err=True)
                safe_console.echo("  [shopify.token_cache]", err=True)
                safe_console.echo("  enabled = true", err=True)
                safe_console.echo('  json_path = "/path/to/token_cache.json"', err=True)
                raise SystemExit(0)

            logger.info("Clearing token cache for profile '%s'", effective_profile)
            try:
                tokencache_clear(cache)
                safe_console.echo("✓ Token cache cleared.")
            except Exception as exc:
                safe_console.echo(f"Error clearing token cache: {exc}", err=True)
                logger.error("Failed to clear token cache: %s", exc)
                raise SystemExit(1) from exc

    @cli_group.command("skucache-clear", context_settings=CLICK_CONTEXT_SETTINGS)
    @option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command (e.g., 'production', 'test')",
    )
    @click.pass_context
    def cli_skucache_clear(ctx: click.Context, profile: str | None) -> None:
        r"""Clear cached SKU-to-GID mappings.

        Forces fresh lookups from Shopify. Use this command when:

        \b
        - SKUs have been reassigned to different variants
        - Products have been deleted and recreated
        - Bulk import changed variant GIDs
        - SKU lookups return incorrect variants

        SKU caching must be configured:

        \b
        [shopify.sku_cache]
        backend = "json"
        json_path = "/path/to/sku_cache.json"

        Examples:
            \b
            # Clear SKU cache for default profile
            $ lib-shopify-graphql skucache-clear

            \b
            # Clear SKU cache for production profile
            $ lib-shopify-graphql skucache-clear --profile production
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "skucache-clear", "profile": effective_profile}

        with lib_log_rich.runtime.bind(job_id="cli-skucache-clear", extra=extra):
            cache = create_sku_cache_from_config(config)
            if cache is None:
                safe_console.echo("SKU caching is not configured.", err=True)
                safe_console.echo("Enable it in your config:", err=True)
                safe_console.echo("  [shopify.sku_cache]", err=True)
                safe_console.echo('  json_path = "/path/to/sku_cache.json"', err=True)
                raise SystemExit(0)

            logger.info("Clearing SKU cache for profile '%s'", effective_profile)
            try:
                skucache_clear(cache)
                safe_console.echo("✓ SKU cache cleared.")
            except Exception as exc:
                safe_console.echo(f"Error clearing SKU cache: {exc}", err=True)
                logger.error("Failed to clear SKU cache: %s", exc)
                raise SystemExit(1) from exc

    @cli_group.command("cache-clear-all", context_settings=CLICK_CONTEXT_SETTINGS)
    @option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command (e.g., 'production', 'test')",
    )
    @click.pass_context
    def cli_cache_clear_all(ctx: click.Context, profile: str | None) -> None:
        r"""Clear all caches (tokens and SKU mappings).

        Clears both the token cache and SKU cache in one operation.
        Only configured caches are cleared.

        Examples:
            \b
            # Clear all caches for default profile
            $ lib-shopify-graphql cache-clear-all

            \b
            # Clear all caches for production profile
            $ lib-shopify-graphql cache-clear-all --profile production
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "cache-clear-all", "profile": effective_profile}

        with lib_log_rich.runtime.bind(job_id="cli-cache-clear-all", extra=extra):
            token_cache = create_token_cache_from_config(config)
            sku_cache = create_sku_cache_from_config(config)

            if token_cache is None and sku_cache is None:
                safe_console.echo("No caches are configured.", err=True)
                safe_console.echo("Configure caching in your config file.", err=True)
                raise SystemExit(0)

            logger.info("Clearing all caches for profile '%s'", effective_profile)
            try:
                cache_clear_all(token_cache, sku_cache)

                cleared: list[str] = []
                if token_cache is not None:
                    cleared.append("tokens")
                if sku_cache is not None:
                    cleared.append("SKU mappings")

                safe_console.echo(f"✓ Cleared: {', '.join(cleared)}.")
            except Exception as exc:
                safe_console.echo(f"Error clearing caches: {exc}", err=True)
                logger.error("Failed to clear caches: %s", exc)
                raise SystemExit(1) from exc

    @cli_group.command("skucache-rebuild", context_settings=CLICK_CONTEXT_SETTINGS)
    @option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command (e.g., 'production', 'test')",
    )
    @option(
        "--query",
        type=str,
        default=None,
        help="Shopify query filter (e.g., 'status:active')",
    )
    @click.pass_context
    def cli_skucache_rebuild(ctx: click.Context, profile: str | None, query: str | None) -> None:
        """Rebuild SKU cache by reading all products from Shopify.

        Connects to Shopify, iterates through all products, and updates the
        SKU cache with fresh SKU-to-GID mappings. Use this to rebuild cache
        after bulk imports, verify cache consistency, or pre-populate for
        faster lookups.

        Requires credentials and SKU cache configured in config file.
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "skucache-rebuild", "profile": effective_profile, "query": query}

        with lib_log_rich.runtime.bind(job_id="cli-skucache-rebuild", extra=extra):
            # Check SKU cache is configured
            sku_cache = create_sku_cache_from_config(config)
            if sku_cache is None:
                safe_console.echo("SKU caching is not configured.", err=True)
                safe_console.echo("Enable it in your config:", err=True)
                safe_console.echo("  [shopify.sku_cache]", err=True)
                safe_console.echo('  json_path = "/path/to/sku_cache.json"', err=True)
                raise SystemExit(1)

            # Extract credentials
            credentials = get_credentials_or_exit(config)

            # Login and rebuild
            safe_console.echo(f"Connecting to {credentials.shop_url}...")
            try:
                with shopify_session(credentials) as session:
                    safe_console.echo("✓ Connected")

                    # Create SKU resolver with the cache
                    sku_resolver = CachedSKUResolver(sku_cache, session._graphql_client)

                    safe_console.echo("Rebuilding SKU cache (this may take a while)...")
                    if query:
                        safe_console.echo(f"  Filter: {query}")

                    total_variants = skucache_rebuild(
                        session,
                        sku_resolver=sku_resolver,
                        query=query,
                    )

                    safe_console.echo(f"✓ Cache rebuilt: {total_variants} variants cached")
                    logger.info("Cache rebuild complete: %s variants cached", total_variants)

            except (AuthenticationError, GraphQLError) as exc:
                safe_console.echo(f"\n✗ Error: {exc}", err=True)
                safe_console.echo(get_fix_suggestion(exc, credentials), err=True)
                raise SystemExit(1) from exc

    @cli_group.command("skucache-check", context_settings=CLICK_CONTEXT_SETTINGS)
    @option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command (e.g., 'production', 'test')",
    )
    @option(
        "--query",
        type=str,
        default=None,
        help="Shopify query filter (e.g., 'status:active')",
    )
    @click.pass_context
    def cli_skucache_check(ctx: click.Context, profile: str | None, query: str | None) -> None:
        """Check SKU cache consistency against Shopify.

        Connects to Shopify, rebuilds the cache into a temporary file, and compares
        it with the actual cache to detect inconsistencies.

        Reports three types of issues:
        - Stale: SKUs in cache but not in Shopify (deleted products/variants)
        - Missing: SKUs in Shopify but not in cache
        - Mismatched: SKUs with different GIDs between cache and Shopify

        Requires credentials and SKU cache configured in config file.
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "skucache-check", "profile": effective_profile, "query": query}

        with lib_log_rich.runtime.bind(job_id="cli-skucache-check", extra=extra):
            sku_cache = create_sku_cache_from_config(config)
            if sku_cache is None:
                exit_sku_cache_not_configured()

            credentials = get_credentials_or_exit(config)

            safe_console.echo(f"Connecting to {credentials.shop_url}...")
            try:
                with shopify_session(credentials) as session:
                    safe_console.echo("✓ Connected")

                    safe_console.echo("Checking SKU cache consistency (this may take a while)...")
                    if query:
                        safe_console.echo(f"  Filter: {query}")

                    result = skucache_check(session, sku_cache, query=query)

                    _display_skucache_summary(result, credentials.shop_url)
                    _display_skucache_details(result)

                    safe_console.echo("")
                    if result.is_consistent:
                        safe_console.echo("✓ Cache is consistent with Shopify")
                    else:
                        safe_console.echo("✗ Cache has inconsistencies - consider running 'skucache-rebuild'")

                    logger.info(
                        "Cache check complete: %s valid, %s stale, %s missing, %s mismatched",
                        result.valid,
                        len(result.stale),
                        len(result.missing),
                        len(result.mismatched),
                    )

                    if not result.is_consistent:
                        raise SystemExit(1)

            except (AuthenticationError, GraphQLError) as exc:
                safe_console.echo(f"\n✗ Error: {exc}", err=True)
                safe_console.echo(get_fix_suggestion(exc, credentials), err=True)
                raise SystemExit(1) from exc


__all__ = [
    "create_mysql_cache_adapter",
    "create_sku_cache_from_config",
    "create_token_cache_from_config",
    "register_cache_commands",
]
