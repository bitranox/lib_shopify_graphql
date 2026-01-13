"""Core entity models for Shopify API responses.

This module contains immutable Pydantic models for Shopify data:
    - Product and variant models
    - Authentication credentials
    - Value objects (Money, SEO, etc.)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._enums import InventoryPolicy, MediaContentType, MediaStatus, MetafieldType, ProductStatus
from ._internal import _normalize_shop_url, _validate_shopify_domain


class SelectedOption(BaseModel):
    """A product variant's selected option (e.g., Size: Large).

    Represents a single option selection for a variant, such as
    'Size: Large' or 'Color: Blue'.

    Attributes:
        name: Option name (e.g., 'Size', 'Color').
        value: Selected value (e.g., 'Large', 'Blue').

    Example:
        >>> opt = SelectedOption(name="Size", value="Large")
        >>> opt.name
        'Size'
    """

    model_config = ConfigDict(frozen=True)

    name: str
    value: str


class Metafield(BaseModel):
    """Custom metadata attached to a Shopify resource.

    Metafields are key-value pairs that store custom data on products,
    variants, customers, orders, and other Shopify resources.

    Attributes:
        id: Shopify GID for the metafield.
        namespace: Container grouping metafields (e.g., 'custom', 'inventory').
        key: Unique identifier within the namespace.
        value: Data stored as string.
        type: Data type as MetafieldType enum.
        created_at: When the metafield was created.
        updated_at: When the metafield was last updated.

    Example:
        >>> mf = Metafield(
        ...     id="gid://shopify/Metafield/123",
        ...     namespace="custom",
        ...     key="color",
        ...     value="blue",
        ...     type=MetafieldType.SINGLE_LINE_TEXT_FIELD,
        ... )
        >>> mf.namespace
        'custom'
    """

    model_config = ConfigDict(frozen=True)

    id: str
    namespace: str
    key: str
    value: str
    type: MetafieldType
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ShopifyCredentials(BaseModel):
    """Credentials for Shopify API authentication.

    Supports two authentication methods:

    1. **Direct Access Token** (for Custom Apps):
       Provide ``access_token`` directly. This is the Admin API access token
       from a custom app installed in the store (starts with ``shpat_``).

    2. **Client Credentials Grant** (for Partner Apps):
       Provide ``client_id`` and ``client_secret`` to obtain tokens via OAuth.
       Tokens are valid for 24 hours and can be refreshed automatically.

    Attributes:
        shop_url: Shopify store URL (e.g., 'mystore.myshopify.com').
        api_version: Shopify API version (format: YYYY-MM).
        access_token: Direct Admin API access token (for custom apps).
        client_id: OAuth client ID from Dev Dashboard (for partner apps).
        client_secret: OAuth client secret from Dev Dashboard (for partner apps).

    Example (Custom App with direct token)::

        creds = ShopifyCredentials(
            shop_url="mystore.myshopify.com",
            access_token="shpat_xxxxx",
        )

    Example (Partner App with client credentials)::

        creds = ShopifyCredentials(
            shop_url="mystore.myshopify.com",
            client_id="your_client_id",
            client_secret="your_client_secret",
        )
    """

    model_config = ConfigDict(frozen=True)

    shop_url: str = Field(
        ...,
        description="Shopify store URL (e.g., 'mystore.myshopify.com')",
    )
    api_version: str = Field(
        default="2026-01",
        description="Shopify API version (format: YYYY-MM)",
    )
    access_token: str | None = Field(
        default=None,
        min_length=1,
        description="Direct Admin API access token (for custom apps, starts with shpat_)",
    )
    client_id: str | None = Field(
        default=None,
        min_length=1,
        description="OAuth client ID from Dev Dashboard (for partner apps)",
    )
    client_secret: str | None = Field(
        default=None,
        min_length=1,
        description="OAuth client secret from Dev Dashboard (for partner apps)",
    )

    @field_validator("shop_url")
    @classmethod
    def validate_shop_url(_cls, v: str) -> str:  # noqa: N805 - cls required by Pydantic classmethod pattern
        """Normalize and validate shop URL format.

        Strips protocol prefix and trailing slashes. Accepts both default
        .myshopify.com domains and custom domains (e.g., shop.rotek.at).

        Args:
            v: Raw shop URL input.

        Returns:
            Normalized shop URL (e.g., 'mystore.myshopify.com' or 'shop.example.com').

        Raises:
            ValueError: If URL is not a valid domain.
        """
        normalized = _normalize_shop_url(v)
        return _validate_shopify_domain(normalized)


class Money(BaseModel):
    """Monetary value with currency code.

    Attributes:
        amount: Decimal amount (e.g., Decimal('19.99')).
        currency_code: ISO 4217 currency code (e.g., 'USD', 'EUR').

    Example:
        >>> price = Money(amount=Decimal("19.99"), currency_code="USD")
        >>> price.amount
        Decimal('19.99')
    """

    model_config = ConfigDict(frozen=True)

    amount: Decimal
    currency_code: str = Field(..., min_length=3, max_length=3)


class PriceRange(BaseModel):
    """Price range for a product (min and max variant prices).

    Attributes:
        min_variant_price: Lowest price among all variants.
        max_variant_price: Highest price among all variants.
    """

    model_config = ConfigDict(frozen=True)

    min_variant_price: Money
    max_variant_price: Money


class SEO(BaseModel):
    """Search engine optimization data.

    Attributes:
        title: SEO title for the product.
        description: SEO meta description.
    """

    model_config = ConfigDict(frozen=True)

    title: str | None = None
    description: str | None = None


class ProductImage(BaseModel):
    """Product image data from Shopify.

    Attributes:
        id: Shopify GID for the image (ProductImage format).
        url: Full URL to the image.
        alt_text: Alternative text for accessibility.
        width: Image width in pixels.
        height: Image height in pixels.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    url: str
    alt_text: str | None = None
    width: int | None = None
    height: int | None = None


