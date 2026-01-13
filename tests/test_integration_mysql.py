"""MySQL cache adapter integration tests.

Tests the MySQLCacheAdapter implementation and cache operations with MySQL backend.
These tests run as part of `make test-slow` when MySQL is configured.

Requirements:
    - pip install lib_shopify_graphql[mysql]
    - MySQL server running
    - SHOPIFY__MYSQL__CONNECTION or individual params configured
    - Shopify credentials for cache operation tests

Database lifecycle:
    - Database is dropped on test start (cleanup from previous runs)
    - Database is dropped after tests complete

Skipped automatically when:
    - Running in CI environment (CI=true)
    - pymysql not installed
    - MySQL not configured

Run with: make test-slow
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from lib_shopify_graphql import Product, ShopifySession

    from conftest import MySQLTestState


pytestmark = [
    pytest.mark.integration,
    pytest.mark.mysql_integration,
]


class TestMySQLCacheAdapter:
    """Tests for MySQLCacheAdapter implementation."""

    def test_auto_creates_database(self, mysql_test_config: "MySQLTestState") -> None:
        """MySQLCacheAdapter auto-creates database when configured."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        cfg = mysql_test_config.config
        auto_create = not mysql_test_config.database_exists

        cache = MySQLCacheAdapter(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            table_name="test_auto_create",
            auto_create_database=auto_create,
        )

        # Verify basic operations work
        cache.set("test_key", "test_value")
        assert cache.get("test_key") == "test_value"

    def test_get_set_delete(self, mysql_test_config: "MySQLTestState") -> None:
        """Basic get/set/delete operations work correctly."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        cfg = mysql_test_config.config
        auto_create = not mysql_test_config.database_exists

        cache = MySQLCacheAdapter(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            table_name="test_crud",
            auto_create_database=auto_create,
        )

        # Set and get
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Update existing key
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

        # Delete
        cache.delete("key1")
        assert cache.get("key1") is None

        # Get non-existent key
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self, mysql_test_config: "MySQLTestState") -> None:
        """TTL causes entries to expire."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        cfg = mysql_test_config.config
        auto_create = not mysql_test_config.database_exists

        cache = MySQLCacheAdapter(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            table_name="test_ttl",
            auto_create_database=auto_create,
        )

        # Set with 1 second TTL
        cache.set("short_lived", "value", ttl=1)
        assert cache.get("short_lived") == "value"

        # Wait for expiration
        time.sleep(2)
        assert cache.get("short_lived") is None

    def test_keys_with_prefix(self, mysql_test_config: "MySQLTestState") -> None:
        """keys() returns keys with optional prefix filter."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        cfg = mysql_test_config.config
        auto_create = not mysql_test_config.database_exists

        cache = MySQLCacheAdapter(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            table_name="test_keys",
            auto_create_database=auto_create,
        )

        cache.clear()

        cache.set("sku:shop1:ABC", "v1")
        cache.set("sku:shop1:DEF", "v2")
        cache.set("token:shop1:client1", "v3")

        assert len(cache.keys()) == 3
        assert len(cache.keys(prefix="sku:")) == 2
        assert len(cache.keys(prefix="token:")) == 1

    def test_clear(self, mysql_test_config: "MySQLTestState") -> None:
        """clear() removes all entries."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        cfg = mysql_test_config.config
        auto_create = not mysql_test_config.database_exists

        cache = MySQLCacheAdapter(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            table_name="test_clear",
            auto_create_database=auto_create,
        )

        cache.set("k1", "v1")
        cache.set("k2", "v2")
        assert len(cache.keys()) == 2

        cache.clear()
        assert len(cache.keys()) == 0

    def test_from_url_factory(self, mysql_test_config: "MySQLTestState") -> None:
        """from_url() creates adapter from connection string."""
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        cfg = mysql_test_config.config
        auto_create = not mysql_test_config.database_exists

        url = f"mysql://{cfg.user}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.database}"

        cache = MySQLCacheAdapter.from_url(
            url,
            table_name="test_from_url",
            auto_create_database=auto_create,
        )

        cache.set("url_key", "url_value")
        assert cache.get("url_key") == "url_value"


