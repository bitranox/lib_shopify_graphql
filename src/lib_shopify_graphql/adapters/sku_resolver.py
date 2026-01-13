"""SKU resolver with bidirectional cache strategy.

This module provides SKU-to-GID resolution for variant identification.

Classes:
    - :class:`CachedSKUResolver`: SKU resolver with bidirectional cache.

Important:
    SKUs in Shopify are NOT guaranteed to be unique. Multiple variants
    (potentially across different products) can share the same SKU.
    The resolver detects this and raises :class:`AmbiguousSKUError`
    when a SKU matches multiple variants.

Cache Behavior:
    The cache maintains bidirectional mappings:
    - Forward: ``sku:{shop}:{sku}`` → ``{"variant_gid", "product_gid"}``
    - Reverse: ``variant:{shop}:{gid}`` → ``{"sku", "product_gid"}``

    Cache is updated on:
    - Read operations: ``resolve()``, ``update_from_product()``
    - Write operations: ``update_from_variant()``

    When a variant's SKU changes, the old forward entry is automatically
    deleted to prevent stale lookups.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from ..exceptions import AmbiguousSKUError
from .constants import DEFAULT_SKU_CACHE_TTL_SECONDS

if TYPE_CHECKING:
    from ..application.ports import CachePort, GraphQLClientPort
    from ..models import Product

logger = logging.getLogger(__name__)


def _escape_graphql_string(value: str) -> str:
    """Escape special characters for GraphQL string literals.

    Args:
        value: Raw string value to escape.

    Returns:
        Escaped string safe for use in GraphQL queries.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


# GraphQL query to find ALL variants by SKU with product info
VARIANTS_BY_SKU_QUERY = """
query VariantsBySKU($sku: String!) {
    productVariants(first: 50, query: $sku) {
        edges {
            node {
                id
                sku
                product {
                    id
                }
            }
        }
    }
}
"""


class SKUCacheEntry(BaseModel):
    """Cache entry for SKU-to-variant mapping.

    Stores the full context needed for bidirectional lookups
    and stale entry detection.
    """

    model_config = ConfigDict(frozen=True)

    variant_gid: str
    product_gid: str
    sku: str


