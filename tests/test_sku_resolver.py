"""SKU resolver tests: verifying bidirectional cache strategy.

Tests use real in-memory implementations instead of mocks to validate
actual system behavior. Each test reads like plain English.

Coverage:
- resolve() always queries Shopify to verify uniqueness
- Unique SKU is cached with bidirectional entries
- Ambiguous SKU raises AmbiguousSKUError
- update_from_variant() handles SKU changes correctly
- update_from_product() updates cache for all variants
- Cache invalidation removes both forward and reverse entries
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lib_shopify_graphql.adapters.sku_resolver import (
    VARIANTS_BY_SKU_QUERY,
    CachedSKUResolver,
    SKUCacheEntry,
)
from lib_shopify_graphql.exceptions import AmbiguousSKUError
from lib_shopify_graphql.models import Product, ProductVariant, Money, ProductStatus

from conftest import FakeGraphQLClient, InMemoryCache


# Shared test timestamp for Product models
_TEST_TIMESTAMP = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


# =============================================================================
# Resolve Always Queries Shopify
# =============================================================================


@pytest.mark.os_agnostic
class TestResolveAlwaysQueriesShopify:
    """resolve() always queries Shopify to verify uniqueness."""

    def test_queries_shopify_for_every_resolve(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Every resolve() call queries Shopify."""
        fake_graphql_client.add_sku_mapping("ABC-123", "gid://shopify/ProductVariant/12345")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        resolver.resolve("ABC-123", "mystore.myshopify.com")
        resolver.resolve("ABC-123", "mystore.myshopify.com")

        assert fake_graphql_client.call_count == 2

    def test_returns_variant_gid_when_unique(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Returns the variant GID when SKU is unique."""
        fake_graphql_client.add_sku_mapping("ABC-123", "gid://shopify/ProductVariant/77777")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        result = resolver.resolve("ABC-123", "mystore.myshopify.com")

        assert result == "gid://shopify/ProductVariant/77777"

    def test_returns_none_when_not_found(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Returns None when SKU not found in Shopify."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        result = resolver.resolve("NONEXISTENT", "mystore.myshopify.com")

        assert result is None


# =============================================================================
# Ambiguous SKU Detection
# =============================================================================


@pytest.mark.os_agnostic
class TestAmbiguousSKUDetection:
    """resolve() raises AmbiguousSKUError when SKU matches multiple variants."""

    def test_raises_error_for_ambiguous_sku(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Raises AmbiguousSKUError when SKU matches multiple variants."""
        fake_graphql_client.add_sku_mappings(
            "DUPE-SKU",
            ["gid://shopify/ProductVariant/111", "gid://shopify/ProductVariant/222"],
        )
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        with pytest.raises(AmbiguousSKUError) as exc_info:
            resolver.resolve("DUPE-SKU", "mystore.myshopify.com")

        assert exc_info.value.sku == "DUPE-SKU"
        assert len(exc_info.value.variant_gids) == 2

    def test_ambiguous_sku_is_not_cached(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Ambiguous SKU is not added to cache."""
        fake_graphql_client.add_sku_mappings(
            "DUPE-SKU",
            ["gid://shopify/ProductVariant/111", "gid://shopify/ProductVariant/222"],
        )
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        with pytest.raises(AmbiguousSKUError):
            resolver.resolve("DUPE-SKU", "mystore.myshopify.com")

        assert len(in_memory_cache) == 0


# =============================================================================
# Bidirectional Cache Storage
# =============================================================================


@pytest.mark.os_agnostic
class TestBidirectionalCacheStorage:
    """resolve() stores bidirectional cache entries (forward + reverse)."""

    def test_unique_sku_creates_forward_entry(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Unique SKU creates forward cache entry (SKU -> variant info)."""
        fake_graphql_client.add_sku_mapping("ABC-123", "gid://shopify/ProductVariant/55555", "gid://shopify/Product/999")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        resolver.resolve("ABC-123", "mystore.myshopify.com")

        forward_key = "sku:mystore.myshopify.com:ABC-123"
        cached = in_memory_cache.get(forward_key)
        assert cached is not None
        entry = SKUCacheEntry.model_validate_json(cached)
        assert entry.variant_gid == "gid://shopify/ProductVariant/55555"
        assert entry.product_gid == "gid://shopify/Product/999"
        assert entry.sku == "ABC-123"

    def test_unique_sku_creates_reverse_entry(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Unique SKU creates reverse cache entry (variant -> SKU info)."""
        fake_graphql_client.add_sku_mapping("ABC-123", "gid://shopify/ProductVariant/55555", "gid://shopify/Product/999")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        resolver.resolve("ABC-123", "mystore.myshopify.com")

        reverse_key = "variant:mystore.myshopify.com:gid://shopify/ProductVariant/55555"
        cached = in_memory_cache.get(reverse_key)
        assert cached is not None
        entry = SKUCacheEntry.model_validate_json(cached)
        assert entry.variant_gid == "gid://shopify/ProductVariant/55555"
        assert entry.sku == "ABC-123"

    def test_different_shops_have_different_cache_namespaces(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Same SKU in different shops are cached separately."""
        fake_graphql_client.add_sku_mapping("SKU-001", "gid://variant/111", "gid://product/1")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        resolver.resolve("SKU-001", "shop1.myshopify.com")
        resolver.resolve("SKU-001", "shop2.myshopify.com")

        # Both forward entries exist with different namespaces
        assert in_memory_cache.get("sku:shop1.myshopify.com:SKU-001") is not None
        assert in_memory_cache.get("sku:shop2.myshopify.com:SKU-001") is not None


# =============================================================================
# Update From Variant
# =============================================================================


@pytest.mark.os_agnostic
class TestUpdateFromVariant:
    """update_from_variant() updates cache after variant upsert."""

    def test_creates_cache_entry_for_new_variant(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Creates cache entries for a new variant."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        resolver.update_from_variant(
            variant_gid="gid://shopify/ProductVariant/123",
            product_gid="gid://shopify/Product/456",
            sku="NEW-SKU",
            shop_url="mystore.myshopify.com",
        )

        # Forward entry exists
        forward = in_memory_cache.get("sku:mystore.myshopify.com:NEW-SKU")
        assert forward is not None
        entry = SKUCacheEntry.model_validate_json(forward)
        assert entry.variant_gid == "gid://shopify/ProductVariant/123"

        # Reverse entry exists
        reverse = in_memory_cache.get("variant:mystore.myshopify.com:gid://shopify/ProductVariant/123")
        assert reverse is not None

    def test_updates_cache_when_sku_changes(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """When SKU changes, old forward entry is deleted."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        # First set old SKU
        resolver.update_from_variant(
            variant_gid="gid://shopify/ProductVariant/123",
            product_gid="gid://shopify/Product/456",
            sku="OLD-SKU",
            shop_url="mystore.myshopify.com",
        )

        # Update to new SKU
        resolver.update_from_variant(
            variant_gid="gid://shopify/ProductVariant/123",
            product_gid="gid://shopify/Product/456",
            sku="NEW-SKU",
            shop_url="mystore.myshopify.com",
        )

        # Old forward entry is deleted
        assert in_memory_cache.get("sku:mystore.myshopify.com:OLD-SKU") is None

        # New forward entry exists
        assert in_memory_cache.get("sku:mystore.myshopify.com:NEW-SKU") is not None

        # Reverse entry is updated
        reverse = in_memory_cache.get("variant:mystore.myshopify.com:gid://shopify/ProductVariant/123")
        entry = SKUCacheEntry.model_validate_json(reverse)
        assert entry.sku == "NEW-SKU"

    def test_handles_variant_with_no_sku(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """When variant has no SKU, only reverse entry is removed."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        # First set SKU
        resolver.update_from_variant(
            variant_gid="gid://shopify/ProductVariant/123",
            product_gid="gid://shopify/Product/456",
            sku="OLD-SKU",
            shop_url="mystore.myshopify.com",
        )

        # Update to no SKU
        resolver.update_from_variant(
            variant_gid="gid://shopify/ProductVariant/123",
            product_gid="gid://shopify/Product/456",
            sku=None,
            shop_url="mystore.myshopify.com",
        )

        # Old forward entry is deleted
        assert in_memory_cache.get("sku:mystore.myshopify.com:OLD-SKU") is None

        # Reverse entry is deleted
        assert in_memory_cache.get("variant:mystore.myshopify.com:gid://shopify/ProductVariant/123") is None


# =============================================================================
# Update From Product
# =============================================================================


@pytest.mark.os_agnostic
class TestUpdateFromProduct:
    """update_from_product() updates cache for all variants in a product."""

    def test_updates_cache_for_all_variants(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Updates cache entries for all variants in product."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test",
            status=ProductStatus.ACTIVE,
            created_at=_TEST_TIMESTAMP,
            updated_at=_TEST_TIMESTAMP,
            variants=[
                ProductVariant(
                    id="gid://shopify/ProductVariant/1",
                    title="Small",
                    sku="SKU-SMALL",
                    price=Money(amount="10.00", currency_code="USD"),
                ),
                ProductVariant(
                    id="gid://shopify/ProductVariant/2",
                    title="Large",
                    sku="SKU-LARGE",
                    price=Money(amount="15.00", currency_code="USD"),
                ),
            ],
        )

        resolver.update_from_product(product, "mystore.myshopify.com")

        # Both SKUs are cached
        assert in_memory_cache.get("sku:mystore.myshopify.com:SKU-SMALL") is not None
        assert in_memory_cache.get("sku:mystore.myshopify.com:SKU-LARGE") is not None

    def test_handles_variants_without_sku(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Variants without SKU don't create forward entries."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test",
            status=ProductStatus.ACTIVE,
            created_at=_TEST_TIMESTAMP,
            updated_at=_TEST_TIMESTAMP,
            variants=[
                ProductVariant(
                    id="gid://shopify/ProductVariant/1",
                    title="No SKU",
                    sku=None,
                    price=Money(amount="10.00", currency_code="USD"),
                ),
            ],
        )

        resolver.update_from_product(product, "mystore.myshopify.com")

        # No forward entry for variant without SKU
        assert len([k for k in in_memory_cache.keys() if k.startswith("sku:")]) == 0


# =============================================================================
# Cache Invalidation
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheInvalidation:
    """invalidate() removes both forward and reverse entries."""

    def test_invalidate_removes_forward_entry(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Invalidate removes the forward SKU entry."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)
        resolver.update_from_variant("gid://variant/123", "gid://product/456", "ABC-123", "mystore.myshopify.com")

        resolver.invalidate("ABC-123", "mystore.myshopify.com")

        assert in_memory_cache.get("sku:mystore.myshopify.com:ABC-123") is None

    def test_invalidate_removes_reverse_entry(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Invalidate removes the reverse variant entry."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)
        resolver.update_from_variant("gid://variant/123", "gid://product/456", "ABC-123", "mystore.myshopify.com")

        resolver.invalidate("ABC-123", "mystore.myshopify.com")

        assert in_memory_cache.get("variant:mystore.myshopify.com:gid://variant/123") is None


# =============================================================================
# Cache Rebuild
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheRebuild:
    """skucache_rebuild() re-resolves SKUs from Shopify and updates cache."""

    def test_resolves_all_skus_and_returns_mapping(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """skucache_rebuild resolves all SKUs and returns a mapping."""
        fake_graphql_client.add_sku_mapping("SKU-1", "gid://variant/1")
        fake_graphql_client.add_sku_mapping("SKU-2", "gid://variant/2")
        fake_graphql_client.add_sku_mapping("SKU-3", "gid://variant/3")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        results = resolver.rebuild_cache(["SKU-1", "SKU-2", "SKU-3"], "mystore.myshopify.com")

        assert results["SKU-1"] == "gid://variant/1"
        assert results["SKU-2"] == "gid://variant/2"
        assert results["SKU-3"] == "gid://variant/3"

    def test_returns_none_for_not_found_skus(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """skucache_rebuild returns None for SKUs not found in Shopify."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        results = resolver.rebuild_cache(["NONEXISTENT"], "mystore.myshopify.com")

        assert results["NONEXISTENT"] is None

    def test_returns_none_for_ambiguous_skus(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """skucache_rebuild returns None for ambiguous SKUs (no exception)."""
        fake_graphql_client.add_sku_mappings("DUPE", ["gid://variant/1", "gid://variant/2"])
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        results = resolver.rebuild_cache(["DUPE"], "mystore.myshopify.com")

        assert results["DUPE"] is None


# =============================================================================
# Error Handling
# =============================================================================


@pytest.mark.os_agnostic
class TestErrorHandling:
    """API errors are handled gracefully without crashing."""

    def test_api_error_returns_none(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """A Shopify API error returns None instead of crashing."""
        fake_graphql_client.configure_error(Exception("Connection failed"))
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        result = resolver.resolve("ABC-123", "mystore.myshopify.com")

        assert result is None

    def test_api_error_does_not_cache_result(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """An API error does not pollute the cache."""
        fake_graphql_client.configure_error(Exception("Timeout"))
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        resolver.resolve("ABC-123", "mystore.myshopify.com")

        assert len(in_memory_cache) == 0


# =============================================================================
# Resolve All
# =============================================================================


@pytest.mark.os_agnostic
class TestResolveAllReturnsAllMatches:
    """resolve_all returns all variant GIDs matching a SKU."""

    def test_returns_all_matching_variants(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Returns list of all variant GIDs with exact SKU match."""
        fake_graphql_client.add_sku_mappings(
            "ABC-123",
            ["gid://shopify/ProductVariant/111", "gid://shopify/ProductVariant/222"],
        )
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        result = resolver.resolve_all("ABC-123")

        assert len(result) == 2
        assert "gid://shopify/ProductVariant/111" in result
        assert "gid://shopify/ProductVariant/222" in result

    def test_returns_empty_list_when_no_matches(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Returns empty list when SKU not found."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        result = resolver.resolve_all("UNKNOWN-SKU")

        assert result == []


# =============================================================================
# Query Definition
# =============================================================================


@pytest.mark.os_agnostic
class TestVariantsBySkuQuery:
    """The GraphQL query is correctly defined."""

    def test_query_includes_required_fields(self) -> None:
        """Query contains essential fields for SKU resolution."""
        assert "productVariants" in VARIANTS_BY_SKU_QUERY
        assert "sku" in VARIANTS_BY_SKU_QUERY
        assert "id" in VARIANTS_BY_SKU_QUERY
        assert "product" in VARIANTS_BY_SKU_QUERY  # Must include product for cache

    def test_query_requests_multiple_results(self) -> None:
        """Query fetches up to 50 results for duplicate SKU detection."""
        assert "first: 50" in VARIANTS_BY_SKU_QUERY


# =============================================================================
# Initialization
# =============================================================================


@pytest.mark.os_agnostic
class TestResolverInitialization:
    """CachedSKUResolver initializes with correct defaults."""

    def test_default_cache_ttl_is_30_days(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Cache TTL defaults to 30 days (2592000 seconds)."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        assert resolver.cache_ttl == 2592000

    def test_custom_cache_ttl_is_honored(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Custom cache TTL is stored and used."""
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client, cache_ttl=7200)

        assert resolver.cache_ttl == 7200


# =============================================================================
# Special Characters in SKU (Edge Cases)
# =============================================================================


@pytest.mark.os_agnostic
class TestSKUSpecialCharacters:
    """SKUs with special characters are handled correctly."""

    def test_sku_with_double_quotes(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """SKU containing double quotes is escaped in query."""
        sku_with_quotes = 'ABC"DEF'
        fake_graphql_client.add_sku_mapping(sku_with_quotes, "gid://shopify/ProductVariant/123")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        result = resolver.resolve(sku_with_quotes, "mystore.myshopify.com")

        assert result == "gid://shopify/ProductVariant/123"

    def test_sku_with_backslash(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """SKU containing backslash is escaped in query."""
        sku_with_backslash = "ABC\\DEF"
        fake_graphql_client.add_sku_mapping(sku_with_backslash, "gid://shopify/ProductVariant/456")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        result = resolver.resolve(sku_with_backslash, "mystore.myshopify.com")

        assert result == "gid://shopify/ProductVariant/456"

    def test_sku_with_mixed_special_chars(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """SKU with multiple special characters is handled."""
        sku_mixed = 'AB"C\\D"EF'
        fake_graphql_client.add_sku_mapping(sku_mixed, "gid://shopify/ProductVariant/789")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        result = resolver.resolve(sku_mixed, "mystore.myshopify.com")

        assert result == "gid://shopify/ProductVariant/789"


# =============================================================================
# Invalid Cache Entry Handling
# =============================================================================


@pytest.mark.os_agnostic
class TestInvalidCacheEntryHandling:
    """Invalid cache entries are handled gracefully."""

    def test_invalid_forward_cache_entry_handled_during_invalidate(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Invalid JSON in forward cache is handled gracefully during invalidate."""
        # Put invalid JSON in the forward cache
        in_memory_cache.set("sku:mystore.myshopify.com:ABC-123", "not valid json")
        resolver = CachedSKUResolver(in_memory_cache, fake_graphql_client)

        # invalidate() should handle invalid cache gracefully
        # It calls _get_forward_entry which will hit the ValueError handler
        resolver.invalidate("ABC-123", "mystore.myshopify.com")

        # No exception raised, forward entry should be deleted
        assert in_memory_cache.get("sku:mystore.myshopify.com:ABC-123") is None