# =============================================================================
# Higher-Level Cache Operations with MySQL Backend
# =============================================================================


class TestSKUCacheRebuildMySQL:
    """Integration tests for SKU cache rebuild with MySQL backend."""

    def test_skucache_rebuild_returns_variant_count(
        self,
        integration_session: "ShopifySession",
        test_product: "Product",
        mysql_sku_cache: Any,
    ) -> None:
        """skucache_rebuild returns count of cached variants."""
        from lib_shopify_graphql import skucache_rebuild
        from lib_shopify_graphql.adapters import CachedSKUResolver

        resolver = CachedSKUResolver(mysql_sku_cache, integration_session._graphql_client)

        # Rebuild cache for test product only
        count = skucache_rebuild(
            integration_session,
            sku_resolver=resolver,
            query=f"id:{test_product.id.split('/')[-1]}",
        )

        # Should have cached at least the variants from test_product
        assert count >= len(test_product.variants)

    def test_skucache_rebuild_populates_sku_mappings(
        self,
        integration_session: "ShopifySession",
        test_product: "Product",
        mysql_sku_cache: Any,
    ) -> None:
        """skucache_rebuild populates SKU-to-GID mappings in MySQL cache."""
        from lib_shopify_graphql import skucache_rebuild
        from lib_shopify_graphql.adapters import CachedSKUResolver

        resolver = CachedSKUResolver(mysql_sku_cache, integration_session._graphql_client)

        # Rebuild cache
        skucache_rebuild(
            integration_session,
            sku_resolver=resolver,
            query=f"id:{test_product.id.split('/')[-1]}",
        )

        # Verify SKUs are now cached
        shop_url = integration_session.get_credentials().shop_url
        for variant in test_product.variants:
            if variant.sku:
                cache_key = f"sku:{shop_url}:{variant.sku}"
                cached_value = mysql_sku_cache.get(cache_key)
                assert cached_value is not None, f"SKU {variant.sku} not cached"

    def test_skucache_clear_removes_all_entries(
        self,
        integration_session: "ShopifySession",
        test_product: "Product",
        mysql_sku_cache: Any,
    ) -> None:
        """skucache_clear removes all cached SKU mappings."""
        from lib_shopify_graphql import skucache_clear, skucache_rebuild
        from lib_shopify_graphql.adapters import CachedSKUResolver

        resolver = CachedSKUResolver(mysql_sku_cache, integration_session._graphql_client)

        # First populate the cache
        skucache_rebuild(
            integration_session,
            sku_resolver=resolver,
            query=f"id:{test_product.id.split('/')[-1]}",
        )

        # Verify at least one SKU is cached
        shop_url = integration_session.get_credentials().shop_url
        variant_with_sku = next((v for v in test_product.variants if v.sku), None)
        assert variant_with_sku is not None

        cache_key = f"sku:{shop_url}:{variant_with_sku.sku}"
        assert mysql_sku_cache.get(cache_key) is not None

        # Clear the cache
        skucache_clear(mysql_sku_cache)

        # Verify cache is empty
        assert mysql_sku_cache.get(cache_key) is None