class CachedSKUResolver:
    """SKU resolver with bidirectional cache.

    Implements :class:`~lib_shopify_graphql.application.ports.SKUResolverPort`.

    Resolution strategy:
    1. Query Shopify GraphQL API for all variants with the SKU
    2. If unique, update forward + reverse cache entries
    3. If ambiguous, raise AmbiguousSKUError (no caching)

    Cache update strategy:
    - On resolve(): store both forward and reverse mappings
    - On update_from_variant(): detect SKU changes, update/invalidate entries
    - On update_from_product(): bulk update cache for all variants

    Attributes:
        cache: Cache adapter for storing SKU mappings.
        graphql: GraphQL client for Shopify API queries.
        cache_ttl: Time-to-live for cache entries in seconds.

    Example:
        >>> resolver = CachedSKUResolver(cache, graphql)
        >>> gid = resolver.resolve("ABC-123", "mystore.myshopify.com")
        >>> gid
        'gid://shopify/ProductVariant/123456789'
    """

    def __init__(
        self,
        cache: CachePort,
        graphql: GraphQLClientPort,
        cache_ttl: int = DEFAULT_SKU_CACHE_TTL_SECONDS,
    ) -> None:
        """Initialize the SKU resolver.

        Args:
            cache: Cache adapter for storing SKU-to-GID mappings.
            graphql: GraphQL client for Shopify API queries.
            cache_ttl: Cache TTL in seconds. Defaults to 24 hours.
        """
        self.cache = cache
        self.graphql = graphql
        self.cache_ttl = cache_ttl

    # -------------------------------------------------------------------------
    # Cache Key Helpers
    # -------------------------------------------------------------------------

    def _make_forward_key(self, sku: str, shop_url: str) -> str:
        """Generate forward cache key (SKU → variant).

        Args:
            sku: Stock keeping unit.
            shop_url: Shop URL for namespacing.

        Returns:
            Cache key in format "sku:{shop_url}:{sku}".
        """
        return f"sku:{shop_url}:{sku}"

    def _make_reverse_key(self, variant_gid: str, shop_url: str) -> str:
        """Generate reverse cache key (variant → SKU).

        Args:
            variant_gid: Variant GID.
            shop_url: Shop URL for namespacing.

        Returns:
            Cache key in format "variant:{shop_url}:{variant_gid}".
        """
        return f"variant:{shop_url}:{variant_gid}"

    # -------------------------------------------------------------------------
    # Cache Entry Helpers
    # -------------------------------------------------------------------------

    def _set_cache_entry(
        self,
        sku: str,
        variant_gid: str,
        product_gid: str,
        shop_url: str,
    ) -> None:
        """Store bidirectional cache entries.

        Creates both forward (SKU → variant) and reverse (variant → SKU)
        mappings for efficient lookups and invalidation.

        Args:
            sku: Stock keeping unit.
            variant_gid: Variant GID.
            product_gid: Product GID.
            shop_url: Shop URL for namespacing.
        """
        entry = SKUCacheEntry(
            variant_gid=variant_gid,
            product_gid=product_gid,
            sku=sku,
        )
        entry_json = entry.model_dump_json()

        # Forward: SKU → variant info
        forward_key = self._make_forward_key(sku, shop_url)
        self.cache.set(forward_key, entry_json, ttl=self.cache_ttl)

        # Reverse: variant → SKU info
        reverse_key = self._make_reverse_key(variant_gid, shop_url)
        self.cache.set(reverse_key, entry_json, ttl=self.cache_ttl)

        logger.debug(
            "Cache entry set",
            extra={"sku": sku, "variant_gid": variant_gid, "product_gid": product_gid},
        )

    def _get_forward_entry(self, sku: str, shop_url: str) -> SKUCacheEntry | None:
        """Get cache entry by SKU (forward lookup).

        Args:
            sku: Stock keeping unit.
            shop_url: Shop URL.

        Returns:
            Cache entry if found, None otherwise.
        """
        key = self._make_forward_key(sku, shop_url)
        cached = self.cache.get(key)
        if not cached:
            return None

        try:
            return SKUCacheEntry.model_validate_json(cached)
        except ValueError:
            # Invalid cache entry, treat as miss
            logger.debug("Invalid forward cache entry", extra={"sku": sku})
            return None

    def _get_reverse_entry(self, variant_gid: str, shop_url: str) -> SKUCacheEntry | None:
        """Get cache entry by variant GID (reverse lookup).

        Args:
            variant_gid: Variant GID.
            shop_url: Shop URL.

        Returns:
            Cache entry if found, None otherwise.
        """
        key = self._make_reverse_key(variant_gid, shop_url)
        cached = self.cache.get(key)
        if not cached:
            return None

        try:
            return SKUCacheEntry.model_validate_json(cached)
        except ValueError:
            # Invalid cache entry, treat as miss
            logger.debug("Invalid reverse cache entry", extra={"variant_gid": variant_gid})
            return None

    def _delete_forward_entry(self, sku: str, shop_url: str) -> None:
        """Delete forward cache entry.

        Args:
            sku: SKU to remove.
            shop_url: Shop URL.
        """
        key = self._make_forward_key(sku, shop_url)
        self.cache.delete(key)

    def _delete_reverse_entry(self, variant_gid: str, shop_url: str) -> None:
        """Delete reverse cache entry.

        Args:
            variant_gid: Variant GID to remove.
            shop_url: Shop URL.
        """
        key = self._make_reverse_key(variant_gid, shop_url)
        self.cache.delete(key)

    # -------------------------------------------------------------------------
    # Public API: Resolution
    # -------------------------------------------------------------------------

    def resolve(self, sku: str, shop_url: str) -> str | None:
        """Resolve a SKU to its variant GID.

        Always queries Shopify to verify uniqueness, then updates the cache.
        This ensures safety even when another variant is assigned the same SKU.

        Args:
            sku: Stock keeping unit identifier.
            shop_url: Shopify store URL for cache key namespacing.

        Returns:
            Variant GID if found and unique, None if not found.

        Raises:
            AmbiguousSKUError: If the SKU matches multiple variants.
                Use explicit variant GID or resolve_all() instead.
        """
        logger.debug("Resolving SKU", extra={"sku": sku, "shop_url": shop_url})

        # Query Shopify for ALL matches to detect ambiguity
        matches = self._query_shopify_for_all_variants(sku)

        if not matches:
            logger.debug("SKU not found", extra={"sku": sku})
            return None

        if len(matches) > 1:
            variant_gids = [m["variant_gid"] for m in matches]
            logger.warning(f"Ambiguous SKU '{sku}' found in {len(matches)} variants: {variant_gids}")
            raise AmbiguousSKUError(sku, variant_gids)

        # Single match - update cache and return
        match = matches[0]
        self._set_cache_entry(
            sku=sku,
            variant_gid=match["variant_gid"],
            product_gid=match["product_gid"],
            shop_url=shop_url,
        )

        logger.debug("SKU resolved", extra={"sku": sku, "gid": match["variant_gid"]})
        return match["variant_gid"]

    def resolve_all(self, sku: str) -> list[str]:
        """Resolve a SKU to ALL matching variant GIDs.

        Does not use cache. Always queries Shopify to find all variants.

        Args:
            sku: Stock keeping unit identifier.

        Returns:
            List of variant GIDs. Empty list if no matches found.
        """
        logger.debug("Resolving all variants for SKU", extra={"sku": sku})
        matches = self._query_shopify_for_all_variants(sku)
        return [m["variant_gid"] for m in matches]

    # -------------------------------------------------------------------------
    # Public API: Cache Updates
    # -------------------------------------------------------------------------

    def update_from_variant(
        self,
        variant_gid: str,
        product_gid: str,
        sku: str | None,
        shop_url: str,
    ) -> None:
        """Update cache after variant upsert.

        Handles SKU changes by:
        1. Looking up old SKU via reverse cache
        2. If SKU changed, deleting old forward entry
        3. Setting new forward + reverse entries

        Args:
            variant_gid: Variant GID.
            product_gid: Product GID.
            sku: New SKU value (None if variant has no SKU).
            shop_url: Shop URL for namespacing.
        """
        # Get old entry via reverse lookup
        old_entry = self._get_reverse_entry(variant_gid, shop_url)

        if old_entry and old_entry.sku and old_entry.sku != sku:
            # SKU changed - delete old forward entry
            self._delete_forward_entry(old_entry.sku, shop_url)
            logger.debug(
                "Old SKU cache invalidated",
                extra={"old_sku": old_entry.sku, "new_sku": sku, "variant_gid": variant_gid},
            )

        if sku:
            # Set new entries
            self._set_cache_entry(sku, variant_gid, product_gid, shop_url)
        else:
            # Variant has no SKU - just delete reverse entry
            self._delete_reverse_entry(variant_gid, shop_url)

    def update_from_product(self, product: Product, shop_url: str) -> None:
        """Update cache for all variants in a product.

        Call this after fetching a product to keep the cache warm.

        Args:
            product: Product with variants.
            shop_url: Shop URL for namespacing.
        """
        if not product.variants:
            return

        for variant in product.variants:
            self.update_from_variant(
                variant_gid=variant.id,
                product_gid=product.id,
                sku=variant.sku,
                shop_url=shop_url,
            )

        logger.debug(
            "Cache updated from product",
            extra={"product_id": product.id, "variant_count": len(product.variants)},
        )

    # -------------------------------------------------------------------------
    # Public API: Cache Management
    # -------------------------------------------------------------------------

    def invalidate(self, sku: str, shop_url: str) -> None:
        """Remove a SKU mapping from cache.

        Deletes both forward and reverse entries for the SKU.

        Args:
            sku: SKU to invalidate.
            shop_url: Shopify store URL.
        """
        # Get entry to find variant GID for reverse deletion
        entry = self._get_forward_entry(sku, shop_url)

        # Delete forward entry
        self._delete_forward_entry(sku, shop_url)

        # Delete reverse entry if we found the variant
        if entry:
            self._delete_reverse_entry(entry.variant_gid, shop_url)

        logger.debug("SKU cache invalidated", extra={"sku": sku, "shop_url": shop_url})

    def rebuild_cache(self, skus: list[str], shop_url: str) -> dict[str, str | None]:
        """Rebuild cache by re-resolving all provided SKUs from Shopify.

        Re-queries Shopify for each SKU and updates the cache with fresh data.
        Use this to verify cache consistency or rebuild after data changes.

        Args:
            skus: List of SKUs to resolve and cache.
            shop_url: Shopify store URL.

        Returns:
            Dictionary mapping each SKU to its variant GID (or None if not found/ambiguous).
        """
        results: dict[str, str | None] = {}
        for sku in skus:
            try:
                results[sku] = self.resolve(sku, shop_url)
            except AmbiguousSKUError:
                results[sku] = None
        return results

    # -------------------------------------------------------------------------
    # Private: Shopify Queries
    # -------------------------------------------------------------------------

    def _query_shopify_for_all_variants(self, sku: str) -> list[dict[str, str]]:
        """Query Shopify GraphQL API for ALL variants by SKU.

        Args:
            sku: Stock keeping unit to search for.

        Returns:
            List of dicts with variant_gid and product_gid for exact SKU matches.
        """
        try:
            escaped_sku = _escape_graphql_string(sku)
            query_string = f'sku:"{escaped_sku}"'
            result: dict[str, Any] = self.graphql.execute(
                VARIANTS_BY_SKU_QUERY,
                variables={"sku": query_string},
            )

            edges = result.get("data", {}).get("productVariants", {}).get("edges", [])
            if not edges:
                return []

            # Collect all exact SKU matches with product info
            matches: list[dict[str, str]] = []
            for edge in edges:
                node = edge.get("node", {})
                if node.get("sku") == sku:
                    variant_gid = node.get("id")
                    product_gid = node.get("product", {}).get("id")
                    if variant_gid and product_gid:
                        matches.append(
                            {
                                "variant_gid": variant_gid,
                                "product_gid": product_gid,
                            }
                        )

            logger.debug(
                "Found variants for SKU",
                extra={"sku": sku, "count": len(matches)},
            )
            return matches

        except Exception as exc:
            logger.warning(f"Failed to query Shopify for SKU '{sku}': {exc}")
            return []


__all__ = ["CachedSKUResolver", "SKUCacheEntry", "VARIANTS_BY_SKU_QUERY"]
