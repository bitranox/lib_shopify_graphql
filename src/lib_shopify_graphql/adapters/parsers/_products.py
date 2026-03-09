"""Product, variant, and entity parsing from Shopify GraphQL responses.

Converts raw GraphQL response dictionaries into typed Pydantic models
for products, variants, images, media, metafields, and related entities.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any

from ...models import (
    SEO,
    InventoryPolicy,
    MediaContentType,
    MediaStatus,
    Metafield,
    MetafieldType,
    Money,
    PageInfo,
    PriceRange,
    Product,
    ProductConnection,
    ProductImage,
    ProductMedia,
    ProductOption,
    ProductStatus,
    ProductVariant,
    SelectedOption,
)
from ._truncation import _check_truncation

logger = logging.getLogger(__name__)


def parse_datetime(dt_str: str | None) -> datetime | None:
    """Parse ISO datetime string to datetime object."""
    if dt_str is None:
        return None
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def parse_money(amount: str | None, currency_code: str) -> Money | None:
    """Parse a money amount string into a Money object."""
    if amount is None:
        return None
    return Money(amount=Decimal(amount), currency_code=currency_code)


def parse_image(image_data: dict[str, Any] | None) -> ProductImage | None:
    """Parse image data from GraphQL response."""
    if image_data is None:
        return None
    return ProductImage(
        id=image_data["id"],
        url=image_data["url"],
        alt_text=image_data.get("altText"),
        width=image_data.get("width"),
        height=image_data.get("height"),
    )


@lru_cache(maxsize=16)
def parse_inventory_policy(policy: str | None) -> InventoryPolicy | None:
    """Parse inventory policy string to enum."""
    if policy is None:
        return None
    return InventoryPolicy(policy)


@lru_cache(maxsize=64)
def parse_metafield_type(type_str: str) -> MetafieldType:
    """Parse metafield type string to enum, with fallback for unknown types."""
    try:
        return MetafieldType(type_str)
    except ValueError:
        logger.warning(f"Unknown metafield type '{type_str}', defaulting to SINGLE_LINE_TEXT_FIELD")
        return MetafieldType.SINGLE_LINE_TEXT_FIELD


def parse_metafields(metafields_data: dict[str, Any] | None) -> list[Metafield]:
    """Parse metafields from GraphQL response."""
    if metafields_data is None:
        return []
    return [
        Metafield(
            id=node["id"],
            namespace=node["namespace"],
            key=node["key"],
            value=node["value"],
            type=parse_metafield_type(node["type"]),
            created_at=parse_datetime(node.get("createdAt")),
            updated_at=parse_datetime(node.get("updatedAt")),
        )
        for node in metafields_data.get("nodes", [])
    ]


def parse_selected_options(options_data: list[dict[str, Any]] | None) -> list[SelectedOption]:
    """Parse selected options from GraphQL response."""
    if options_data is None:
        return []
    return [SelectedOption(name=opt["name"], value=opt["value"]) for opt in options_data]


def parse_seo(seo_data: dict[str, Any] | None) -> SEO | None:
    """Parse SEO data from GraphQL response."""
    if seo_data is None:
        return None
    return SEO(title=seo_data.get("title"), description=seo_data.get("description"))


def parse_price_range(price_range_data: dict[str, Any] | None) -> PriceRange | None:
    """Parse price range data from GraphQL response."""
    if price_range_data is None:
        return None
    min_price_data = price_range_data.get("minVariantPrice")
    if min_price_data is None:
        return None
    min_price = Money(amount=Decimal(min_price_data["amount"]), currency_code=min_price_data["currencyCode"])
    max_price_data = price_range_data.get("maxVariantPrice")
    max_price = min_price
    if max_price_data:
        max_price = Money(amount=Decimal(max_price_data["amount"]), currency_code=max_price_data["currencyCode"])
    return PriceRange(min_variant_price=min_price, max_variant_price=max_price)


def parse_options(options_data: list[dict[str, Any]] | None) -> list[ProductOption]:
    """Parse product options from GraphQL response."""
    if options_data is None:
        return []
    return [ProductOption(id=opt["id"], name=opt["name"], position=opt["position"], values=opt.get("values", [])) for opt in options_data]


def parse_variant(variant_data: dict[str, Any], currency_code: str) -> ProductVariant:
    """Parse variant data from GraphQL response."""
    return ProductVariant(
        id=variant_data["id"],
        title=variant_data["title"],
        display_name=variant_data.get("displayName"),
        sku=variant_data.get("sku"),
        barcode=variant_data.get("barcode"),
        price=Money(amount=Decimal(variant_data["price"]), currency_code=currency_code),
        compare_at_price=parse_money(variant_data.get("compareAtPrice"), currency_code),
        inventory_quantity=variant_data.get("inventoryQuantity"),
        inventory_policy=parse_inventory_policy(variant_data.get("inventoryPolicy")),
        available_for_sale=variant_data.get("availableForSale", True),
        taxable=variant_data.get("taxable", True),
        position=variant_data.get("position", 1),
        created_at=parse_datetime(variant_data.get("createdAt")),
        updated_at=parse_datetime(variant_data.get("updatedAt")),
        image=parse_image(variant_data.get("image")),
        selected_options=parse_selected_options(variant_data.get("selectedOptions")),
        metafields=parse_metafields(variant_data.get("metafields")),
    )


def _get_currency_code(product_data: dict[str, Any]) -> str:
    """Extract currency code from product price range, defaulting to USD."""
    price_range = product_data.get("priceRangeV2", {})
    min_price = price_range.get("minVariantPrice")
    if min_price:
        return min_price["currencyCode"]
    return "USD"


def _parse_images(product_data: dict[str, Any]) -> list[ProductImage]:
    """Parse product images from GraphQL response."""
    images: list[ProductImage] = []
    for img in product_data.get("images", {}).get("nodes", []):
        parsed = parse_image(img)
        if parsed:
            images.append(parsed)
    return images


def _parse_media(product_data: dict[str, Any]) -> list[ProductMedia]:
    """Parse product media from GraphQL response.

    Parses the media nodes which use MediaImage GIDs (different from ProductImage).
    These IDs are required for media mutations (update, delete, reorder).
    """
    media_list: list[ProductMedia] = []
    for media in product_data.get("media", {}).get("nodes", []):
        # Extract image data if this is a MediaImage
        image_data: dict[str, Any] = media.get("image") or {}
        # Parse enum values with proper fallbacks
        raw_content_type = media.get("mediaContentType")
        content_type = MediaContentType(raw_content_type) if raw_content_type else MediaContentType.IMAGE

        raw_status = media.get("status")
        status = MediaStatus(raw_status) if raw_status else MediaStatus.READY

        media_list.append(
            ProductMedia(
                id=media["id"],
                alt=media.get("alt"),
                media_content_type=content_type,
                status=status,
                url=image_data.get("url"),
                width=image_data.get("width"),
                height=image_data.get("height"),
            )
        )
    return media_list


def _parse_variants(product_data: dict[str, Any], currency_code: str) -> list[ProductVariant]:
    """Parse product variants from GraphQL response."""
    return [parse_variant(var, currency_code) for var in product_data.get("variants", {}).get("nodes", [])]


def parse_product(
    product_data: dict[str, Any],
    *,
    operation: str = "fetch",
) -> Product:
    """Parse product data from GraphQL response into a Product model.

    Args:
        product_data: Raw product data from GraphQL response.
        operation: Name of the calling operation for truncation warnings
            (e.g., "get_product_by_id", "list_products").
    """
    # Check for possible truncation and log warnings
    product_id = product_data.get("id", "unknown")
    _check_truncation(product_data, product_id, operation=operation)

    currency_code = _get_currency_code(product_data)
    created_at = datetime.fromisoformat(product_data["createdAt"].replace("Z", "+00:00"))
    updated_at = datetime.fromisoformat(product_data["updatedAt"].replace("Z", "+00:00"))

    return Product(
        id=product_data["id"],
        legacy_resource_id=product_data.get("legacyResourceId"),
        title=product_data["title"],
        description=product_data.get("description"),
        description_html=product_data.get("descriptionHtml"),
        handle=product_data["handle"],
        vendor=product_data.get("vendor"),
        product_type=product_data.get("productType"),
        status=ProductStatus(product_data["status"]),
        tags=product_data.get("tags", []),
        created_at=created_at,
        updated_at=updated_at,
        published_at=parse_datetime(product_data.get("publishedAt")),
        variants=_parse_variants(product_data, currency_code),
        images=_parse_images(product_data),
        media=_parse_media(product_data),
        featured_image=parse_image(product_data.get("featuredImage")),
        options=parse_options(product_data.get("options")),
        seo=parse_seo(product_data.get("seo")),
        price_range=parse_price_range(product_data.get("priceRangeV2")),
        total_inventory=product_data.get("totalInventory"),
        tracks_inventory=product_data.get("tracksInventory", True),
        has_only_default_variant=product_data.get("hasOnlyDefaultVariant", False),
        has_out_of_stock_variants=product_data.get("hasOutOfStockVariants", False),
        is_gift_card=product_data.get("isGiftCard", False),
        online_store_url=product_data.get("onlineStoreUrl"),
        online_store_preview_url=product_data.get("onlineStorePreviewUrl"),
        template_suffix=product_data.get("templateSuffix"),
        metafields=parse_metafields(product_data.get("metafields")),
    )


def parse_page_info(page_info_data: dict[str, Any]) -> PageInfo:
    """Parse PageInfo from GraphQL connection response.

    Args:
        page_info_data: PageInfo data from GraphQL response.

    Returns:
        PageInfo model with cursor information.
    """
    return PageInfo(
        has_next_page=page_info_data.get("hasNextPage", False),
        has_previous_page=page_info_data.get("hasPreviousPage", False),
        start_cursor=page_info_data.get("startCursor"),
        end_cursor=page_info_data.get("endCursor"),
    )


def parse_product_connection(
    products_data: dict[str, Any],
    *,
    operation: str = "list_products",
) -> ProductConnection:
    """Parse products connection from GraphQL response into ProductConnection model.

    Args:
        products_data: The 'products' field from GraphQL response containing
            nodes and pageInfo.
        operation: Name of the calling operation for truncation warnings
            (e.g., "list_products", "list_products_paginated", "iter_products").

    Returns:
        ProductConnection with parsed products and pagination info.

    Example:
        >>> data = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "abc"}}
        >>> result = parse_product_connection(data)
        >>> result.page_info.has_next_page
        True
    """
    nodes = products_data.get("nodes", [])
    products = [parse_product(node, operation=operation) for node in nodes]

    page_info_data = products_data.get("pageInfo", {})
    page_info = parse_page_info(page_info_data)

    return ProductConnection(
        products=products,
        page_info=page_info,
    )


__all__ = [
    "parse_datetime",
    "parse_image",
    "parse_inventory_policy",
    "parse_metafield_type",
    "parse_metafields",
    "parse_money",
    "parse_options",
    "parse_page_info",
    "parse_price_range",
    "parse_product",
    "parse_product_connection",
    "parse_selected_options",
    "parse_seo",
    "parse_variant",
]