class TestSKUCacheCheckMySQL:
    """Integration tests for SKU cache consistency check with MySQL backend."""

    def test_skucache_check_consistent_after_rebuild(
        self,
        integration_session: "ShopifySession",
        test_product: "Product",
        mysql_sku_cache: Any,
    ) -> None:
        """skucache_check reports consistent after rebuild."""
        from lib_shopify_graphql import skucache_check, skucache_rebuild
        from lib_shopify_graphql.adapters import CachedSKUResolver

        resolver = CachedSKUResolver(mysql_sku_cache, integration_session._graphql_client)

        # Clear and rebuild cache for test product
        mysql_sku_cache.clear()
        product_id_num = test_product.id.split("/")[-1]
        skucache_rebuild(
            integration_session,
            sku_resolver=resolver,
            query=f"id:{product_id_num}",
        )

        # Run cache check
        result = skucache_check(
            integration_session,
            mysql_sku_cache,
            query=f"id:{product_id_num}",
        )

        # Cache should be consistent after rebuild
        assert result.is_consistent
        assert len(result.stale) == 0
        assert len(result.missing) == 0
        assert len(result.mismatched) == 0


class TestTokenCacheMySQL:
    """Integration tests for token cache operations with MySQL backend."""

    def test_tokencache_clear_removes_token(
        self,
        integration_credentials: Any,
        mysql_token_cache: Any,
    ) -> None:
        """tokencache_clear removes cached tokens."""
        from lib_shopify_graphql import tokencache_clear
        from lib_shopify_graphql.composition import create_cached_token_provider

        # Skip if using direct access token (no OAuth flow)
        if integration_credentials.access_token:
            pytest.skip("Test requires client credentials (OAuth flow)")

        assert integration_credentials.client_id is not None
        assert integration_credentials.client_secret is not None

        cached_provider = create_cached_token_provider(cache=mysql_token_cache)

        # First call caches the token
        cached_provider.obtain_token(
            integration_credentials.shop_url,
            integration_credentials.client_id,
            integration_credentials.client_secret,
        )

        # Verify token is cached
        cache_key = f"token:{integration_credentials.shop_url}:{integration_credentials.client_id}"
        assert mysql_token_cache.get(cache_key) is not None

        # Clear the cache
        tokencache_clear(mysql_token_cache)

        # Verify cache is empty
        assert mysql_token_cache.get(cache_key) is None


class TestCacheClearAllMySQL:
    """Integration tests for clearing all caches with MySQL backend."""

    def test_cache_clear_all_clears_both_caches(
        self,
        integration_session: "ShopifySession",
        test_product: "Product",
        integration_credentials: Any,
        mysql_sku_cache: Any,
        mysql_token_cache: Any,
    ) -> None:
        """cache_clear_all clears both token and SKU caches."""
        from lib_shopify_graphql import cache_clear_all, skucache_rebuild
        from lib_shopify_graphql.adapters import CachedSKUResolver
        from lib_shopify_graphql.composition import create_cached_token_provider

        # Populate SKU cache
        resolver = CachedSKUResolver(mysql_sku_cache, integration_session._graphql_client)
        skucache_rebuild(
            integration_session,
            sku_resolver=resolver,
            query=f"id:{test_product.id.split('/')[-1]}",
        )

        # Populate token cache (if using OAuth)
        if integration_credentials.client_id and integration_credentials.client_secret:
            cached_provider = create_cached_token_provider(cache=mysql_token_cache)
            cached_provider.obtain_token(
                integration_credentials.shop_url,
                integration_credentials.client_id,
                integration_credentials.client_secret,
            )

        # Verify caches have entries
        shop_url = integration_session.get_credentials().shop_url
        variant_with_sku = next((v for v in test_product.variants if v.sku), None)
        sku_key: str | None = None
        if variant_with_sku and variant_with_sku.sku:
            sku_key = f"sku:{shop_url}:{variant_with_sku.sku}"
            assert mysql_sku_cache.get(sku_key) is not None

        # Clear all caches
        cache_clear_all(token_cache=mysql_token_cache, sku_cache=mysql_sku_cache)

        # Verify both caches are empty
        if sku_key is not None:
            assert mysql_sku_cache.get(sku_key) is None

        if integration_credentials.client_id:
            token_key = f"token:{shop_url}:{integration_credentials.client_id}"
            assert mysql_token_cache.get(token_key) is None
