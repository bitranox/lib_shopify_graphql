"""Integration tests that connect to a real Shopify shop.

These tests require environment variables:
- SHOPIFY__SHOP_URL: Your shop URL (e.g., mystore.myshopify.com)
- SHOPIFY__CLIENT_ID: OAuth client ID from Dev Dashboard
- SHOPIFY__CLIENT_SECRET: OAuth client secret from Dev Dashboard

Run with: make test-slow

The test suite:
1. Automatically finds a product with a SKU in the shop
2. Duplicates that product at session start (as DRAFT, with images)
3. Runs all tests against the duplicated product
4. Deletes the duplicated product at session end
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from lib_shopify_graphql import (
    ImageSource,
    ImageUpdate,
    Product,
    ProductUpdate,
    VariantUpdate,
    adjust_inventory,
    create_image,
    delete_image,
    get_product_by_id,
    reorder_images,
    set_inventory,
    update_image,
    update_product,
    update_variant,
)

if TYPE_CHECKING:
    from pathlib import Path

    from lib_shopify_graphql import ShopifyCredentials, ShopifySession


# =============================================================================
# Product Read Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestProductRead:
    """Integration tests for reading products."""

    def test_get_product_by_id_returns_product(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """get_product_by_id returns a valid Product."""
        product = get_product_by_id(integration_session, test_product.id)

        assert isinstance(product, Product)
        assert product.id == test_product.id

    def test_product_has_title(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """Duplicated product has the expected title prefix."""
        product = get_product_by_id(integration_session, test_product.id)

        assert product.title.startswith("[TEST]")

    def test_product_has_variants(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """Duplicated product has at least one variant."""
        product = get_product_by_id(integration_session, test_product.id)

        assert len(product.variants) > 0

    def test_product_is_draft(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """Duplicated product is in DRAFT status."""
        from lib_shopify_graphql import ProductStatus

        product = get_product_by_id(integration_session, test_product.id)

        assert product.status == ProductStatus.DRAFT

    def test_product_has_handle(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """Duplicated product has a valid handle."""
        product = get_product_by_id(integration_session, test_product.id)

        assert product.handle is not None
        assert len(product.handle) > 0


# =============================================================================
# Product Listing Tests (Pagination Functions)
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestProductListing:
    """Integration tests for product listing with pagination."""

    def test_list_products_returns_list(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """list_products returns a list of Product objects."""
        from lib_shopify_graphql import list_products

        products = list_products(integration_session, max_products=10)

        assert isinstance(products, list)
        assert len(products) > 0
        assert all(isinstance(p, Product) for p in products)

    def test_list_products_finds_test_product(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """list_products can find the test product."""
        from lib_shopify_graphql import list_products

        # Filter by the test product ID
        product_id_numeric = test_product.id.split("/")[-1]
        products = list_products(
            integration_session,
            query=f"id:{product_id_numeric}",
        )

        assert len(products) == 1
        assert products[0].id == test_product.id

    def test_list_products_max_products_limits_results(
        self,
        integration_session: "ShopifySession",
    ) -> None:
        """max_products parameter limits the number of returned products."""
        from lib_shopify_graphql import list_products

        products = list_products(integration_session, max_products=2)

        assert len(products) <= 2

    def test_list_products_query_filter_works(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """Query filter correctly filters products."""
        from lib_shopify_graphql import list_products

        # Test product has status:DRAFT
        products = list_products(
            integration_session,
            query="status:draft",
            max_products=100,
        )

        # Should find at least our test product
        test_product_ids = [p.id for p in products]
        assert test_product.id in test_product_ids


@pytest.mark.integration
@pytest.mark.local_only
class TestIterProducts:
    """Integration tests for iter_products iterator."""

    def test_iter_products_yields_products(
        self,
        integration_session: "ShopifySession",
    ) -> None:
        """iter_products yields Product objects."""
        from lib_shopify_graphql import iter_products

        # Take first 5 products
        products: list[Product] = []
        for i, product in enumerate(iter_products(integration_session)):
            products.append(product)
            if i >= 4:
                break

        assert len(products) > 0
        assert all(isinstance(p, Product) for p in products)

    def test_iter_products_finds_test_product(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """iter_products can find the test product with query filter."""
        from lib_shopify_graphql import iter_products

        product_id_numeric = test_product.id.split("/")[-1]
        products = list(
            iter_products(
                integration_session,
                query=f"id:{product_id_numeric}",
            )
        )

        assert len(products) == 1
        assert products[0].id == test_product.id

    def test_iter_products_is_lazy(
        self,
        integration_session: "ShopifySession",
    ) -> None:
        """iter_products returns an iterator, not a list."""
        from collections.abc import Iterator

        from lib_shopify_graphql import iter_products

        result = iter_products(integration_session)

        assert isinstance(result, Iterator)
        assert not isinstance(result, list)


@pytest.mark.integration
@pytest.mark.local_only
class TestListProductsPaginated:
    """Integration tests for list_products_paginated (manual pagination)."""

    def test_list_products_paginated_returns_connection(
        self,
        integration_session: "ShopifySession",
    ) -> None:
        """list_products_paginated returns a ProductConnection."""
        from lib_shopify_graphql import ProductConnection, list_products_paginated

        result = list_products_paginated(integration_session, first=10)

        assert isinstance(result, ProductConnection)
        assert hasattr(result, "products")
        assert hasattr(result, "page_info")

    def test_list_products_paginated_page_info(
        self,
        integration_session: "ShopifySession",
    ) -> None:
        """list_products_paginated includes valid page_info."""
        from lib_shopify_graphql import list_products_paginated

        result = list_products_paginated(integration_session, first=5)

        assert result.page_info is not None
        # has_next_page should be a boolean
        assert isinstance(result.page_info.has_next_page, bool)

    def test_list_products_paginated_cursor_pagination(
        self,
        integration_session: "ShopifySession",
    ) -> None:
        """list_products_paginated cursor pagination works correctly."""
        from lib_shopify_graphql import list_products_paginated

        # Get first page
        page1 = list_products_paginated(integration_session, first=2)

        if not page1.page_info.has_next_page:
            pytest.skip("Shop has fewer than 3 products - cannot test pagination")

        # Get second page using cursor
        page2 = list_products_paginated(
            integration_session,
            first=2,
            after=page1.page_info.end_cursor,
        )

        # Pages should have different products (assuming shop has > 2 products)
        page1_ids = {p.id for p in page1.products}
        page2_ids = {p.id for p in page2.products}

        # If there are products on page 2, they should be different from page 1
        if page2.products:
            assert page1_ids.isdisjoint(page2_ids), "Second page should have different products"

    def test_list_products_paginated_query_filter(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """list_products_paginated query filter works."""
        from lib_shopify_graphql import list_products_paginated

        product_id_numeric = test_product.id.split("/")[-1]
        result = list_products_paginated(
            integration_session,
            first=10,
            query=f"id:{product_id_numeric}",
        )

        assert len(result.products) == 1
        assert result.products[0].id == test_product.id


# =============================================================================
# Product Update Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestProductUpdate:
    """Integration tests for updating products."""

    def test_update_product_description(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """update_product can change the description."""
        new_description = "<p>Updated description for integration test</p>"

        updated = update_product(
            integration_session,
            test_product.id,
            ProductUpdate(description_html=new_description),
        )

        assert updated.description_html == new_description

    def test_update_product_vendor(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """update_product can change the vendor."""
        new_vendor = "Integration Test Vendor"

        updated = update_product(
            integration_session,
            test_product.id,
            ProductUpdate(vendor=new_vendor),
        )

        assert updated.vendor == new_vendor

    def test_update_product_tags(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """update_product can update tags."""
        new_tags = ["integration-test", "automated", "temp"]

        updated = update_product(
            integration_session,
            test_product.id,
            ProductUpdate(tags=new_tags),
        )

        assert set(updated.tags) == set(new_tags)


# =============================================================================
# Variant Update Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestVariantUpdate:
    """Integration tests for updating variants."""

    def test_update_variant_price(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """update_variant can change the price."""
        variant = test_product.variants[0]
        new_price = Decimal("99.99")

        updated = update_variant(
            integration_session,
            variant.id,
            VariantUpdate(price=new_price),
            product_id=test_product.id,
        )

        assert updated.price.amount == new_price

    def test_update_variant_compare_at_price(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """update_variant can set compare_at_price for sales."""
        variant = test_product.variants[0]
        compare_price = Decimal("149.99")

        updated = update_variant(
            integration_session,
            variant.id,
            VariantUpdate(compare_at_price=compare_price),
            product_id=test_product.id,
        )

        assert updated.compare_at_price is not None
        assert updated.compare_at_price.amount == compare_price


# =============================================================================
# Inventory Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestInventory:
    """Integration tests for inventory operations."""

    def test_set_inventory_sets_quantity(
        self,
        integration_session: ShopifySession,
        test_product: Product,
        primary_location: str,
    ) -> None:
        """set_inventory sets absolute quantity."""
        variant = test_product.variants[0]

        level = set_inventory(
            integration_session,
            variant.id,
            quantity=10,
            location_id=primary_location,
        )

        assert level.available == 10

    def test_set_inventory_to_zero(
        self,
        integration_session: ShopifySession,
        test_product: Product,
        primary_location: str,
    ) -> None:
        """set_inventory can set quantity to zero."""
        variant = test_product.variants[0]

        level = set_inventory(
            integration_session,
            variant.id,
            quantity=0,
            location_id=primary_location,
        )

        assert level.available == 0

    def test_adjust_inventory_increases(
        self,
        integration_session: ShopifySession,
        test_product: Product,
        primary_location: str,
    ) -> None:
        """adjust_inventory can increase quantity."""
        variant = test_product.variants[0]

        # First set to known value
        set_inventory(integration_session, variant.id, quantity=10, location_id=primary_location)

        # Then adjust up
        level = adjust_inventory(
            integration_session,
            variant.id,
            delta=5,
            location_id=primary_location,
        )

        # adjust_inventory confirms the operation but doesn't return actual quantity
        assert level.inventory_item_id is not None
        assert level.location_id == primary_location
        assert level.available is None  # Shopify doesn't return resulting quantity

    def test_adjust_inventory_decreases(
        self,
        integration_session: ShopifySession,
        test_product: Product,
        primary_location: str,
    ) -> None:
        """adjust_inventory can decrease quantity."""
        variant = test_product.variants[0]

        # First set to known value
        set_inventory(integration_session, variant.id, quantity=20, location_id=primary_location)

        # Then adjust down
        level = adjust_inventory(
            integration_session,
            variant.id,
            delta=-5,
            location_id=primary_location,
        )

        # adjust_inventory confirms the operation but doesn't return actual quantity
        assert level.inventory_item_id is not None
        assert level.location_id == primary_location
        assert level.available is None  # Shopify doesn't return resulting quantity


# =============================================================================
# SKU Cache Rebuild Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestSKUCacheRebuild:
    """Integration tests for SKU cache rebuild operations."""

    def test_skucache_rebuild_returns_variant_count(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """skucache_rebuild returns count of cached variants."""
        from pathlib import Path
        import tempfile

        from lib_shopify_graphql import skucache_rebuild
        from lib_shopify_graphql.composition import create_json_cache, create_sku_resolver

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "sku_cache.json"
            cache = create_json_cache(cache_path)
            resolver = create_sku_resolver(cache=cache, graphql_client=integration_session._graphql_client)

            # Rebuild cache for all products (filtered to just test product)
            count = skucache_rebuild(
                integration_session,
                sku_resolver=resolver,
                query=f"id:{test_product.id.split('/')[-1]}",  # Filter to test product only
            )

            # Should have cached at least the variants from test_product
            assert count >= len(test_product.variants)

    def test_skucache_rebuild_populates_sku_mappings(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """skucache_rebuild populates SKU-to-GID mappings in cache."""
        from pathlib import Path
        import tempfile

        from lib_shopify_graphql import skucache_rebuild
        from lib_shopify_graphql.composition import create_json_cache, create_sku_resolver

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "sku_cache.json"
            cache = create_json_cache(cache_path)
            resolver = create_sku_resolver(cache=cache, graphql_client=integration_session._graphql_client)

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
                    # Cache key format: sku:{shop_url}:{sku}
                    cache_key = f"sku:{shop_url}:{variant.sku}"
                    cached_value = cache.get(cache_key)
                    assert cached_value is not None, f"SKU {variant.sku} not cached"

    def test_skucache_clear_removes_all_entries(
        self,
        integration_session: ShopifySession,
        test_product: Product,
    ) -> None:
        """skucache_clear removes all cached SKU mappings."""
        from pathlib import Path
        import tempfile

        from lib_shopify_graphql import skucache_clear, skucache_rebuild
        from lib_shopify_graphql.composition import create_json_cache, create_sku_resolver

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "sku_cache.json"
            cache = create_json_cache(cache_path)
            resolver = create_sku_resolver(cache=cache, graphql_client=integration_session._graphql_client)

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
            assert cache.get(cache_key) is not None

            # Clear the cache
            skucache_clear(cache)

            # Verify cache is empty
            assert cache.get(cache_key) is None


# =============================================================================
# Token Cache Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestTokenCache:
    """Integration tests for token cache operations."""

    def test_cached_token_provider_caches_token(
        self,
        integration_credentials: "ShopifyCredentials | None",
    ) -> None:
        """CachedTokenProvider caches the token after first fetch."""
        from pathlib import Path
        import tempfile

        from lib_shopify_graphql.composition import (
            create_cached_token_provider,
            create_json_cache,
        )

        # Skip if no credentials available
        if integration_credentials is None:
            pytest.skip("Test requires Shopify credentials")

        # Skip if using direct access token (no OAuth flow)
        if integration_credentials.access_token:
            pytest.skip("Test requires client credentials (OAuth flow)")

        # After the skip check, we know these are non-None
        assert integration_credentials.client_id is not None
        assert integration_credentials.client_secret is not None

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "token_cache.json"
            cache = create_json_cache(cache_path)
            cached_provider = create_cached_token_provider(cache=cache)

            # First call - fetches token from Shopify
            token1, expiry1 = cached_provider.obtain_token(
                integration_credentials.shop_url,
                integration_credentials.client_id,
                integration_credentials.client_secret,
            )

            assert token1 is not None
            assert expiry1 is not None

            # Token should be cached
            cache_key = f"token:{integration_credentials.shop_url}:{integration_credentials.client_id}"
            cached_value = cache.get(cache_key)
            assert cached_value is not None

    def test_tokencache_clear_forces_refetch(
        self,
        integration_credentials: "ShopifyCredentials | None",
    ) -> None:
        """Clearing token cache forces a new token fetch."""
        from pathlib import Path
        import tempfile

        from lib_shopify_graphql import tokencache_clear
        from lib_shopify_graphql.composition import (
            create_cached_token_provider,
            create_json_cache,
        )

        # Skip if no credentials available
        if integration_credentials is None:
            pytest.skip("Test requires Shopify credentials")

        # Skip if using direct access token (no OAuth flow)
        if integration_credentials.access_token:
            pytest.skip("Test requires client credentials (OAuth flow)")

        # After the skip check, we know these are non-None
        assert integration_credentials.client_id is not None
        assert integration_credentials.client_secret is not None

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "token_cache.json"
            cache = create_json_cache(cache_path)
            cached_provider = create_cached_token_provider(cache=cache)

            # First call - caches the token
            cached_provider.obtain_token(
                integration_credentials.shop_url,
                integration_credentials.client_id,
                integration_credentials.client_secret,
            )

            # Verify token is cached
            cache_key = f"token:{integration_credentials.shop_url}:{integration_credentials.client_id}"
            assert cache.get(cache_key) is not None

            # Clear the cache
            tokencache_clear(cache)

            # Verify cache is empty
            assert cache.get(cache_key) is None

            # Next call should still work (fetches new token)
            token2, _ = cached_provider.obtain_token(
                integration_credentials.shop_url,
                integration_credentials.client_id,
                integration_credentials.client_secret,
            )
            assert token2 is not None

    def test_cache_clear_all_clears_both_caches(
        self,
        integration_session: ShopifySession,
        test_product: Product,
        integration_credentials: "ShopifyCredentials",
    ) -> None:
        """cache_clear_all clears both token and SKU caches."""
        from pathlib import Path
        import tempfile

        from lib_shopify_graphql import cache_clear_all, skucache_rebuild
        from lib_shopify_graphql.composition import (
            create_cached_token_provider,
            create_json_cache,
            create_sku_resolver,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            token_cache_path = Path(tmpdir) / "token_cache.json"
            sku_cache_path = Path(tmpdir) / "sku_cache.json"
            token_cache = create_json_cache(token_cache_path)
            sku_cache = create_json_cache(sku_cache_path)

            # Populate SKU cache
            resolver = create_sku_resolver(cache=sku_cache, graphql_client=integration_session._graphql_client)
            skucache_rebuild(
                integration_session,
                sku_resolver=resolver,
                query=f"id:{test_product.id.split('/')[-1]}",
            )

            # Populate token cache (if using OAuth)
            if integration_credentials.client_id and integration_credentials.client_secret:
                cached_provider = create_cached_token_provider(cache=token_cache)
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
                assert sku_cache.get(sku_key) is not None

            # Clear all caches
            cache_clear_all(token_cache=token_cache, sku_cache=sku_cache)

            # Verify both caches are empty
            if sku_key is not None:
                assert sku_cache.get(sku_key) is None

            if integration_credentials.client_id:
                token_key = f"token:{shop_url}:{integration_credentials.client_id}"
                assert token_cache.get(token_key) is None


# =============================================================================
# Image Operations Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestImageOperations:
    """Integration tests for product image operations."""

    def test_create_image_from_url(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """create_image can add an image from an external URL."""
        # Skip if product has no images to use as source URL
        if not test_product.images:
            pytest.skip("Test product has no images")

        # Use the existing image URL as source (Shopify will re-fetch it)
        source_url = test_product.images[0].url
        alt_text = "Integration test image from URL"

        # create_image returns ImageCreateSuccess directly (not ImageCreateResult)
        created = create_image(
            integration_session,
            test_product.id,
            ImageSource(url=source_url, alt_text=alt_text),
        )

        assert created.image_id is not None
        # Status may be PROCESSING or READY depending on timing
        assert created.status in ("PROCESSING", "READY", "UPLOADED")

    def test_create_image_from_file(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """create_image can upload an image from a local file."""
        import tempfile
        from pathlib import Path

        import httpx

        # Skip if product has no images to download
        if not test_product.images:
            pytest.skip("Test product has no images")

        # Download existing image to temp file
        source_url = test_product.images[0].url
        with httpx.Client() as client:
            response = client.get(source_url)
            response.raise_for_status()
            image_data = response.content

        # Save to temp file with proper extension
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_data)
            tmp_path = Path(tmp.name)

        try:
            # create_image returns ImageCreateSuccess directly
            created = create_image(
                integration_session,
                test_product.id,
                ImageSource(file_path=tmp_path, alt_text="Uploaded from file"),
            )

            assert created.image_id is not None
            assert created.status in ("PROCESSING", "READY", "UPLOADED")
        finally:
            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

    def test_update_image_alt_text(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """update_image can change the alt text of an image."""
        # Skip if product has no media (use media for proper GID format)
        if not test_product.media:
            pytest.skip("Test product has no media")

        # Use media[0].id which has the correct MediaImage GID format
        media = test_product.media[0]
        new_alt_text = "Updated alt text for integration test"

        updated = update_image(
            integration_session,
            test_product.id,
            media.id,
            ImageUpdate(alt_text=new_alt_text),
        )

        assert updated.alt_text == new_alt_text

    def test_delete_image(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """delete_image can remove an image from a product."""
        # Skip if product has no images
        if not test_product.images:
            pytest.skip("Test product has no images")

        # First, create a new image to delete (don't delete original)
        source_url = test_product.images[0].url
        created = create_image(
            integration_session,
            test_product.id,
            ImageSource(url=source_url, alt_text="Temp image to delete"),
        )

        new_image_id = created.image_id

        # Now delete the newly created image
        delete_result = delete_image(
            integration_session,
            test_product.id,
            new_image_id,
        )

        # Verify image was deleted (check either image_ids or media_ids)
        deleted_ids = delete_result.deleted_image_ids + delete_result.deleted_media_ids
        assert len(deleted_ids) > 0 or new_image_id in deleted_ids

    def test_reorder_images(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """reorder_images can change the order of product images."""
        # Skip if product has no media at all (use media for proper GID format)
        if not test_product.media:
            pytest.skip("Test product has no media")

        # If only 1 media item, upload a second one first
        if len(test_product.media) < 2:
            # Get URL from images (for URL-based upload)
            if not test_product.images:
                pytest.skip("Test product has no images to copy")
            source_url = test_product.images[0].url
            created = create_image(
                integration_session,
                test_product.id,
                ImageSource(url=source_url, alt_text="Second image for reorder test"),
            )

            # Build media list with original + new image
            # The created image returns a MediaImage GID
            new_image_id = created.image_id
            media_ids = [test_product.media[0].id, new_image_id]
        else:
            media_ids = [m.id for m in test_product.media]

        # Reverse the order
        reversed_ids = list(reversed(media_ids))

        result = reorder_images(
            integration_session,
            test_product.id,
            reversed_ids,
        )

        # Reorder is async, so we just verify the operation was accepted
        assert result.product_id == test_product.id
        # job_id may be None if it completed synchronously


# =============================================================================
# CLI Command Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.local_only
class TestCLICommands:
    """Integration tests for CLI commands."""

    def test_cli_10_get_product(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """CLI get-product returns product data as JSON."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["get-product", test_product.id, "--format", "json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == test_product.id
        assert "[TEST]" in data["title"]

    def test_cli_11_update_product_title(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """CLI update-product can update the title."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        new_title = f"[TEST] CLI Updated Title {test_product.id[-8:]}"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["update-product", test_product.id, "--title", new_title, "--format", "json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == new_title

    def test_cli_12_update_product_vendor(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """CLI update-product can update the vendor."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        new_vendor = "CLI Test Vendor"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["update-product", test_product.id, "--vendor", new_vendor, "--format", "json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["vendor"] == new_vendor

    def test_cli_20_add_image_from_url(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """CLI add-image can add an image from URL."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        # Skip if product has no images to copy URL from
        if not test_product.images:
            pytest.skip("Test product has no images")

        source_url = test_product.images[0].url

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "add-image",
                test_product.id,
                "--url",
                source_url,
                "--alt",
                "CLI test image",
                "--format",
                "json",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # add-image returns {"images": [...]}
        assert len(data["images"]) == 1
        assert data["images"][0]["image_id"] is not None

    def test_cli_21_update_image(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """CLI update-image can update alt text."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        # Skip if product has no media
        if not test_product.media:
            pytest.skip("Test product has no media")

        media = test_product.media[0]
        new_alt = "CLI updated alt text"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "update-image",
                test_product.id,
                media.id,
                "--alt",
                new_alt,
                "--format",
                "json",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["alt_text"] == new_alt

    def test_cli_22_delete_image(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """CLI delete-image can delete an image."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        # Skip if product has no images
        if not test_product.images:
            pytest.skip("Test product has no images")

        # First create an image to delete
        source_url = test_product.images[0].url
        created = create_image(
            integration_session,
            test_product.id,
            ImageSource(url=source_url, alt_text="CLI temp image"),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "delete-image",
                test_product.id,
                created.image_id,
                "--format",
                "json",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["product_id"] == test_product.id

    def test_cli_23_reorder_images(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
    ) -> None:
        """CLI reorder-images can reorder product images."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        # Skip if product has no media
        if not test_product.media:
            pytest.skip("Test product has no media")

        # If only 1 media, create a second one
        if len(test_product.media) < 2:
            if not test_product.images:
                pytest.skip("Test product has no images to copy")
            source_url = test_product.images[0].url
            created = create_image(
                integration_session,
                test_product.id,
                ImageSource(url=source_url, alt_text="CLI second image"),
            )
            media_ids = [test_product.media[0].id, created.image_id]
        else:
            media_ids = [m.id for m in test_product.media[:2]]

        # Reverse the order
        order_str = ",".join(reversed(media_ids))

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "reorder-images",
                test_product.id,
                "--order",
                order_str,
                "--format",
                "json",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["product_id"] == test_product.id

    def test_cli_30_health(
        self,
        integration_credentials: "ShopifyCredentials | None",
    ) -> None:
        """CLI health command checks API connectivity."""
        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        if integration_credentials is None:
            pytest.skip("Integration credentials not configured")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["health"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "successful" in result.output.lower() or "healthy" in result.output.lower() or "ok" in result.output.lower()

    def test_cli_31_info(self) -> None:
        """CLI info command displays package information."""
        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["info"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "lib_shopify_graphql" in result.output or "lib-shopify-graphql" in result.output

    def test_cli_32_config(self) -> None:
        """CLI config command displays configuration."""
        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "--format", "json"], catch_exceptions=False)

        assert result.exit_code == 0
        # Should output valid JSON
        import json

        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_cli_00_skucache_clear(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI skucache-clear clears the SKU cache."""
        from click.testing import CliRunner

        from lib_shopify_graphql import skucache_rebuild
        from lib_shopify_graphql.cli import cli
        from lib_shopify_graphql.composition import create_json_cache, create_sku_resolver

        # Create a temp cache file with content
        cache_path = tmp_path / "sku_cache.json"
        cache = create_json_cache(cache_path)
        resolver = create_sku_resolver(cache=cache, graphql_client=integration_session._graphql_client)

        # Populate cache
        skucache_rebuild(
            integration_session,
            sku_resolver=resolver,
            query=f"id:{test_product.id.split('/')[-1]}",
        )

        # Verify cache has content
        shop_url = integration_session.get_credentials().shop_url
        variant_with_sku = next((v for v in test_product.variants if v.sku), None)
        assert variant_with_sku is not None
        cache_key = f"sku:{shop_url}:{variant_with_sku.sku}"
        assert cache.get(cache_key) is not None

        # Create env file with cache config pointing to our temp cache
        env_file = tmp_path / ".env"
        env_file.write_text(f"SHOPIFY__SKU_CACHE__ENABLED=true\nSHOPIFY__SKU_CACHE__BACKEND=json\nSHOPIFY__SKU_CACHE__JSON_PATH={cache_path}\n")
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        result = runner.invoke(cli, ["skucache-clear"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "cleared" in result.output.lower() or "✓" in result.output

    def test_cli_01_tokencache_clear(
        self,
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI tokencache-clear clears the token cache."""
        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli
        from lib_shopify_graphql.composition import create_json_cache

        # Create a temp cache file with content
        cache_path = tmp_path / "token_cache.json"
        cache = create_json_cache(cache_path)
        cache.set("token:test.myshopify.com:test_client", '{"token": "test_token"}')

        # Create env file with cache config
        env_file = tmp_path / ".env"
        env_file.write_text(f"SHOPIFY__TOKEN_CACHE__ENABLED=true\nSHOPIFY__TOKEN_CACHE__BACKEND=json\nSHOPIFY__TOKEN_CACHE__JSON_PATH={cache_path}\n")
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        result = runner.invoke(cli, ["tokencache-clear"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "cleared" in result.output.lower() or "✓" in result.output

    def test_cli_02_cache_clear_all(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI cache-clear-all clears both token and SKU caches."""
        from click.testing import CliRunner

        from lib_shopify_graphql import skucache_rebuild
        from lib_shopify_graphql.cli import cli
        from lib_shopify_graphql.composition import create_json_cache, create_sku_resolver

        # Create temp cache files
        sku_cache_path = tmp_path / "sku_cache.json"
        token_cache_path = tmp_path / "token_cache.json"
        sku_cache = create_json_cache(sku_cache_path)
        token_cache = create_json_cache(token_cache_path)

        # Populate SKU cache
        resolver = create_sku_resolver(cache=sku_cache, graphql_client=integration_session._graphql_client)
        skucache_rebuild(
            integration_session,
            sku_resolver=resolver,
            query=f"id:{test_product.id.split('/')[-1]}",
        )

        # Populate token cache
        token_cache.set("token:test.myshopify.com:test_client", '{"token": "test_token"}')

        # Create env file with cache config
        env_file = tmp_path / ".env"
        env_file.write_text(
            f"SHOPIFY__SKU_CACHE__ENABLED=true\n"
            f"SHOPIFY__SKU_CACHE__BACKEND=json\n"
            f"SHOPIFY__SKU_CACHE__JSON_PATH={sku_cache_path}\n"
            f"SHOPIFY__TOKEN_CACHE__ENABLED=true\n"
            f"SHOPIFY__TOKEN_CACHE__BACKEND=json\n"
            f"SHOPIFY__TOKEN_CACHE__JSON_PATH={token_cache_path}\n"
        )
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        result = runner.invoke(cli, ["cache-clear-all"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "cleared" in result.output.lower() or "✓" in result.output

    def test_cli_03_skucache_rebuild(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI skucache-rebuild rebuilds the SKU cache."""
        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli
        from lib_shopify_graphql.composition import create_json_cache

        # Create empty temp cache file
        sku_cache_path = tmp_path / "sku_cache.json"
        create_json_cache(sku_cache_path)  # Initialize empty cache

        # Get credentials from session
        creds = integration_session.get_credentials()

        # Create env file with credentials and cache config
        env_file = tmp_path / ".env"
        env_lines = [
            f"SHOPIFY__SHOP_URL={creds.shop_url}",
            "SHOPIFY__SKU_CACHE__ENABLED=true",
            "SHOPIFY__SKU_CACHE__BACKEND=json",
            f"SHOPIFY__SKU_CACHE__JSON_PATH={sku_cache_path}",
        ]
        if creds.client_id and creds.client_secret:
            env_lines.extend(
                [
                    f"SHOPIFY__CLIENT_ID={creds.client_id}",
                    f"SHOPIFY__CLIENT_SECRET={creds.client_secret}",
                ]
            )
        elif creds.access_token:
            env_lines.append(f"SHOPIFY__ACCESS_TOKEN={creds.access_token}")

        env_file.write_text("\n".join(env_lines) + "\n")
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        # Query for just the test product to make it fast
        result = runner.invoke(
            cli,
            ["skucache-rebuild", "--query", f"id:{test_product.id.split('/')[-1]}"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "rebuilt" in result.output.lower() or "cached" in result.output.lower()

    def test_cli_40_create_product(
        self,
        integration_session: "ShopifySession",
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI create-product creates a product and we clean it up."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql import delete_product
        from lib_shopify_graphql.cli import cli

        # Get credentials from session
        creds = integration_session.get_credentials()

        # Create env file with credentials
        env_file = tmp_path / ".env"
        env_lines = [f"SHOPIFY__SHOP_URL={creds.shop_url}"]
        if creds.client_id and creds.client_secret:
            env_lines.extend(
                [
                    f"SHOPIFY__CLIENT_ID={creds.client_id}",
                    f"SHOPIFY__CLIENT_SECRET={creds.client_secret}",
                ]
            )
        elif creds.access_token:
            env_lines.append(f"SHOPIFY__ACCESS_TOKEN={creds.access_token}")

        env_file.write_text("\n".join(env_lines) + "\n")
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "create-product",
                "--title",
                "[TEST] CLI Integration Test Product",
                "--status",
                "draft",  # lowercase to test case-insensitivity
                "--format",
                "json",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "[TEST] CLI Integration Test Product"
        assert data["status"] == "DRAFT"

        # Cleanup: delete the created product
        created_product_id = data["id"]
        delete_product(integration_session, created_product_id)

    def test_cli_41_duplicate_product(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI duplicate-product duplicates a product and we clean it up."""
        import json

        from click.testing import CliRunner

        from lib_shopify_graphql import delete_product
        from lib_shopify_graphql.cli import cli

        # Get credentials from session
        creds = integration_session.get_credentials()

        # Create env file with credentials
        env_file = tmp_path / ".env"
        env_lines = [f"SHOPIFY__SHOP_URL={creds.shop_url}"]
        if creds.client_id and creds.client_secret:
            env_lines.extend(
                [
                    f"SHOPIFY__CLIENT_ID={creds.client_id}",
                    f"SHOPIFY__CLIENT_SECRET={creds.client_secret}",
                ]
            )
        elif creds.access_token:
            env_lines.append(f"SHOPIFY__ACCESS_TOKEN={creds.access_token}")

        env_file.write_text("\n".join(env_lines) + "\n")
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "duplicate-product",
                test_product.id,
                "[TEST] CLI Duplicated Product",
                "--status",
                "draft",  # lowercase to test case-insensitivity
                "--format",
                "json",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "[TEST] CLI Duplicated Product"
        assert data["status"] == "DRAFT"

        # Cleanup: delete the duplicated product
        duplicated_product_id = data["id"]
        delete_product(integration_session, duplicated_product_id)

    def test_cli_42_delete_product(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI delete-product deletes a product.

        First duplicates a product via API, then deletes it via CLI.
        """
        import json
        import uuid

        from click.testing import CliRunner

        from lib_shopify_graphql import VariantUpdate, duplicate_product, update_variant
        from lib_shopify_graphql.cli import cli
        from lib_shopify_graphql.models import ProductStatus

        # First, duplicate the test product via API (so we have something to delete)
        test_title = f"[TEST] Product to Delete - {uuid.uuid4().hex[:8]}"
        result_dup = duplicate_product(
            integration_session,
            test_product.id,
            test_title,
            include_images=False,  # Faster without images
            new_status=ProductStatus.DRAFT,
        )

        product_to_delete = result_dup.new_product

        # Assign a SKU to the first variant
        test_sku = f"TEST-DELETE-{uuid.uuid4().hex[:8]}"
        if product_to_delete.variants:
            update_variant(
                integration_session,
                product_to_delete.variants[0].id,
                VariantUpdate(sku=test_sku),
                product_id=product_to_delete.id,
            )

        # Get credentials from session
        creds = integration_session.get_credentials()

        # Create env file with credentials
        env_file = tmp_path / ".env"
        env_lines = [f"SHOPIFY__SHOP_URL={creds.shop_url}"]
        if creds.client_id and creds.client_secret:
            env_lines.extend(
                [
                    f"SHOPIFY__CLIENT_ID={creds.client_id}",
                    f"SHOPIFY__CLIENT_SECRET={creds.client_secret}",
                ]
            )
        elif creds.access_token:
            env_lines.append(f"SHOPIFY__ACCESS_TOKEN={creds.access_token}")

        env_file.write_text("\n".join(env_lines) + "\n")
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "delete-product",
                product_to_delete.id,
                "--force",  # Skip confirmation prompt
                "--format",
                "json",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["deleted_product_id"] == product_to_delete.id
        assert data["success"] is True

    def test_cli_91_skucache_check_api(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
        tmp_path: "Path",
    ) -> None:
        """Verify SKU cache consistency after all other tests.

        This test:
        1. Creates a fresh JSON cache
        2. Rebuilds the cache from Shopify for the test product
        3. Runs skucache_check to verify the cache matches Shopify
        4. Asserts the cache is fully consistent
        """
        from lib_shopify_graphql import skucache_check, skucache_rebuild
        from lib_shopify_graphql.adapters import CachedSKUResolver
        from lib_shopify_graphql.composition import create_json_cache

        # Create temp cache and rebuild for test product
        cache_path = tmp_path / "sku_cache.json"
        cache = create_json_cache(cache_path)
        resolver = CachedSKUResolver(cache, integration_session._graphql_client)

        # Rebuild cache for test product only
        product_id_num = test_product.id.split("/")[-1]
        skucache_rebuild(
            integration_session,
            sku_resolver=resolver,
            query=f"id:{product_id_num}",
        )

        # Run cache check
        result = skucache_check(
            integration_session,
            cache,
            query=f"id:{product_id_num}",
        )

        # Cache should be consistent after rebuild
        assert result.is_consistent, f"Cache inconsistent: stale={result.stale}, missing={result.missing}, mismatched={result.mismatched}"
        assert result.valid >= 0
        assert len(result.stale) == 0
        assert len(result.missing) == 0
        assert len(result.mismatched) == 0

    def test_cli_50_test_limits(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI test-limits checks for GraphQL limit truncation."""
        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli

        # Get credentials from session
        creds = integration_session.get_credentials()

        # Create env file with credentials
        env_file = tmp_path / ".env"
        env_lines = [f"SHOPIFY__SHOP_URL={creds.shop_url}"]
        if creds.client_id and creds.client_secret:
            env_lines.extend(
                [
                    f"SHOPIFY__CLIENT_ID={creds.client_id}",
                    f"SHOPIFY__CLIENT_SECRET={creds.client_secret}",
                ]
            )
        elif creds.access_token:
            env_lines.append(f"SHOPIFY__ACCESS_TOKEN={creds.access_token}")

        env_file.write_text("\n".join(env_lines) + "\n")
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        # Limit to just 1 product for speed
        product_id_num = test_product.id.split("/")[-1]
        result = runner.invoke(
            cli,
            ["test-limits", "-n", "1", "--query", f"id:{product_id_num}"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # Should show some output about limits
        assert "limit" in result.output.lower() or "product" in result.output.lower()

    def test_cli_90_skucache_check(
        self,
        integration_session: "ShopifySession",
        test_product: Product,
        tmp_path: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """CLI skucache-check verifies cache consistency."""
        from click.testing import CliRunner

        from lib_shopify_graphql.cli import cli
        from lib_shopify_graphql.composition import create_json_cache

        # Create temp cache file and pre-populate via rebuild
        sku_cache_path = tmp_path / "sku_cache.json"
        create_json_cache(sku_cache_path)

        # Get credentials from session
        creds = integration_session.get_credentials()

        # Create env file with credentials and cache config
        env_file = tmp_path / ".env"
        env_lines = [
            f"SHOPIFY__SHOP_URL={creds.shop_url}",
            "SHOPIFY__SKU_CACHE__ENABLED=true",
            "SHOPIFY__SKU_CACHE__BACKEND=json",
            f"SHOPIFY__SKU_CACHE__JSON_PATH={sku_cache_path}",
        ]
        if creds.client_id and creds.client_secret:
            env_lines.extend(
                [
                    f"SHOPIFY__CLIENT_ID={creds.client_id}",
                    f"SHOPIFY__CLIENT_SECRET={creds.client_secret}",
                ]
            )
        elif creds.access_token:
            env_lines.append(f"SHOPIFY__ACCESS_TOKEN={creds.access_token}")

        env_file.write_text("\n".join(env_lines) + "\n")
        monkeypatch.chdir(tmp_path)

        # Clear config cache to pick up new settings
        from lib_shopify_graphql.config import get_config

        get_config.cache_clear()

        runner = CliRunner()
        product_id_num = test_product.id.split("/")[-1]

        # First rebuild the cache
        result = runner.invoke(
            cli,
            ["skucache-rebuild", "--query", f"id:{product_id_num}"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # Now check cache consistency
        result = runner.invoke(
            cli,
            ["skucache-check", "--query", f"id:{product_id_num}"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # Should indicate cache is consistent or show stats
        output_lower = result.output.lower()
        assert "consistent" in output_lower or "valid" in output_lower or "check" in output_lower