class ProductMedia(BaseModel):
    """Product media data from Shopify (for media API operations).

    Unlike ProductImage, this uses the Media API format which is required
    for media mutations (update, delete, reorder).

    Attributes:
        id: Shopify GID for the media (MediaImage format).
        alt: Alternative text for accessibility.
        media_content_type: Type of media (IMAGE, VIDEO, etc.).
        status: Processing status.
        url: Full URL to the media.
        width: Media width in pixels.
        height: Media height in pixels.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    alt: str | None = None
    media_content_type: MediaContentType = MediaContentType.IMAGE
    status: MediaStatus = MediaStatus.READY
    url: str | None = None
    width: int | None = None
    height: int | None = None


class ProductOption(BaseModel):
    """Product option definition (e.g., Size, Color).

    Attributes:
        id: Shopify GID for the option.
        name: Option name (e.g., 'Size', 'Color').
        position: Display order (1-indexed).
        values: List of option values (e.g., ['Small', 'Medium', 'Large']).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    position: int
    values: list[str] = Field(default_factory=list[str])


class ProductVariant(BaseModel):
    """Product variant data from Shopify.

    Represents a specific variant of a product (size, color, etc.).

    Attributes:
        id: Shopify GID for the variant.
        title: Variant title (e.g., 'Small / Red').
        display_name: Full display name (product title + variant title).
        sku: Stock keeping unit.
        barcode: Barcode (UPC, ISBN, etc.).
        price: Current price.
        compare_at_price: Original price for showing discount.
        inventory_quantity: Available inventory count.
        inventory_policy: Policy when out of stock (DENY or CONTINUE).
        available_for_sale: Whether variant can be purchased.
        taxable: Whether variant is taxable.
        weight: Variant weight in shop's default unit.
        position: Display order (1-indexed).
        created_at: When the variant was created.
        updated_at: When the variant was last updated.
        image: Variant-specific image.
        selected_options: List of selected option name/value pairs.
        metafields: Custom metadata attached to the variant.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    display_name: str | None = None
    sku: str | None = None
    barcode: str | None = None
    price: Money
    compare_at_price: Money | None = None
    inventory_quantity: int | None = None
    inventory_policy: InventoryPolicy | None = None
    available_for_sale: bool = True
    taxable: bool = True
    weight: Decimal | None = None
    position: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    image: ProductImage | None = None
    selected_options: list[SelectedOption] = Field(default_factory=list[SelectedOption])
    metafields: list[Metafield] = Field(default_factory=list[Metafield])


class Product(BaseModel):
    """Full Shopify product data.

    Contains all product information including variants and images.

    Attributes:
        id: Shopify GID (e.g., 'gid://shopify/Product/123').
        legacy_resource_id: REST API numeric ID.
        title: Product title.
        description: Plain text description.
        description_html: HTML formatted description.
        handle: URL-friendly identifier.
        vendor: Product vendor/manufacturer.
        product_type: Product category/type.
        status: Publication status.
        tags: List of product tags.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
        published_at: Publication timestamp.
        variants: List of product variants.
        images: List of product images.
        featured_image: Primary display image.
        options: List of product options (Size, Color, etc.).
        seo: Search engine optimization data.
        price_range: Min/max price range.
        total_inventory: Total inventory across all variants.
        tracks_inventory: Whether inventory is tracked.
        has_only_default_variant: True if only one default variant.
        has_out_of_stock_variants: True if any variants are out of stock.
        is_gift_card: Whether this is a gift card product.
        online_store_url: URL on the online store.
        online_store_preview_url: Preview URL for the online store.
        template_suffix: Theme template suffix.
        metafields: Custom metadata attached to the product.

    Example:
        >>> product = Product(
        ...     id="gid://shopify/Product/123",
        ...     title="Example Product",
        ...     handle="example-product",
        ...     status=ProductStatus.ACTIVE,
        ...     created_at=datetime.now(),
        ...     updated_at=datetime.now(),
        ... )
        >>> product.title
        'Example Product'
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        ...,
        description="Shopify GID (e.g., 'gid://shopify/Product/123')",
    )
    legacy_resource_id: str | None = None
    title: str
    description: str | None = None
    description_html: str | None = None
    handle: str
    vendor: str | None = None
    product_type: str | None = None
    status: ProductStatus
    tags: list[str] = Field(default_factory=list[str])
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    variants: list[ProductVariant] = Field(default_factory=list[ProductVariant])
    images: list[ProductImage] = Field(default_factory=list[ProductImage])
    media: list[ProductMedia] = Field(default_factory=list[ProductMedia])
    featured_image: ProductImage | None = None
    options: list[ProductOption] = Field(default_factory=list[ProductOption])
    seo: SEO | None = None
    price_range: PriceRange | None = None
    total_inventory: int | None = None
    tracks_inventory: bool = True
    has_only_default_variant: bool = False
    has_out_of_stock_variants: bool = False
    is_gift_card: bool = False
    online_store_url: str | None = None
    online_store_preview_url: str | None = None
    template_suffix: str | None = None
    metafields: list[Metafield] = Field(default_factory=list[Metafield])


class ShopifySessionInfo(BaseModel):
    """Read-only information about an active Shopify session.

    Provides a safe view of session state without exposing credentials.

    Attributes:
        shop_url: Connected store URL.
        api_version: API version in use.
        is_active: Whether the session is currently active.
        token_expiration: When the access token expires (if known).
    """

    model_config = ConfigDict(frozen=True)

    shop_url: str
    api_version: str
    is_active: bool = True
    token_expiration: datetime | None = None


__all__ = [
    "Metafield",
    "Money",
    "PriceRange",
    "Product",
    "ProductImage",
    "ProductMedia",
    "ProductOption",
    "ProductVariant",
    "SEO",
    "SelectedOption",
    "ShopifyCredentials",
    "ShopifySessionInfo",
]
