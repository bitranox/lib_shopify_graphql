"""Pydantic model tests: each model tells a clear validation story.

Tests for the Shopify data models covering:
- ShopifyCredentials validation and normalization
- Money model with currency validation
- ProductImage, ProductVariant, and Product models
- ShopifySessionInfo immutability
- Metafield, ProductOption, PriceRange, SEO models

All tests use real Pydantic validation behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from lib_shopify_graphql.models import (
    InventoryPolicy,
    Metafield,
    MetafieldType,
    Money,
    PriceRange,
    Product,
    ProductImage,
    ProductOption,
    ProductStatus,
    ProductVariant,
    SEO,
    SelectedOption,
    ShopifyCredentials,
    ShopifySessionInfo,
)


# =============================================================================
# ShopifyCredentials Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestShopifyCredentialsCreation:
    """ShopifyCredentials accepts valid input and sets defaults."""

    def test_accepts_valid_credentials(self) -> None:
        """Valid credentials are accepted without error."""
        creds = ShopifyCredentials(
            shop_url="mystore.myshopify.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        assert creds.shop_url == "mystore.myshopify.com"
        assert creds.client_id == "test_client_id"
        assert creds.client_secret == "test_client_secret"

    def test_defaults_to_latest_api_version(self) -> None:
        """API version defaults to 2026-01 when not specified."""
        creds = ShopifyCredentials(
            shop_url="mystore.myshopify.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        assert creds.api_version == "2026-01"

    def test_accepts_custom_api_version(self) -> None:
        """Custom API version overrides the default."""
        creds = ShopifyCredentials(
            shop_url="mystore.myshopify.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
            api_version="2025-01",
        )

        assert creds.api_version == "2025-01"


@pytest.mark.os_agnostic
class TestShopifyCredentialsUrlNormalization:
    """ShopifyCredentials normalizes shop URLs consistently."""

    def test_strips_https_prefix(self) -> None:
        """HTTPS prefix is removed from shop URL."""
        creds = ShopifyCredentials(
            shop_url="https://mystore.myshopify.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        assert creds.shop_url == "mystore.myshopify.com"

    def test_strips_http_prefix(self) -> None:
        """HTTP prefix is removed from shop URL."""
        creds = ShopifyCredentials(
            shop_url="http://mystore.myshopify.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        assert creds.shop_url == "mystore.myshopify.com"

    def test_strips_trailing_slash(self) -> None:
        """Trailing slash is removed from shop URL."""
        creds = ShopifyCredentials(
            shop_url="mystore.myshopify.com/",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        assert creds.shop_url == "mystore.myshopify.com"

    def test_lowercases_url(self) -> None:
        """Shop URL is lowercased for consistency."""
        creds = ShopifyCredentials(
            shop_url="MyStore.MyShopify.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        assert creds.shop_url == "mystore.myshopify.com"

    def test_trims_whitespace(self) -> None:
        """Whitespace is trimmed from shop URL."""
        creds = ShopifyCredentials(
            shop_url="  mystore.myshopify.com  ",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        assert creds.shop_url == "mystore.myshopify.com"

    def test_normalizes_complex_url(self) -> None:
        """Multiple normalizations are applied together."""
        creds = ShopifyCredentials(
            shop_url="  HTTPS://MyStore.MyShopify.com/  ",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        assert creds.shop_url == "mystore.myshopify.com"


@pytest.mark.os_agnostic
class TestShopifyCredentialsValidation:
    """ShopifyCredentials rejects invalid input."""

    def test_rejects_invalid_domain_without_dot(self) -> None:
        """Domains without a dot are rejected."""
        with pytest.raises(ValueError, match="must be a valid domain"):
            ShopifyCredentials(
                shop_url="localhost",
                client_id="test_client_id",
                client_secret="test_client_secret",
            )

    def test_rejects_localhost_localdomain(self) -> None:
        """localhost.localdomain is rejected (SSRF protection)."""
        with pytest.raises(ValueError, match="cannot be localhost"):
            ShopifyCredentials(
                shop_url="localhost.localdomain",
                client_id="test_client_id",
                client_secret="test_client_secret",
            )

    def test_rejects_private_ip_address(self) -> None:
        """Private IP addresses are rejected (SSRF protection)."""
        with pytest.raises(ValueError, match="private.*loopback.*reserved"):
            ShopifyCredentials(
                shop_url="192.168.1.1",
                client_id="test_client_id",
                client_secret="test_client_secret",
            )

    def test_rejects_loopback_ip_address(self) -> None:
        """Loopback IP addresses are rejected (SSRF protection)."""
        with pytest.raises(ValueError, match="private.*loopback.*reserved"):
            ShopifyCredentials(
                shop_url="127.0.0.1",
                client_id="test_client_id",
                client_secret="test_client_secret",
            )

    def test_rejects_domain_with_spaces(self) -> None:
        """Domains with spaces are rejected."""
        with pytest.raises(ValueError, match="must be a valid domain"):
            ShopifyCredentials(
                shop_url="my store.example.com",
                client_id="test_client_id",
                client_secret="test_client_secret",
            )

    def test_accepts_custom_domain(self) -> None:
        """Custom domains (not .myshopify.com) are accepted."""
        creds = ShopifyCredentials(
            shop_url="shop.rotek.at",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        assert creds.shop_url == "shop.rotek.at"

    def test_rejects_empty_client_id(self) -> None:
        """Empty client_id is rejected."""
        with pytest.raises(ValueError):
            ShopifyCredentials(
                shop_url="mystore.myshopify.com",
                client_id="",
                client_secret="test_client_secret",
            )

    def test_rejects_empty_client_secret(self) -> None:
        """Empty client_secret is rejected."""
        with pytest.raises(ValueError):
            ShopifyCredentials(
                shop_url="mystore.myshopify.com",
                client_id="test_client_id",
                client_secret="",
            )


@pytest.mark.os_agnostic
class TestShopifyCredentialsImmutability:
    """ShopifyCredentials is frozen and cannot be modified."""

    def test_cannot_modify_shop_url(self) -> None:
        """Attempting to modify shop_url raises an error."""
        creds = ShopifyCredentials(
            shop_url="mystore.myshopify.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        with pytest.raises(Exception):
            creds.shop_url = "other.myshopify.com"  # type: ignore[misc]

    def test_cannot_modify_client_id(self) -> None:
        """Attempting to modify client_id raises an error."""
        creds = ShopifyCredentials(
            shop_url="mystore.myshopify.com",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )

        with pytest.raises(Exception):
            creds.client_id = "new_client_id"  # type: ignore[misc]


# =============================================================================
# Money Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestMoneyCreation:
    """Money model holds currency amounts."""

    def test_accepts_valid_currency(self) -> None:
        """Valid 3-letter currency code is accepted."""
        money = Money(amount=Decimal("19.99"), currency_code="USD")

        assert money.amount == Decimal("19.99")
        assert money.currency_code == "USD"

    def test_preserves_decimal_precision(self) -> None:
        """Decimal precision is preserved exactly."""
        money = Money(amount=Decimal("123.456789"), currency_code="USD")

        assert money.amount == Decimal("123.456789")

    def test_accepts_zero_amount(self) -> None:
        """Zero amount is valid."""
        money = Money(amount=Decimal("0"), currency_code="USD")

        assert money.amount == Decimal("0")

    def test_accepts_negative_amount(self) -> None:
        """Negative amounts are valid (for refunds, etc.)."""
        money = Money(amount=Decimal("-10.00"), currency_code="USD")

        assert money.amount == Decimal("-10.00")


@pytest.mark.os_agnostic
class TestMoneyCurrencyValidation:
    """Money rejects invalid currency codes."""

    def test_rejects_short_currency_code(self) -> None:
        """Currency code shorter than 3 characters is rejected."""
        with pytest.raises(ValueError):
            Money(amount=Decimal("19.99"), currency_code="US")

    def test_rejects_long_currency_code(self) -> None:
        """Currency code longer than 3 characters is rejected."""
        with pytest.raises(ValueError):
            Money(amount=Decimal("19.99"), currency_code="USDD")


@pytest.mark.os_agnostic
class TestMoneyImmutability:
    """Money is frozen and cannot be modified."""

    def test_cannot_modify_amount(self) -> None:
        """Attempting to modify amount raises an error."""
        money = Money(amount=Decimal("19.99"), currency_code="USD")

        with pytest.raises(Exception):
            money.amount = Decimal("29.99")  # type: ignore[misc]

    def test_cannot_modify_currency_code(self) -> None:
        """Attempting to modify currency_code raises an error."""
        money = Money(amount=Decimal("19.99"), currency_code="USD")

        with pytest.raises(Exception):
            money.currency_code = "EUR"  # type: ignore[misc]


# =============================================================================
# ProductImage Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestProductImageCreation:
    """ProductImage captures image data."""

    def test_creates_with_required_fields(self) -> None:
        """Image is created with only required fields."""
        image = ProductImage(
            id="gid://shopify/ProductImage/123",
            url="https://cdn.shopify.com/image.jpg",
        )

        assert image.id == "gid://shopify/ProductImage/123"
        assert image.url == "https://cdn.shopify.com/image.jpg"

    def test_defaults_optional_fields_to_none(self) -> None:
        """Optional fields default to None."""
        image = ProductImage(
            id="gid://shopify/ProductImage/123",
            url="https://cdn.shopify.com/image.jpg",
        )

        assert image.alt_text is None
        assert image.width is None
        assert image.height is None

    def test_accepts_all_fields(self) -> None:
        """All fields are accepted when provided."""
        image = ProductImage(
            id="gid://shopify/ProductImage/123",
            url="https://cdn.shopify.com/image.jpg",
            alt_text="Product photo",
            width=800,
            height=600,
        )

        assert image.alt_text == "Product photo"
        assert image.width == 800
        assert image.height == 600


# =============================================================================
# ProductVariant Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestProductVariantCreation:
    """ProductVariant captures variant data."""

    def test_creates_with_required_fields(self) -> None:
        """Variant is created with only required fields."""
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Small / Red",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
        )

        assert variant.id == "gid://shopify/ProductVariant/123"
        assert variant.title == "Small / Red"
        assert variant.price.amount == Decimal("19.99")

    def test_defaults_available_for_sale_to_true(self) -> None:
        """available_for_sale defaults to True."""
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Small / Red",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
        )

        assert variant.available_for_sale is True

    def test_defaults_taxable_to_true(self) -> None:
        """taxable defaults to True."""
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Small / Red",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
        )

        assert variant.taxable is True

    def test_defaults_sku_to_none(self) -> None:
        """sku defaults to None."""
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Small / Red",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
        )

        assert variant.sku is None


@pytest.mark.os_agnostic
class TestProductVariantWithAllFields:
    """ProductVariant accepts all optional fields."""

    def test_accepts_inventory_fields(self) -> None:
        """Inventory-related fields are accepted."""
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Small / Red",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
            inventory_quantity=100,
            inventory_policy=InventoryPolicy.DENY,
        )

        assert variant.inventory_quantity == 100
        assert variant.inventory_policy == InventoryPolicy.DENY

    def test_accepts_compare_at_price(self) -> None:
        """compare_at_price is accepted for showing original price."""
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Small / Red",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
            compare_at_price=Money(amount=Decimal("29.99"), currency_code="USD"),
        )

        assert variant.compare_at_price is not None
        assert variant.compare_at_price.amount == Decimal("29.99")

    def test_accepts_sku_and_barcode(self) -> None:
        """SKU and barcode are accepted."""
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Small / Red",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
            sku="SKU-001",
            barcode="1234567890123",
        )

        assert variant.sku == "SKU-001"
        assert variant.barcode == "1234567890123"


# =============================================================================
# Product Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestProductCreation:
    """Product captures full product data."""

    def test_creates_with_required_fields(self) -> None:
        """Product is created with only required fields."""
        now = datetime.now(timezone.utc)
        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test-product",
            status=ProductStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

        assert product.id == "gid://shopify/Product/123"
        assert product.title == "Test Product"
        assert product.handle == "test-product"
        assert product.status == ProductStatus.ACTIVE

    def test_defaults_collections_to_empty_lists(self) -> None:
        """Collection fields default to empty lists."""
        now = datetime.now(timezone.utc)
        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test-product",
            status=ProductStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

        assert product.variants == []
        assert product.images == []
        assert product.tags == []
        assert product.options == []
        assert product.metafields == []


@pytest.mark.os_agnostic
class TestProductWithVariantsAndImages:
    """Product accepts variants and images."""

    def test_accepts_variants(self) -> None:
        """Variants are accepted and stored."""
        now = datetime.now(timezone.utc)
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Default",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
        )

        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test-product",
            status=ProductStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            variants=[variant],
        )

        assert len(product.variants) == 1
        assert product.variants[0].title == "Default"

    def test_accepts_images(self) -> None:
        """Images are accepted and stored."""
        now = datetime.now(timezone.utc)
        image = ProductImage(
            id="gid://shopify/ProductImage/123",
            url="https://cdn.shopify.com/image.jpg",
        )

        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test-product",
            status=ProductStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            images=[image],
        )

        assert len(product.images) == 1

    def test_accepts_featured_image(self) -> None:
        """Featured image is accepted."""
        now = datetime.now(timezone.utc)
        image = ProductImage(
            id="gid://shopify/ProductImage/123",
            url="https://cdn.shopify.com/image.jpg",
        )

        product = Product(
            id="gid://shopify/Product/123",
            title="Test Product",
            handle="test-product",
            status=ProductStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            featured_image=image,
        )

        assert product.featured_image is not None
        assert product.featured_image.url == "https://cdn.shopify.com/image.jpg"


# =============================================================================
# ProductStatus Enum Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestProductStatusEnum:
    """ProductStatus enum provides expected values."""

    def test_active_status_value(self) -> None:
        """ACTIVE status has correct string value."""
        assert ProductStatus.ACTIVE == "ACTIVE"

    def test_archived_status_value(self) -> None:
        """ARCHIVED status has correct string value."""
        assert ProductStatus.ARCHIVED == "ARCHIVED"

    def test_draft_status_value(self) -> None:
        """DRAFT status has correct string value."""
        assert ProductStatus.DRAFT == "DRAFT"


# =============================================================================
# InventoryPolicy Enum Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestInventoryPolicyEnum:
    """InventoryPolicy enum provides expected values."""

    def test_deny_policy_value(self) -> None:
        """DENY policy has correct string value."""
        assert InventoryPolicy.DENY == "DENY"

    def test_continue_policy_value(self) -> None:
        """CONTINUE policy has correct string value."""
        assert InventoryPolicy.CONTINUE == "CONTINUE"


# =============================================================================
# ShopifySessionInfo Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestShopifySessionInfoCreation:
    """ShopifySessionInfo captures session state."""

    def test_creates_with_all_fields(self) -> None:
        """Session info is created with provided fields."""
        info = ShopifySessionInfo(
            shop_url="mystore.myshopify.com",
            api_version="2026-01",
            is_active=True,
        )

        assert info.shop_url == "mystore.myshopify.com"
        assert info.api_version == "2026-01"
        assert info.is_active is True

    def test_defaults_is_active_to_true(self) -> None:
        """is_active defaults to True."""
        info = ShopifySessionInfo(
            shop_url="mystore.myshopify.com",
            api_version="2026-01",
        )

        assert info.is_active is True

    def test_accepts_inactive_state(self) -> None:
        """is_active can be set to False."""
        info = ShopifySessionInfo(
            shop_url="mystore.myshopify.com",
            api_version="2026-01",
            is_active=False,
        )

        assert info.is_active is False


@pytest.mark.os_agnostic
class TestShopifySessionInfoImmutability:
    """ShopifySessionInfo is frozen and cannot be modified."""

    def test_cannot_modify_is_active(self) -> None:
        """Attempting to modify is_active raises an error."""
        info = ShopifySessionInfo(
            shop_url="mystore.myshopify.com",
            api_version="2026-01",
        )

        with pytest.raises(Exception):
            info.is_active = False  # type: ignore[misc]

    def test_cannot_modify_shop_url(self) -> None:
        """Attempting to modify shop_url raises an error."""
        info = ShopifySessionInfo(
            shop_url="mystore.myshopify.com",
            api_version="2026-01",
        )

        with pytest.raises(Exception):
            info.shop_url = "other.myshopify.com"  # type: ignore[misc]


# =============================================================================
# Metafield Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestMetafieldCreation:
    """Metafield captures custom metadata."""

    def test_creates_with_required_fields(self) -> None:
        """Metafield is created with required fields."""
        metafield = Metafield(
            id="gid://shopify/Metafield/123",
            namespace="custom",
            key="color",
            value="blue",
            type=MetafieldType.SINGLE_LINE_TEXT_FIELD,
        )

        assert metafield.id == "gid://shopify/Metafield/123"
        assert metafield.namespace == "custom"
        assert metafield.key == "color"
        assert metafield.value == "blue"
        assert metafield.type == MetafieldType.SINGLE_LINE_TEXT_FIELD

    def test_defaults_timestamps_to_none(self) -> None:
        """Timestamps default to None."""
        metafield = Metafield(
            id="gid://shopify/Metafield/123",
            namespace="custom",
            key="color",
            value="blue",
            type=MetafieldType.SINGLE_LINE_TEXT_FIELD,
        )

        assert metafield.created_at is None
        assert metafield.updated_at is None

    def test_accepts_timestamps(self) -> None:
        """Timestamps are accepted when provided."""
        now = datetime.now(timezone.utc)
        metafield = Metafield(
            id="gid://shopify/Metafield/123",
            namespace="custom",
            key="color",
            value="blue",
            type=MetafieldType.SINGLE_LINE_TEXT_FIELD,
            created_at=now,
            updated_at=now,
        )

        assert metafield.created_at == now
        assert metafield.updated_at == now


@pytest.mark.os_agnostic
class TestMetafieldTypeEnum:
    """MetafieldType enum provides expected values."""

    def test_single_line_text_field_value(self) -> None:
        """SINGLE_LINE_TEXT_FIELD has correct string value."""
        assert MetafieldType.SINGLE_LINE_TEXT_FIELD == "single_line_text_field"

    def test_json_value(self) -> None:
        """JSON has correct string value."""
        assert MetafieldType.JSON == "json"

    def test_number_integer_value(self) -> None:
        """NUMBER_INTEGER has correct string value."""
        assert MetafieldType.NUMBER_INTEGER == "number_integer"


@pytest.mark.os_agnostic
class TestMetafieldTypeEnumValues:
    """MetafieldType enum covers all Shopify metafield types."""

    def test_multi_line_text_field_value(self) -> None:
        """MULTI_LINE_TEXT_FIELD has correct string value."""
        assert MetafieldType.MULTI_LINE_TEXT_FIELD == "multi_line_text_field"

    def test_number_decimal_value(self) -> None:
        """NUMBER_DECIMAL has correct string value."""
        assert MetafieldType.NUMBER_DECIMAL == "number_decimal"

    def test_boolean_value(self) -> None:
        """BOOLEAN has correct string value."""
        assert MetafieldType.BOOLEAN == "boolean"

    def test_date_value(self) -> None:
        """DATE has correct string value."""
        assert MetafieldType.DATE == "date"

    def test_date_time_value(self) -> None:
        """DATE_TIME has correct string value."""
        assert MetafieldType.DATE_TIME == "date_time"

    def test_color_value(self) -> None:
        """COLOR has correct string value."""
        assert MetafieldType.COLOR == "color"

    def test_url_value(self) -> None:
        """URL has correct string value."""
        assert MetafieldType.URL == "url"

    def test_money_value(self) -> None:
        """MONEY has correct string value."""
        assert MetafieldType.MONEY == "money"

    def test_product_reference_value(self) -> None:
        """PRODUCT_REFERENCE has correct string value."""
        assert MetafieldType.PRODUCT_REFERENCE == "product_reference"

    def test_rich_text_field_value(self) -> None:
        """RICH_TEXT_FIELD has correct string value."""
        assert MetafieldType.RICH_TEXT_FIELD == "rich_text_field"


@pytest.mark.os_agnostic
class TestMetafieldTypeEnumConversion:
    """MetafieldType enum converts from strings correctly."""

    def test_converts_from_string(self) -> None:
        """MetafieldType can be created from string value."""
        mf_type = MetafieldType("single_line_text_field")

        assert mf_type == MetafieldType.SINGLE_LINE_TEXT_FIELD

    def test_converts_json_from_string(self) -> None:
        """JSON type can be created from string value."""
        mf_type = MetafieldType("json")

        assert mf_type == MetafieldType.JSON

    def test_invalid_string_raises_value_error(self) -> None:
        """Invalid string raises ValueError."""
        with pytest.raises(ValueError):
            MetafieldType("invalid_type")

    def test_is_string_subclass(self) -> None:
        """MetafieldType is a string subclass for easy comparison."""
        mf_type = MetafieldType.SINGLE_LINE_TEXT_FIELD

        assert isinstance(mf_type, str)
        assert mf_type == "single_line_text_field"


@pytest.mark.os_agnostic
class TestMetafieldTypeEnumIteration:
    """MetafieldType enum supports iteration."""

    def test_can_iterate_over_all_types(self) -> None:
        """All MetafieldType values can be iterated."""
        types = list(MetafieldType)

        assert len(types) > 20  # We defined 25 types
        assert MetafieldType.SINGLE_LINE_TEXT_FIELD in types
        assert MetafieldType.JSON in types

    def test_list_types_have_string_values(self) -> None:
        """List types have compound string values."""
        assert MetafieldType.LIST_SINGLE_LINE_TEXT_FIELD == "list.single_line_text_field"
        assert MetafieldType.LIST_FILE_REFERENCE == "list.file_reference"


# =============================================================================
# SelectedOption Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestSelectedOptionCreation:
    """SelectedOption captures variant option selections."""

    def test_creates_with_name_and_value(self) -> None:
        """SelectedOption is created with name and value."""
        option = SelectedOption(name="Size", value="Large")

        assert option.name == "Size"
        assert option.value == "Large"

    def test_immutable(self) -> None:
        """SelectedOption is frozen and cannot be modified."""
        option = SelectedOption(name="Size", value="Large")

        with pytest.raises(Exception):
            option.name = "Color"  # type: ignore[misc]


@pytest.mark.os_agnostic
class TestSelectedOptionEquality:
    """SelectedOption supports equality comparison."""

    def test_equal_options_are_equal(self) -> None:
        """Two options with same name and value are equal."""
        option1 = SelectedOption(name="Size", value="Large")
        option2 = SelectedOption(name="Size", value="Large")

        assert option1 == option2

    def test_different_names_are_not_equal(self) -> None:
        """Options with different names are not equal."""
        option1 = SelectedOption(name="Size", value="Large")
        option2 = SelectedOption(name="Color", value="Large")

        assert option1 != option2

    def test_different_values_are_not_equal(self) -> None:
        """Options with different values are not equal."""
        option1 = SelectedOption(name="Size", value="Large")
        option2 = SelectedOption(name="Size", value="Small")

        assert option1 != option2


@pytest.mark.os_agnostic
class TestSelectedOptionHashing:
    """SelectedOption is hashable for use in sets and dicts."""

    def test_can_be_used_in_set(self) -> None:
        """SelectedOption can be added to a set."""
        option1 = SelectedOption(name="Size", value="Large")
        option2 = SelectedOption(name="Color", value="Red")

        options_set = {option1, option2}  # type: ignore[reportUnhashable]

        assert len(options_set) == 2

    def test_equal_options_have_same_hash(self) -> None:
        """Equal options have the same hash."""
        option1 = SelectedOption(name="Size", value="Large")
        option2 = SelectedOption(name="Size", value="Large")

        assert hash(option1) == hash(option2)

    def test_can_be_used_as_dict_key(self) -> None:
        """SelectedOption can be used as dictionary key."""
        option = SelectedOption(name="Size", value="Large")

        mapping = {option: "value"}  # type: ignore[reportUnhashable]

        assert mapping[option] == "value"


@pytest.mark.os_agnostic
class TestSelectedOptionSerialization:
    """SelectedOption serializes to dict for JSON output."""

    def test_model_dump_returns_dict(self) -> None:
        """model_dump returns a dictionary."""
        option = SelectedOption(name="Size", value="Large")

        dumped = option.model_dump()

        assert isinstance(dumped, dict)
        assert dumped["name"] == "Size"
        assert dumped["value"] == "Large"

    def test_model_dump_json_returns_string(self) -> None:
        """model_dump_json returns a JSON string."""
        option = SelectedOption(name="Size", value="Large")

        json_str = option.model_dump_json()

        assert isinstance(json_str, str)
        assert "Size" in json_str
        assert "Large" in json_str


@pytest.mark.os_agnostic
class TestSelectedOptionVariantUsage:
    """SelectedOption integrates with ProductVariant."""

    def test_variant_accepts_selected_options(self) -> None:
        """ProductVariant accepts list of SelectedOption."""
        options = [
            SelectedOption(name="Size", value="Large"),
            SelectedOption(name="Color", value="Red"),
        ]

        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Large / Red",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
            selected_options=options,
        )

        assert len(variant.selected_options) == 2
        assert variant.selected_options[0].name == "Size"
        assert variant.selected_options[1].value == "Red"

    def test_variant_defaults_to_empty_options(self) -> None:
        """ProductVariant defaults to empty selected_options list."""
        variant = ProductVariant(
            id="gid://shopify/ProductVariant/123",
            title="Default",
            price=Money(amount=Decimal("19.99"), currency_code="USD"),
        )

        assert variant.selected_options == []


# =============================================================================
# ProductOption Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestProductOptionCreation:
    """ProductOption captures option definitions."""

    def test_creates_with_all_fields(self) -> None:
        """ProductOption is created with all fields."""
        option = ProductOption(
            id="gid://shopify/ProductOption/1",
            name="Size",
            position=1,
            values=["Small", "Medium", "Large"],
        )

        assert option.id == "gid://shopify/ProductOption/1"
        assert option.name == "Size"
        assert option.position == 1
        assert option.values == ["Small", "Medium", "Large"]

    def test_defaults_values_to_empty_list(self) -> None:
        """Values default to empty list."""
        option = ProductOption(
            id="gid://shopify/ProductOption/1",
            name="Size",
            position=1,
        )

        assert option.values == []


# =============================================================================
# PriceRange Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestPriceRangeCreation:
    """PriceRange captures min/max pricing."""

    def test_creates_with_min_and_max(self) -> None:
        """PriceRange is created with min and max prices."""
        min_price = Money(amount=Decimal("9.99"), currency_code="USD")
        max_price = Money(amount=Decimal("29.99"), currency_code="USD")

        price_range = PriceRange(
            min_variant_price=min_price,
            max_variant_price=max_price,
        )

        assert price_range.min_variant_price.amount == Decimal("9.99")
        assert price_range.max_variant_price.amount == Decimal("29.99")

    def test_accepts_same_min_and_max(self) -> None:
        """Same min and max prices are valid."""
        price = Money(amount=Decimal("19.99"), currency_code="USD")

        price_range = PriceRange(
            min_variant_price=price,
            max_variant_price=price,
        )

        assert price_range.min_variant_price == price_range.max_variant_price


# =============================================================================
# SEO Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestSeoCreation:
    """SEO captures search engine optimization data."""

    def test_creates_with_title_and_description(self) -> None:
        """SEO is created with title and description."""
        seo = SEO(
            title="Product Title - Brand",
            description="Product description for search engines.",
        )

        assert seo.title == "Product Title - Brand"
        assert seo.description == "Product description for search engines."

    def test_defaults_to_none(self) -> None:
        """Fields default to None."""
        seo = SEO()

        assert seo.title is None
        assert seo.description is None

    def test_accepts_partial_data(self) -> None:
        """Only title or only description can be provided."""
        seo_title_only = SEO(title="Just a title")
        seo_desc_only = SEO(description="Just a description")

        assert seo_title_only.title == "Just a title"
        assert seo_title_only.description is None
        assert seo_desc_only.title is None
        assert seo_desc_only.description == "Just a description"


# =============================================================================
# Exception Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestVariantNotFoundError:
    """VariantNotFoundError provides variant lookup failure details."""

    def test_default_message(self) -> None:
        """Error has default message with identifier."""
        from lib_shopify_graphql.exceptions import VariantNotFoundError

        error = VariantNotFoundError("SKU123")

        assert error.identifier == "SKU123"
        assert "Variant not found: SKU123" in str(error)
        assert "SKU123" in error.message

    def test_custom_message(self) -> None:
        """Error accepts custom message."""
        from lib_shopify_graphql.exceptions import VariantNotFoundError

        error = VariantNotFoundError("SKU123", message="Custom error message")

        assert error.identifier == "SKU123"
        assert error.message == "Custom error message"


@pytest.mark.os_agnostic
class TestGraphQLTimeoutError:
    """GraphQLTimeoutError provides timeout details."""

    def test_stores_timeout_and_query(self) -> None:
        """Error stores timeout value and query."""
        from lib_shopify_graphql.exceptions import GraphQLTimeoutError

        error = GraphQLTimeoutError("Operation timed out", timeout=30.0, query="query { shop { name } }")

        assert error.timeout == 30.0
        assert error.query == "query { shop { name } }"
        assert error.message == "Operation timed out"
        assert "Operation timed out" in str(error)


# =============================================================================
# Domain Layer Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDomainModule:
    """Domain module is importable and exports correctly."""

    def test_domain_module_imports(self) -> None:
        """Domain module can be imported."""
        from lib_shopify_graphql import domain

        assert domain is not None
        assert hasattr(domain, "__all__")
        assert isinstance(domain.__all__, list)
