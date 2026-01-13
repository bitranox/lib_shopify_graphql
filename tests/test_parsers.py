"""Parser tests: verifying GraphQL response parsing behavior.

Tests use real data structures to validate actual parsing behavior.
Each test reads like plain English.

Coverage:
- DateTime parsing from ISO strings
- Money parsing from amount strings
- Image parsing from response data
- Inventory policy parsing
- Metafield type parsing with fallback
- SEO, options, selected options parsing
- Price range parsing
- Product and variant parsing
- Input builders for mutations
- User error parsing
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from lib_shopify_graphql.adapters.parsers import (
    VariantMutationResult,
    build_product_input,
    build_variant_input,
    parse_datetime,
    parse_graphql_errors,
    parse_image,
    parse_inventory_level,
    parse_inventory_policy,
    parse_metafield_type,
    parse_metafields,
    parse_money,
    parse_options,
    parse_price_range,
    parse_product,
    parse_selected_options,
    parse_seo,
    parse_user_errors,
    parse_variant,
    parse_variant_from_mutation,
)
from lib_shopify_graphql.models import (
    InventoryPolicy,
    MetafieldInput,
    MetafieldType,
    ProductStatus,
    ProductUpdate,
    VariantUpdate,
    WeightUnit,
)


# =============================================================================
# DateTime Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseDatetime:
    """parse_datetime converts ISO strings to datetime objects."""

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        assert parse_datetime(None) is None

    def test_iso_string_with_z_suffix(self) -> None:
        """Z suffix is converted to +00:00 timezone."""
        result = parse_datetime("2024-01-15T10:30:00Z")

        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_iso_string_with_timezone(self) -> None:
        """Explicit timezone is preserved."""
        result = parse_datetime("2024-01-15T10:30:00+00:00")

        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


# =============================================================================
# Money Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseMoney:
    """parse_money converts amount strings to Money objects."""

    def test_none_amount_returns_none(self) -> None:
        """None amount returns None."""
        assert parse_money(None, "USD") is None

    def test_valid_amount_returns_money(self) -> None:
        """Valid amount string returns Money object."""
        result = parse_money("19.99", "USD")

        assert result is not None
        assert result.amount == Decimal("19.99")
        assert result.currency_code == "USD"

    def test_different_currency(self) -> None:
        """Currency code is preserved."""
        result = parse_money("100.00", "EUR")

        assert result is not None
        assert result.currency_code == "EUR"


# =============================================================================
# Image Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseImage:
    """parse_image converts image data to ProductImage objects."""

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        assert parse_image(None) is None

    def test_valid_image_data(self) -> None:
        """Valid image data returns ProductImage."""
        data = {
            "id": "gid://shopify/ProductImage/123",
            "url": "https://cdn.shopify.com/image.jpg",
            "altText": "Product photo",
            "width": 800,
            "height": 600,
        }

        result = parse_image(data)

        assert result is not None
        assert result.id == "gid://shopify/ProductImage/123"
        assert result.url == "https://cdn.shopify.com/image.jpg"
        assert result.alt_text == "Product photo"
        assert result.width == 800
        assert result.height == 600

    def test_missing_optional_fields(self) -> None:
        """Missing optional fields default to None."""
        data = {
            "id": "gid://shopify/ProductImage/123",
            "url": "https://cdn.shopify.com/image.jpg",
        }

        result = parse_image(data)

        assert result is not None
        assert result.alt_text is None
        assert result.width is None
        assert result.height is None


# =============================================================================
# Inventory Policy Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseInventoryPolicy:
    """parse_inventory_policy converts strings to InventoryPolicy enum."""

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        assert parse_inventory_policy(None) is None

    def test_deny_value(self) -> None:
        """DENY string returns InventoryPolicy.DENY."""
        assert parse_inventory_policy("DENY") == InventoryPolicy.DENY

    def test_continue_value(self) -> None:
        """CONTINUE string returns InventoryPolicy.CONTINUE."""
        assert parse_inventory_policy("CONTINUE") == InventoryPolicy.CONTINUE


# =============================================================================
# Metafield Type Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseMetafieldType:
    """parse_metafield_type converts strings to MetafieldType enum."""

    def test_known_type(self) -> None:
        """Known type string returns correct enum value."""
        result = parse_metafield_type("single_line_text_field")

        assert result == MetafieldType.SINGLE_LINE_TEXT_FIELD

    def test_unknown_type_falls_back(self) -> None:
        """Unknown type falls back to SINGLE_LINE_TEXT_FIELD."""
        result = parse_metafield_type("unknown_future_type")

        assert result == MetafieldType.SINGLE_LINE_TEXT_FIELD


# =============================================================================
# Metafields Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseMetafields:
    """parse_metafields converts metafields data to Metafield list."""

    def test_none_returns_empty_list(self) -> None:
        """None input returns empty list."""
        assert parse_metafields(None) == []

    def test_valid_metafields(self) -> None:
        """Valid metafields data returns Metafield list."""
        data = {
            "nodes": [
                {
                    "id": "gid://shopify/Metafield/1",
                    "namespace": "custom",
                    "key": "color",
                    "value": "blue",
                    "type": "single_line_text_field",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-02T00:00:00Z",
                }
            ]
        }

        result = parse_metafields(data)

        assert len(result) == 1
        assert result[0].id == "gid://shopify/Metafield/1"
        assert result[0].namespace == "custom"
        assert result[0].key == "color"
        assert result[0].value == "blue"

    def test_empty_nodes(self) -> None:
        """Empty nodes list returns empty list."""
        assert parse_metafields({"nodes": []}) == []


# =============================================================================
# Selected Options Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseSelectedOptions:
    """parse_selected_options converts options data to SelectedOption list."""

    def test_none_returns_empty_list(self) -> None:
        """None input returns empty list."""
        assert parse_selected_options(None) == []

    def test_valid_options(self) -> None:
        """Valid options data returns SelectedOption list."""
        data = [
            {"name": "Size", "value": "Large"},
            {"name": "Color", "value": "Blue"},
        ]

        result = parse_selected_options(data)

        assert len(result) == 2
        assert result[0].name == "Size"
        assert result[0].value == "Large"
        assert result[1].name == "Color"
        assert result[1].value == "Blue"


# =============================================================================
# SEO Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseSeo:
    """parse_seo converts SEO data to SEO object."""

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        assert parse_seo(None) is None

    def test_valid_seo_data(self) -> None:
        """Valid SEO data returns SEO object."""
        data = {"title": "SEO Title", "description": "SEO Description"}

        result = parse_seo(data)

        assert result is not None
        assert result.title == "SEO Title"
        assert result.description == "SEO Description"


# =============================================================================
# Price Range Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParsePriceRange:
    """parse_price_range converts price range data to PriceRange object."""

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        assert parse_price_range(None) is None

    def test_missing_min_price_returns_none(self) -> None:
        """Missing minVariantPrice returns None."""
        assert parse_price_range({}) is None

    def test_valid_price_range(self) -> None:
        """Valid price range data returns PriceRange object."""
        data = {
            "minVariantPrice": {"amount": "10.00", "currencyCode": "USD"},
            "maxVariantPrice": {"amount": "50.00", "currencyCode": "USD"},
        }

        result = parse_price_range(data)

        assert result is not None
        assert result.min_variant_price.amount == Decimal("10.00")
        assert result.max_variant_price.amount == Decimal("50.00")

    def test_missing_max_uses_min(self) -> None:
        """Missing maxVariantPrice defaults to minVariantPrice."""
        data = {"minVariantPrice": {"amount": "10.00", "currencyCode": "USD"}}

        result = parse_price_range(data)

        assert result is not None
        assert result.min_variant_price.amount == Decimal("10.00")
        assert result.max_variant_price.amount == Decimal("10.00")


# =============================================================================
# Product Options Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseOptions:
    """parse_options converts options data to ProductOption list."""

    def test_none_returns_empty_list(self) -> None:
        """None input returns empty list."""
        assert parse_options(None) == []

    def test_valid_options(self) -> None:
        """Valid options data returns ProductOption list."""
        data = [
            {"id": "gid://opt/1", "name": "Size", "position": 1, "values": ["S", "M", "L"]},
        ]

        result = parse_options(data)

        assert len(result) == 1
        assert result[0].id == "gid://opt/1"
        assert result[0].name == "Size"
        assert result[0].values == ["S", "M", "L"]


# =============================================================================
# Variant Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseVariant:
    """parse_variant converts variant data to ProductVariant object."""

    def test_minimal_variant_data(self) -> None:
        """Minimal variant data returns ProductVariant."""
        data = {
            "id": "gid://shopify/ProductVariant/123",
            "title": "Default Title",
            "price": "19.99",
        }

        result = parse_variant(data, "USD")

        assert result.id == "gid://shopify/ProductVariant/123"
        assert result.title == "Default Title"
        assert result.price.amount == Decimal("19.99")

    def test_full_variant_data(self) -> None:
        """Full variant data parses all fields."""
        data = {
            "id": "gid://shopify/ProductVariant/123",
            "title": "Small / Red",
            "displayName": "Product - Small / Red",
            "sku": "SKU-001",
            "barcode": "1234567890",
            "price": "29.99",
            "compareAtPrice": "39.99",
            "inventoryQuantity": 100,
            "inventoryPolicy": "DENY",
            "availableForSale": True,
            "taxable": True,
            "position": 1,
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-02T00:00:00Z",
            "selectedOptions": [{"name": "Size", "value": "Small"}],
        }

        result = parse_variant(data, "USD")

        assert result.sku == "SKU-001"
        assert result.barcode == "1234567890"
        assert result.compare_at_price is not None
        assert result.compare_at_price.amount == Decimal("39.99")
        assert result.inventory_quantity == 100
        assert result.inventory_policy == InventoryPolicy.DENY


# =============================================================================
# Product Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseProduct:
    """parse_product converts product data to Product object."""

    def test_minimal_product_data(self) -> None:
        """Minimal product data returns Product."""
        data = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "handle": "test-product",
            "status": "ACTIVE",
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-02T00:00:00Z",
        }

        result = parse_product(data)

        assert result.id == "gid://shopify/Product/123"
        assert result.title == "Test Product"
        assert result.handle == "test-product"
        assert result.status == ProductStatus.ACTIVE

    def test_product_with_variants(self) -> None:
        """Product with variants parses variant list."""
        data = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "handle": "test-product",
            "status": "ACTIVE",
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-02T00:00:00Z",
            "priceRangeV2": {"minVariantPrice": {"amount": "19.99", "currencyCode": "EUR"}},
            "variants": {
                "nodes": [
                    {"id": "gid://variant/1", "title": "Default", "price": "19.99"},
                ]
            },
        }

        result = parse_product(data)

        assert len(result.variants) == 1
        assert result.variants[0].price.currency_code == "EUR"


# =============================================================================
# GraphQL Error Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseGraphqlErrors:
    """parse_graphql_errors converts error data to GraphQLErrorEntry list."""

    def test_parses_error_list(self) -> None:
        """Error list is converted to GraphQLErrorEntry objects."""
        errors = [{"message": "Something went wrong", "path": ["product", "title"]}]

        result = parse_graphql_errors(errors)

        assert len(result) == 1
        assert result[0].message == "Something went wrong"


# =============================================================================
# User Error Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseUserErrors:
    """parse_user_errors converts mutation errors to UpdateFailure list."""

    def test_empty_list(self) -> None:
        """Empty error list returns empty failure list."""
        assert parse_user_errors([]) == []

    def test_error_with_field_path(self) -> None:
        """Error with field path extracts field string."""
        errors = [{"field": ["variants", 0, "sku"], "message": "SKU already exists", "code": "TAKEN"}]

        result = parse_user_errors(errors)

        assert len(result) == 1
        assert result[0].identifier == "variants.0.sku"
        assert result[0].error == "SKU already exists"
        assert result[0].error_code == "TAKEN"

    def test_error_without_field(self) -> None:
        """Error without field uses 'unknown' identifier."""
        errors = [{"message": "Unknown error"}]

        result = parse_user_errors(errors)

        assert result[0].identifier == "unknown"


# =============================================================================
# Variant from Mutation Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseVariantFromMutation:
    """parse_variant_from_mutation parses mutation response variants."""

    def test_parses_mutation_response(self) -> None:
        """Mutation response variant is parsed correctly."""
        data = VariantMutationResult(
            id="gid://shopify/ProductVariant/123",
            title="Small",
            sku="SKU-001",
            price="29.99",
            inventoryPolicy="DENY",  # Use alias name for pyright compatibility
            taxable=True,
        )

        result = parse_variant_from_mutation(data)

        assert result.id == "gid://shopify/ProductVariant/123"
        assert result.sku == "SKU-001"
        assert result.price.amount == Decimal("29.99")

    def test_weight_not_returned_by_mutation(self) -> None:
        """Weight is not returned by mutation, always None."""
        data = VariantMutationResult(
            id="gid://variant/1",
            price="10.00",
        )

        result = parse_variant_from_mutation(data)

        # Mutation responses don't include weight, so it's always None
        assert result.weight is None


# =============================================================================
# Inventory Level Parsing
# =============================================================================


@pytest.mark.os_agnostic
class TestParseInventoryLevel:
    """parse_inventory_level parses inventory data."""

    def test_parses_inventory_level(self) -> None:
        """Inventory level data is parsed correctly."""
        data = {
            "inventoryItemId": "gid://item/1",
            "locationId": "gid://location/1",
            "available": 50,
            "updatedAt": "2024-01-15T10:00:00Z",
        }

        result = parse_inventory_level(data)

        assert result.inventory_item_id == "gid://item/1"
        assert result.location_id == "gid://location/1"
        assert result.available == 50


# =============================================================================
# Input Builders
# =============================================================================


@pytest.mark.os_agnostic
class TestBuildProductInput:
    """build_product_input creates GraphQL ProductInput."""

    def test_empty_update_returns_id_only(self) -> None:
        """Empty update only includes product ID."""
        update = ProductUpdate()

        result = build_product_input("gid://product/1", update)

        assert result == {"id": "gid://product/1"}

    def test_title_update(self) -> None:
        """Title update is included."""
        update = ProductUpdate(title="New Title")

        result = build_product_input("gid://product/1", update)

        assert result["title"] == "New Title"

    def test_status_enum_converted(self) -> None:
        """Status enum is converted to string value."""
        update = ProductUpdate(status=ProductStatus.ARCHIVED)

        result = build_product_input("gid://product/1", update)

        assert result["status"] == "ARCHIVED"

    def test_seo_fields(self) -> None:
        """SEO fields are nested under 'seo' key."""
        update = ProductUpdate(seo_title="SEO Title", seo_description="SEO Desc")

        result = build_product_input("gid://product/1", update)

        assert result["seo"] == {"title": "SEO Title", "description": "SEO Desc"}

    def test_metafields_converted(self) -> None:
        """Metafields are converted to input format."""
        update = ProductUpdate(
            metafields=[
                MetafieldInput(
                    namespace="custom",
                    key="color",
                    value="blue",
                    type=MetafieldType.SINGLE_LINE_TEXT_FIELD,
                )
            ]
        )

        result = build_product_input("gid://product/1", update)

        assert result["metafields"] == [{"namespace": "custom", "key": "color", "value": "blue", "type": "single_line_text_field"}]


@pytest.mark.os_agnostic
class TestBuildVariantInput:
    """build_variant_input creates GraphQL VariantInput."""

    def test_empty_update_returns_id_only(self) -> None:
        """Empty update only includes variant ID."""
        update = VariantUpdate()

        result = build_variant_input("gid://variant/1", update)

        assert result == {"id": "gid://variant/1"}

    def test_price_converted_to_string(self) -> None:
        """Decimal price is converted to string."""
        update = VariantUpdate(price=Decimal("29.99"))

        result = build_variant_input("gid://variant/1", update)

        assert result["price"] == "29.99"

    def test_inventory_policy_enum_converted(self) -> None:
        """InventoryPolicy enum is converted to string."""
        update = VariantUpdate(inventory_policy=InventoryPolicy.CONTINUE)

        result = build_variant_input("gid://variant/1", update)

        assert result["inventoryPolicy"] == "CONTINUE"

    def test_weight_unit_enum_converted(self) -> None:
        """WeightUnit enum is converted to string in inventoryItem.measurement."""
        update = VariantUpdate(weight=Decimal("1.5"), weight_unit=WeightUnit.KILOGRAMS)

        result = build_variant_input("gid://variant/1", update)

        # Weight fields moved to inventoryItem.measurement in API 2024-04+
        assert "inventoryItem" in result
        assert "measurement" in result["inventoryItem"]
        measurement = result["inventoryItem"]["measurement"]
        assert measurement["weight"]["value"] == 1.5
        assert measurement["weight"]["unit"] == "KILOGRAMS"

    def test_option_values(self) -> None:
        """Option values are converted to optionValues format."""
        update = VariantUpdate(option1="Small", option2="Red")

        result = build_variant_input("gid://variant/1", update)

        assert {"optionName": "Option1", "name": "Small"} in result["optionValues"]
        assert {"optionName": "Option2", "name": "Red"} in result["optionValues"]


# =============================================================================
# Error Formatting Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestFormatGraphQLError:
    """format_graphql_error formats individual errors correctly."""

    def test_formats_error_with_code(self) -> None:
        """Error with extension code includes code prefix."""
        from lib_shopify_graphql.adapters.parsers import format_graphql_error
        from lib_shopify_graphql.exceptions import GraphQLErrorEntry

        error = GraphQLErrorEntry(
            message="Rate limited",
            extensions={"code": "THROTTLED"},
        )

        result = format_graphql_error(error)

        assert result == "[THROTTLED] Rate limited"

    def test_formats_error_without_code(self) -> None:
        """Error without extension code shows message only."""
        from lib_shopify_graphql.adapters.parsers import format_graphql_error
        from lib_shopify_graphql.exceptions import GraphQLErrorEntry

        error = GraphQLErrorEntry(message="Simple error")

        result = format_graphql_error(error)

        assert result == "Simple error"

    def test_formats_error_with_empty_extensions(self) -> None:
        """Error with empty extensions shows message only."""
        from lib_shopify_graphql.adapters.parsers import format_graphql_error
        from lib_shopify_graphql.exceptions import GraphQLErrorEntry

        error = GraphQLErrorEntry(message="Simple error", extensions={})

        result = format_graphql_error(error)

        assert result == "Simple error"


@pytest.mark.os_agnostic
class TestFormatGraphQLErrors:
    """format_graphql_errors formats multiple errors correctly."""

    def test_formats_error_with_path(self) -> None:
        """Error with path includes path info."""
        from lib_shopify_graphql.adapters.parsers import format_graphql_errors
        from lib_shopify_graphql.exceptions import GraphQLErrorEntry

        errors = [
            GraphQLErrorEntry(message="Not found", path=("product", "variants", 0)),
        ]

        result = format_graphql_errors(errors)

        assert result == "Not found (at product.variants.0)"

    def test_formats_multiple_errors(self) -> None:
        """Multiple errors are semicolon-separated."""
        from lib_shopify_graphql.adapters.parsers import format_graphql_errors
        from lib_shopify_graphql.exceptions import GraphQLErrorEntry

        errors = [
            GraphQLErrorEntry(message="Error 1"),
            GraphQLErrorEntry(message="Error 2"),
        ]

        result = format_graphql_errors(errors)

        assert result == "Error 1; Error 2"


# =============================================================================
# ProductCreate Input Builder Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestBuildProductCreateInput:
    """build_product_create_input builds GraphQL ProductInput correctly."""

    def test_includes_seo_title_only(self) -> None:
        """When only seo_title is set, SEO object includes only title."""
        from lib_shopify_graphql.adapters.parsers import build_product_create_input
        from lib_shopify_graphql.models import ProductCreate

        create = ProductCreate(title="Test Product", seo_title="SEO Title")

        result = build_product_create_input(create)

        assert result["seo"] == {"title": "SEO Title"}

    def test_includes_seo_description_only(self) -> None:
        """When only seo_description is set, SEO object includes only description."""
        from lib_shopify_graphql.adapters.parsers import build_product_create_input
        from lib_shopify_graphql.models import ProductCreate

        create = ProductCreate(title="Test Product", seo_description="SEO Description")

        result = build_product_create_input(create)

        assert result["seo"] == {"description": "SEO Description"}

    def test_includes_both_seo_fields(self) -> None:
        """When both SEO fields are set, both are included."""
        from lib_shopify_graphql.adapters.parsers import build_product_create_input
        from lib_shopify_graphql.models import ProductCreate

        create = ProductCreate(
            title="Test Product",
            seo_title="SEO Title",
            seo_description="SEO Description",
        )

        result = build_product_create_input(create)

        assert result["seo"] == {"title": "SEO Title", "description": "SEO Description"}

    def test_excludes_seo_when_not_set(self) -> None:
        """When no SEO fields are set, seo key is not included."""
        from lib_shopify_graphql.adapters.parsers import build_product_create_input
        from lib_shopify_graphql.models import ProductCreate

        create = ProductCreate(title="Test Product")

        result = build_product_create_input(create)

        assert "seo" not in result


# =============================================================================
# Truncation Detection Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestHasMorePages:
    """_has_more_pages detects truncation via pageInfo.hasNextPage."""

    def test_returns_true_when_has_next_page(self) -> None:
        """Returns True when pageInfo.hasNextPage is True."""
        from lib_shopify_graphql.adapters.parsers import _has_more_pages

        connection_data: dict[str, Any] = {"pageInfo": {"hasNextPage": True}, "nodes": []}

        assert _has_more_pages(connection_data) is True

    def test_returns_false_when_no_next_page(self) -> None:
        """Returns False when pageInfo.hasNextPage is False."""
        from lib_shopify_graphql.adapters.parsers import _has_more_pages

        connection_data: dict[str, Any] = {"pageInfo": {"hasNextPage": False}, "nodes": []}

        assert _has_more_pages(connection_data) is False

    def test_returns_false_when_no_page_info(self) -> None:
        """Returns False when pageInfo is missing."""
        from lib_shopify_graphql.adapters.parsers import _has_more_pages

        connection_data: dict[str, Any] = {"nodes": []}

        assert _has_more_pages(connection_data) is False

    def test_returns_false_when_none(self) -> None:
        """Returns False when connection_data is None."""
        from lib_shopify_graphql.adapters.parsers import _has_more_pages

        assert _has_more_pages(None) is False

    def test_returns_false_when_empty_dict(self) -> None:
        """Returns False when connection_data is empty dict."""
        from lib_shopify_graphql.adapters.parsers import _has_more_pages

        assert _has_more_pages({}) is False


@pytest.mark.os_agnostic
class TestGetTruncationInfo:
    """get_truncation_info analyzes raw product data for truncation."""

    def test_detects_no_truncation(self) -> None:
        """Returns truncated=False when no fields are truncated."""
        from lib_shopify_graphql.adapters.parsers import get_truncation_info

        product_data: dict[str, Any] = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "images": {"pageInfo": {"hasNextPage": False}, "nodes": [{"id": "1"}]},
            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": []},
        }

        result = get_truncation_info(product_data)

        assert result.truncated is False
        assert result.product_id == "gid://shopify/Product/123"
        assert result.product_title == "Test Product"

    def test_detects_images_truncated(self) -> None:
        """Detects when images are truncated."""
        from lib_shopify_graphql.adapters.parsers import get_truncation_info

        product_data: dict[str, Any] = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "images": {"pageInfo": {"hasNextPage": True}, "nodes": [{"id": "1"}]},
            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": []},
        }

        result = get_truncation_info(product_data)

        assert result.truncated is True
        assert result.fields.images.truncated is True
        assert result.fields.images.count == 1

    def test_detects_metafields_truncated(self) -> None:
        """Detects when metafields are truncated."""
        from lib_shopify_graphql.adapters.parsers import get_truncation_info

        product_data: dict[str, Any] = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "images": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "metafields": {
                "pageInfo": {"hasNextPage": True},
                "nodes": [{"id": "mf1"}, {"id": "mf2"}],
            },
            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": []},
        }

        result = get_truncation_info(product_data)

        assert result.truncated is True
        assert result.fields.metafields.truncated is True
        assert result.fields.metafields.count == 2

    def test_detects_variants_truncated(self) -> None:
        """Detects when variants are truncated."""
        from lib_shopify_graphql.adapters.parsers import get_truncation_info

        product_data: dict[str, Any] = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "images": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "variants": {
                "pageInfo": {"hasNextPage": True},
                "nodes": [{"id": "v1", "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []}}],
            },
        }

        result = get_truncation_info(product_data)

        assert result.truncated is True
        assert result.fields.variants.truncated is True
        assert result.fields.variants.count == 1

    def test_detects_variant_metafields_truncated(self) -> None:
        """Detects when variant metafields are truncated."""
        from lib_shopify_graphql.adapters.parsers import get_truncation_info

        product_data: dict[str, Any] = {
            "id": "gid://shopify/Product/123",
            "title": "Test Product",
            "images": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "variants": {
                "pageInfo": {"hasNextPage": False},
                "nodes": [
                    {
                        "id": "v1",
                        "metafields": {
                            "pageInfo": {"hasNextPage": True},
                            "nodes": [{"id": "vmf1"}],
                        },
                    }
                ],
            },
        }

        result = get_truncation_info(product_data)

        assert result.truncated is True
        assert result.fields.variant_metafields.truncated is True
        assert result.fields.variant_metafields.count == 1

    def test_includes_config_keys(self) -> None:
        """Includes config_key and env_var for each field."""
        from lib_shopify_graphql.adapters.parsers import get_truncation_info

        product_data: dict[str, Any] = {
            "id": "gid://shopify/Product/123",
            "title": "Test",
            "images": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "media": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "metafields": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "variants": {"pageInfo": {"hasNextPage": False}, "nodes": []},
        }

        result = get_truncation_info(product_data)

        assert result.fields.images.config_key == "product_max_images"
        assert result.fields.images.env_var == "GRAPHQL__PRODUCT_MAX_IMAGES"
        assert result.fields.metafields.config_key == "product_max_metafields"
        assert result.fields.variants.config_key == "product_max_variants"


# =============================================================================
# GraphQL Limits Configuration Tests
# =============================================================================


class FakeConfig:
    """Fake config for testing GraphQLLimits.from_config()."""

    def __init__(self, graphql_config: dict[str, Any] | None = None) -> None:
        self._graphql = graphql_config

    def get(self, key: str, default: Any = None) -> Any:
        if key == "graphql":
            return self._graphql if self._graphql is not None else default
        return default


@pytest.mark.os_agnostic
class TestGraphQLLimitsFromConfig:
    """Tests for GraphQLLimits.from_config() to cover all code paths."""

    def test_returns_defaults_when_config_empty(self) -> None:
        """Returns defaults when graphql config section is empty."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({})
        result = GraphQLLimits.from_config(config)

        assert result.product_max_images == 20
        assert result.product_max_variants == 20
        assert result.product_warn_on_truncation is True

    def test_parses_int_values_from_config(self) -> None:
        """Parses integer values from config."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_max_images": 50, "product_max_variants": 100})
        result = GraphQLLimits.from_config(config)

        assert result.product_max_images == 50
        assert result.product_max_variants == 100

    def test_parses_string_values_as_int(self) -> None:
        """Parses string values as integers (e.g., from env vars)."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_max_images": "30", "product_max_variants": "50"})
        result = GraphQLLimits.from_config(config)

        assert result.product_max_images == 30
        assert result.product_max_variants == 50

    def test_returns_default_when_value_is_none(self) -> None:
        """Returns default when config value is explicitly None."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_max_images": None})
        result = GraphQLLimits.from_config(config)

        assert result.product_max_images == 20  # default

    def test_returns_default_for_non_int_non_str_value(self) -> None:
        """Returns default when config value is neither int nor string."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_max_images": [1, 2, 3]})  # list instead of int
        result = GraphQLLimits.from_config(config)

        assert result.product_max_images == 20  # default

    def test_parses_bool_true_values(self) -> None:
        """Parses boolean True from config."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": True})
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is True

    def test_parses_bool_false_values(self) -> None:
        """Parses boolean False from config."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": False})
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is False

    def test_parses_string_true_values(self) -> None:
        """Parses string 'true' as boolean True (env var case)."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": "true"})
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is True

    def test_parses_string_yes_values(self) -> None:
        """Parses string 'yes' as boolean True."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": "yes"})
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is True

    def test_parses_string_1_as_true(self) -> None:
        """Parses string '1' as boolean True."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": "1"})
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is True

    def test_parses_string_false_values(self) -> None:
        """Parses string 'false' as boolean False."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": "false"})
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is False

    def test_bool_default_when_value_is_none(self) -> None:
        """Returns default when bool config value is None."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": None})
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is True  # default

    def test_converts_truthy_non_bool_to_bool(self) -> None:
        """Converts truthy non-bool/non-string value to bool."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": 1})  # int instead of bool
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is True

    def test_converts_falsy_non_bool_to_bool(self) -> None:
        """Converts falsy non-bool/non-string value to bool."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig({"product_warn_on_truncation": 0})  # int instead of bool
        result = GraphQLLimits.from_config(config)

        assert result.product_warn_on_truncation is False

    def test_handles_non_dict_graphql_config(self) -> None:
        """Returns defaults when graphql config is not a dict."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits

        config: Any = FakeConfig(None)  # Not a dict
        result = GraphQLLimits.from_config(config)

        # Should use empty dict fallback and get all defaults
        assert result.product_max_images == 20
        assert result.product_warn_on_truncation is True


@pytest.mark.os_agnostic
class TestGetLimitsFromConfig:
    """Tests for get_limits_from_config() function."""

    def test_returns_graphql_limits_instance(self) -> None:
        """Returns a GraphQLLimits instance."""
        from lib_shopify_graphql.adapters.queries import GraphQLLimits, get_limits_from_config

        # Clear the lru_cache to get fresh result
        get_limits_from_config.cache_clear()
        result = get_limits_from_config()

        assert isinstance(result, GraphQLLimits)

    def test_returns_default_limits_on_config_error(self) -> None:
        """Returns DEFAULT_LIMITS when config raises exception."""
        from unittest.mock import patch

        from lib_shopify_graphql.adapters.queries import DEFAULT_LIMITS, get_limits_from_config

        get_limits_from_config.cache_clear()

        # Patch at the source module where get_config is defined
        with patch("lib_shopify_graphql.config.get_config") as mock_get_config:
            mock_get_config.side_effect = RuntimeError("Config not available")
            result = get_limits_from_config()

        assert result == DEFAULT_LIMITS
