"""Cache management operations for Shopify API.

This module provides functions to clear token and SKU caches,
and to check cache consistency against Shopify.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..application.ports import CachePort
    from ._session import ShopifySession

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CacheMismatch:
    """A cache entry that differs from Shopify.

    Indicates that a SKU exists in both the cache and Shopify,
    but the cached variant or product GID differs from the actual data.

    Attributes:
        sku: The SKU that has mismatched data.
        cached_variant_gid: Variant GID stored in cache.
        actual_variant_gid: Variant GID from Shopify.
        cached_product_gid: Product GID stored in cache.
        actual_product_gid: Product GID from Shopify.
    """

    sku: str
    cached_variant_gid: str
    actual_variant_gid: str
    cached_product_gid: str
    actual_product_gid: str


@dataclass(frozen=True, slots=True)
class CacheCheckResult:
    """Result of SKU cache consistency check.

    Contains statistics and detailed lists of discrepancies found
    when comparing the local cache against Shopify.

    Attributes:
        total_cached: Number of SKU entries in the local cache.
        total_shopify: Number of SKU entries found in Shopify.
        valid: Number of entries that match exactly.
        stale: List of SKUs in cache but not in Shopify (deleted/renamed).
        missing: List of SKUs in Shopify but not in cache.
        mismatched: List of SKUs with different GIDs between cache and Shopify.
    """

    total_cached: int
    total_shopify: int
    valid: int
    stale: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)
    mismatched: tuple[CacheMismatch, ...] = field(default_factory=tuple)

    @property
    def is_consistent(self) -> bool:
        """Return True if cache is fully consistent with Shopify."""
        return len(self.stale) == 0 and len(self.missing) == 0 and len(self.mismatched) == 0


def tokencache_clear(cache: CachePort) -> None:
    """Clear all cached OAuth tokens.

    Removes all cached access tokens. Use this when you need to force
    re-authentication, such as after rotating client secrets.

    Args:
        cache: The token cache adapter to clear.

    Example:
        >>> from pathlib import Path
        >>> from lib_shopify_graphql import tokencache_clear
        >>> from lib_shopify_graphql.adapters import JsonFileCacheAdapter
        >>>
        >>> cache = JsonFileCacheAdapter(Path("/tmp/token_cache.json"))
        >>> tokencache_clear(cache)

        >>> # Or using composition helper
        >>> from lib_shopify_graphql.composition import create_json_cache
        >>> cache = create_json_cache(Path("/tmp/token_cache.json"))
        >>> tokencache_clear(cache)
    """
    logger.info("Clearing token cache")
    cache.clear()
    logger.info("Token cache cleared")


def skucache_clear(cache: CachePort) -> None:
    """Clear all cached SKU-to-GID mappings.

    Removes all cached SKU resolutions. Use this when SKUs have changed
    or you need to force fresh lookups from Shopify.

    Args:
        cache: The SKU cache adapter to clear.

    Example:
        >>> from pathlib import Path
        >>> from lib_shopify_graphql import skucache_clear
        >>> from lib_shopify_graphql.adapters import JsonFileCacheAdapter
        >>>
        >>> cache = JsonFileCacheAdapter(Path("/tmp/sku_cache.json"))
        >>> skucache_clear(cache)

        >>> # Or using composition helper
        >>> from lib_shopify_graphql.composition import create_json_cache
        >>> cache = create_json_cache(Path("/tmp/sku_cache.json"))
        >>> skucache_clear(cache)
    """
    logger.info("Clearing SKU cache")
    cache.clear()
    logger.info("SKU cache cleared")


def cache_clear_all(
    token_cache: CachePort | None = None,
    sku_cache: CachePort | None = None,
) -> None:
    """Clear all caches (tokens and SKU mappings).

    Convenience function that clears both caches in one call.
    Only clears caches that are provided (non-None).

    Args:
        token_cache: The token cache adapter to clear.
        sku_cache: The SKU cache adapter to clear.

    Example:
        >>> from pathlib import Path
        >>> from lib_shopify_graphql import cache_clear_all
        >>> from lib_shopify_graphql.adapters import JsonFileCacheAdapter
        >>>
        >>> token_cache = JsonFileCacheAdapter(Path("/tmp/token_cache.json"))
        >>> sku_cache = JsonFileCacheAdapter(Path("/tmp/sku_cache.json"))
        >>> cache_clear_all(token_cache, sku_cache)
    """
    if token_cache is not None:
        tokencache_clear(token_cache)
    if sku_cache is not None:
        skucache_clear(sku_cache)


def _read_cache_entries(cache: CachePort, sku_prefix: str) -> dict[str, Any]:
    """Read and parse all SKU cache entries with the given prefix."""
    from ..adapters.sku_resolver import SKUCacheEntry

    entries: dict[str, Any] = {}
    for key in cache.keys(prefix=sku_prefix):
        value = cache.get(key)
        if not value:
            continue
        sku = key[len(sku_prefix) :]
        try:
            entries[sku] = SKUCacheEntry.model_validate_json(value)
        except ValueError:
            logger.debug(f"Invalid cache entry for key '{key}', skipping")
    return entries


def _rebuild_to_temp_cache(
    session: ShopifySession,
    sku_prefix: str,
    query: str | None,
) -> dict[str, Any]:
    """Rebuild SKU cache from Shopify into a temporary file and return entries."""
    from ..adapters.cache_json import JsonFileCacheAdapter
    from ..adapters.sku_resolver import CachedSKUResolver
    from ._products import skucache_rebuild

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_cache = JsonFileCacheAdapter(Path(tmpdir) / "temp_sku_cache.json")
        temp_resolver = CachedSKUResolver(temp_cache, session._graphql_client)

        total = skucache_rebuild(session, sku_resolver=temp_resolver, query=query)
        logger.info(f"Rebuilt {total} variants from Shopify")

        return _read_cache_entries(temp_cache, sku_prefix)


def _find_mismatches(
    actual_entries: dict[str, Any],
    shopify_entries: dict[str, Any],
    common_skus: set[str],
) -> list[CacheMismatch]:
    """Find entries where cached GIDs differ from Shopify."""
    mismatched: list[CacheMismatch] = []
    for sku in sorted(common_skus):
        cached = actual_entries[sku]
        actual = shopify_entries[sku]
        if cached.variant_gid != actual.variant_gid or cached.product_gid != actual.product_gid:
            mismatched.append(
                CacheMismatch(
                    sku=sku,
                    cached_variant_gid=cached.variant_gid,
                    actual_variant_gid=actual.variant_gid,
                    cached_product_gid=cached.product_gid,
                    actual_product_gid=actual.product_gid,
                )
            )
    return mismatched


def skucache_check(
    session: ShopifySession,
    cache: CachePort,
    *,
    query: str | None = None,
) -> CacheCheckResult:
    """Check SKU cache consistency by comparing with Shopify.

    Rebuilds the SKU cache from Shopify into a temporary file, then compares
    it with the actual cache to detect inconsistencies.

    This function helps diagnose cache issues such as:
    - Stale entries: SKUs cached but no longer in Shopify (products deleted)
    - Missing entries: SKUs in Shopify but not cached
    - Mismatched entries: SKUs with different variant/product GIDs

    Args:
        session: Active Shopify session.
        cache: The actual SKU cache to check.
        query: Optional Shopify query filter (e.g., "status:active").
            If None, checks all products.

    Returns:
        CacheCheckResult with comparison details.

    Raises:
        SessionNotActiveError: If the session is not active.

    Example::

        from lib_shopify_graphql import login, skucache_check

        session = login(credentials)
        result = skucache_check(session, sku_cache)
        if result.is_consistent:
            print("Cache is consistent")
        else:
            print(f"Found {len(result.stale)} stale entries")
    """
    from ..exceptions import SessionNotActiveError

    if not session.is_active:
        raise SessionNotActiveError("Session is not active.")

    shop_url = session.get_credentials().shop_url
    sku_prefix = f"sku:{shop_url}:"

    logger.info("Reading entries from actual cache")
    actual_entries = _read_cache_entries(cache, sku_prefix)
    logger.info(f"Found {len(actual_entries)} entries in actual cache")

    logger.info("Rebuilding cache from Shopify into temporary file")
    shopify_entries = _rebuild_to_temp_cache(session, sku_prefix, query)

    actual_skus = set(actual_entries.keys())
    shopify_skus = set(shopify_entries.keys())
    common = actual_skus & shopify_skus

    stale = tuple(sorted(actual_skus - shopify_skus))
    missing = tuple(sorted(shopify_skus - actual_skus))
    mismatched = _find_mismatches(actual_entries, shopify_entries, common)
    valid = len(common) - len(mismatched)

    logger.info(f"Cache check complete: {valid} valid, {len(stale)} stale, {len(missing)} missing, {len(mismatched)} mismatched")

    return CacheCheckResult(
        total_cached=len(actual_entries),
        total_shopify=len(shopify_entries),
        valid=valid,
        stale=stale,
        missing=missing,
        mismatched=tuple(mismatched),
    )


__all__ = [
    "CacheCheckResult",
    "CacheMismatch",
    "cache_clear_all",
    "skucache_check",
    "skucache_clear",
    "tokencache_clear",
]
