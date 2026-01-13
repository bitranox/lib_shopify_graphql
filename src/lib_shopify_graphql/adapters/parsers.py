"""Parsing functions for Shopify GraphQL API responses.

This module contains all functions for parsing raw GraphQL response data
into typed Pydantic models. Centralizing parsers improves testability
and reduces shopify_client.py complexity.

Also includes input builders for converting update models to GraphQL input format.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models._operations import TruncationInfo

from ..exceptions import GraphQLErrorEntry, GraphQLErrorLocation
from ..models import (
    SEO,
    CurrencyCode,
    InventoryLevel,
    InventoryPolicy,
    MediaContentType,
    MediaStatus,
    Metafield,
    MetafieldInput,
    MetafieldType,
    Money,
    PageInfo,
    PriceRange,
    Product,
    ProductConnection,
    ProductCreate,
    ProductImage,
    ProductMedia,
    ProductOption,
    ProductStatus,
    ProductUpdate,
    ProductVariant,
    SelectedOption,
    StagedUploadTarget,
    UpdateFailure,
    VariantUpdate,
    WeightUnit,
)
from ..models._operations import VariantMutationResult

logger = logging.getLogger(__name__)


# =============================================================================
# Truncation Warning System
# =============================================================================

# Query hints explain what each operation does and why limits matter
_QUERY_HINTS: dict[str, dict[str, str]] = {
    "get_product_by_id": {
        "images": "GetProduct query fetches single product - safe to increase limit",
        "media": "GetProduct query fetches single product - safe to increase limit",
        "default": "GetProduct query fetches single product",
    },
    "list_products": {
        "images": "ListProducts query fetches many products - increase cautiously to avoid MAX_COST_EXCEEDED",
        "media": "ListProducts query fetches many products - increase cautiously to avoid MAX_COST_EXCEEDED",
        "default": "ListProducts query multiplies cost by page_size",
    },
    "iter_products": {
        "images": "iter_products uses ListProducts internally - same cost considerations",
        "media": "iter_products uses ListProducts internally - same cost considerations",
        "default": "iter_products uses ListProducts with page_size=250",
    },
    "list_products_paginated": {
        "images": "ListProducts query - cost = page_size × nested_items",
        "media": "ListProducts query - cost = page_size × nested_items",
        "default": "ListProducts query - reduce first= parameter or nested limits",
    },
    "skucache_rebuild": {
        "images": "skucache_rebuild iterates all products - images not needed for SKU cache",
        "media": "skucache_rebuild iterates all products - media not needed for SKU cache",
        "default": "skucache_rebuild only needs variants for SKU mapping",
    },
    "create_product": {
        "images": "productCreate mutation - returned product has same limits as GetProduct",
        "media": "productCreate mutation - returned product has same limits as GetProduct",
        "default": "productCreate returns created product - safe to increase limits",
    },
    "duplicate_product": {
        "images": "productDuplicate mutation - returned product has same limits as GetProduct",
        "media": "productDuplicate mutation - returned product has same limits as GetProduct",
        "default": "productDuplicate returns new product - safe to increase limits",
    },
}


def _get_query_hint(operation: str, field: str) -> str:
    """Get contextual hint for a truncation warning.

    Args:
        operation: The operation being performed.
        field: The field that hit the limit (images, media, etc.).

    Returns:
        Hint string explaining the context and recommendation.
    """
    op_hints = _QUERY_HINTS.get(operation, {})
    return op_hints.get(field, op_hints.get("default", f"{operation} operation"))


def _has_more_pages(connection_data: dict[str, Any] | None) -> bool:
    """Check if a connection has more pages (data was truncated).

    Args:
        connection_data: Raw connection data with pageInfo.

    Returns:
        True if hasNextPage is True, indicating truncation.
    """
    if connection_data is None:
        return False
    page_info = connection_data.get("pageInfo", {})
    return page_info.get("hasNextPage", False)


def _log_truncation_warning(
    operation: str,
    title: str,
    short_id: str,
    field_name: str,
    count: int,
    config_key: str,
    env_var: str,
    extra_warning: str = "",
) -> None:
    """Log a truncation warning for a specific field."""
    query_hint = _get_query_hint(operation, field_name)
    extra = f" {extra_warning}" if extra_warning else ""
    logger.warning(
        "[%s] Product '%s' (ID: %s) has MORE than %d %s (TRUNCATED). Data is missing! Increase [graphql] %s or set %s env var.%s",
        operation,
        title,
        short_id,
        count,
        field_name,
        config_key,
        env_var,
        extra + (f" Current query: {query_hint}" if query_hint else ""),
    )


def _check_connection_truncation(
    product_data: dict[str, Any],
    field_key: str,
    operation: str,
    title: str,
    short_id: str,
    config_key: str,
    env_var: str,
    extra_warning: str = "",
) -> None:
    """Check a single connection field for truncation and log if found."""
    field_data = product_data.get(field_key, {})
    nodes = field_data.get("nodes", [])
    if _has_more_pages(field_data):
        _log_truncation_warning(operation, title, short_id, field_key, len(nodes), config_key, env_var, extra_warning)


def _check_truncation(
    product_data: dict[str, Any],
    product_id: str,
    *,
    operation: str = "fetch",
) -> None:
    """Check if any nested collections were truncated and log warnings.

    Uses pageInfo.hasNextPage to definitively detect truncation.
    Logs actionable warnings with config recommendations.

    Args:
        product_data: Raw product data from GraphQL response.
        product_id: Product ID for logging context.
        operation: Name of the operation being performed for context
            (e.g., "get_product_by_id", "list_products", "iter_products").
    """
    from .queries import get_limits_from_config

    limits = get_limits_from_config()
    if not limits.product_warn_on_truncation:
        return

    title = product_data.get("title", "Unknown")
    short_id = product_id.split("/")[-1] if "/" in product_id else product_id

    # Check connection fields with pageInfo
    _check_connection_truncation(
        product_data,
        "images",
        operation,
        title,
        short_id,
        "product_max_images",
        "GRAPHQL__PRODUCT_MAX_IMAGES",
    )
    _check_connection_truncation(
        product_data,
        "media",
        operation,
        title,
        short_id,
        "product_max_media",
        "GRAPHQL__PRODUCT_MAX_MEDIA",
    )
    _check_connection_truncation(
        product_data,
        "metafields",
        operation,
        title,
        short_id,
        "product_max_metafields",
        "GRAPHQL__PRODUCT_MAX_METAFIELDS",
    )
    _check_connection_truncation(
        product_data,
        "variants",
        operation,
        title,
        short_id,
        "product_max_variants",
        "GRAPHQL__PRODUCT_MAX_VARIANTS",
        "WARNING: High values increase query cost significantly.",
    )

    # Check options (no pageInfo - uses count heuristic)
    options = product_data.get("options", [])
    if len(options) >= limits.product_max_options:
        logger.warning(
            "[%s] Product '%s' (ID: %s) returned %d options (limit: %d). "
            "Some options may be missing. Increase [graphql] product_max_options or set "
            "GRAPHQL__PRODUCT_MAX_OPTIONS env var.",
            operation,
            title,
            short_id,
            len(options),
            limits.product_max_options,
        )

    # Check variant metafields (sample first variant)
    variants = product_data.get("variants", {}).get("nodes", [])
    if variants:
        variant_mf_data = variants[0].get("metafields", {})
        if _has_more_pages(variant_mf_data):
            _log_truncation_warning(
                operation,
                title,
                short_id,
                "variant metafields",
                len(variant_mf_data.get("nodes", [])),
                "product_max_variant_metafields",
                "GRAPHQL__PRODUCT_MAX_VARIANT_METAFIELDS",
                "WARNING: Cost = product_max_variants × product_max_variant_metafields!",
            )


def get_truncation_info(product_data: dict[str, Any]) -> TruncationInfo:
    """Analyze raw product data for truncation and return structured info.

    Uses pageInfo.hasNextPage to definitively detect truncation.
    Returns structured information about what was truncated.

    Args:
        product_data: Raw product data from GraphQL response.

    Returns:
        TruncationInfo with product details and per-field truncation status.
    """
    from ..models._operations import FieldTruncationInfo, TruncationFields, TruncationInfo
    from .queries import get_limits_from_config

    limits = get_limits_from_config()
    product_id = product_data.get("id", "unknown")
    title = product_data.get("title", "Unknown")

    # Check each nested connection
    images_data = product_data.get("images", {})
    media_data = product_data.get("media", {})
    metafields_data = product_data.get("metafields", {})
    variants_data = product_data.get("variants", {})

    images_truncated = _has_more_pages(images_data)
    media_truncated = _has_more_pages(media_data)
    metafields_truncated = _has_more_pages(metafields_data)
    variants_truncated = _has_more_pages(variants_data)

    # Check variant metafields (first variant as sample)
    variants = variants_data.get("nodes", [])
    variant_metafields_truncated = False
    variant_metafields_count = 0
    if variants:
        first_variant = variants[0]
        variant_metafields_data = first_variant.get("metafields", {})
        variant_metafields_count = len(variant_metafields_data.get("nodes", []))
        variant_metafields_truncated = _has_more_pages(variant_metafields_data)

    any_truncated = images_truncated or media_truncated or metafields_truncated or variants_truncated or variant_metafields_truncated

    fields = TruncationFields(
        images=FieldTruncationInfo(
            count=len(images_data.get("nodes", [])),
            limit=limits.product_max_images,
            truncated=images_truncated,
            config_key="product_max_images",
            env_var="GRAPHQL__PRODUCT_MAX_IMAGES",
        ),
        media=FieldTruncationInfo(
            count=len(media_data.get("nodes", [])),
            limit=limits.product_max_media,
            truncated=media_truncated,
            config_key="product_max_media",
            env_var="GRAPHQL__PRODUCT_MAX_MEDIA",
        ),
        metafields=FieldTruncationInfo(
            count=len(metafields_data.get("nodes", [])),
            limit=limits.product_max_metafields,
            truncated=metafields_truncated,
            config_key="product_max_metafields",
            env_var="GRAPHQL__PRODUCT_MAX_METAFIELDS",
        ),
        variants=FieldTruncationInfo(
            count=len(variants),
            limit=limits.product_max_variants,
            truncated=variants_truncated,
            config_key="product_max_variants",
            env_var="GRAPHQL__PRODUCT_MAX_VARIANTS",
            cost_warning="High values increase query cost significantly!",
        ),
        variant_metafields=FieldTruncationInfo(
            count=variant_metafields_count,
            limit=limits.product_max_variant_metafields,
            truncated=variant_metafields_truncated,
            config_key="product_max_variant_metafields",
            env_var="GRAPHQL__PRODUCT_MAX_VARIANT_METAFIELDS",
            cost_warning="Cost = product_max_variants × product_max_variant_metafields!",
        ),
    )

    return TruncationInfo(
        product_id=product_id,
        product_title=title,
        truncated=any_truncated,
        fields=fields,
    )


def _parse_graphql_error_location(loc_data: dict[str, Any]) -> GraphQLErrorLocation:
    """Parse a single error location from raw data."""
    return GraphQLErrorLocation(
        line=loc_data.get("line", 0),
        column=loc_data.get("column", 0),
    )


def _parse_single_graphql_error(error_data: dict[str, Any]) -> GraphQLErrorEntry:
    """Parse a single GraphQL error from raw API data."""
    locations_raw = error_data.get("locations")
    locations: tuple[GraphQLErrorLocation, ...] | None = None
    if locations_raw:
        locations = tuple(_parse_graphql_error_location(loc) for loc in locations_raw)

    path_raw = error_data.get("path")
    path: tuple[str | int, ...] | None = None
    if path_raw:
        path = tuple(path_raw)

    return GraphQLErrorEntry(
        message=error_data.get("message", "Unknown error"),
        locations=locations,
        path=path,
        extensions=error_data.get("extensions"),
    )


def parse_graphql_errors(errors_data: list[dict[str, Any]]) -> list[GraphQLErrorEntry]:
    """Parse GraphQL errors from API response into structured models."""
    return [_parse_single_graphql_error(error) for error in errors_data]


def format_graphql_error(error: GraphQLErrorEntry) -> str:
    """Format a single GraphQL error with its extension code if available.

    Args:
        error: Parsed GraphQL error entry.

    Returns:
        Formatted error string including code if present.

    Example:
        >>> error = GraphQLErrorEntry(message="Rate limited", extensions={"code": "THROTTLED"})
        >>> format_graphql_error(error)
        '[THROTTLED] Rate limited'
    """
    code = None
    if error.extensions:
        code = error.extensions.get("code")

    if code:
        return f"[{code}] {error.message}"
    return error.message


def format_graphql_errors(errors: list[GraphQLErrorEntry]) -> str:
    """Format multiple GraphQL errors into a single string.

    Includes error codes from extensions and path information.

    Args:
        errors: List of parsed GraphQL error entries.

    Returns:
        Semicolon-separated formatted error messages.

    Example:
        >>> errors = parse_graphql_errors([{"message": "Not found", "path": ["product"]}])
        >>> format_graphql_errors(errors)
        'Not found (at product)'
    """
    formatted: list[str] = []
    for error in errors:
        msg = format_graphql_error(error)
        if error.path:
            path_str = ".".join(str(p) for p in error.path)
            msg = f"{msg} (at {path_str})"
        formatted.append(msg)
    return "; ".join(formatted)


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


# =============================================================================
# Input Builders for Mutations
# =============================================================================


def _build_metafield_inputs(metafields: list[MetafieldInput] | None) -> list[dict[str, str]] | None:
    """Convert MetafieldInput list to GraphQL input format."""
    if metafields is None:
        return None
    return [{"namespace": mf.namespace, "key": mf.key, "value": mf.value, "type": mf.type.value} for mf in metafields]


_PRODUCT_FIELD_MAPPING: dict[str, str] = {
    "title": "title",
    "description_html": "descriptionHtml",
    "handle": "handle",
    "vendor": "vendor",
    "product_type": "productType",
    "tags": "tags",
    "status": "status",
    "template_suffix": "templateSuffix",
    "gift_card": "giftCard",
    "requires_selling_plan": "requiresSellingPlan",
    "collections_to_join": "collectionsToJoin",
    "collections_to_leave": "collectionsToLeave",
    "category": "category",
}


def _add_product_fields(result: dict[str, Any], set_fields: dict[str, Any]) -> None:
    """Add mapped product fields to result."""
    for model_field, graphql_field in _PRODUCT_FIELD_MAPPING.items():
        if model_field in set_fields:
            value = set_fields[model_field]
            result[graphql_field] = value.value if isinstance(value, ProductStatus) else value


def _add_seo_fields(result: dict[str, Any], set_fields: dict[str, Any]) -> None:
    """Add SEO fields as nested object if present."""
    if "seo_title" not in set_fields and "seo_description" not in set_fields:
        return
    seo: dict[str, str | None] = {}
    if "seo_title" in set_fields:
        seo["title"] = set_fields["seo_title"]  # type: ignore[assignment]
    if "seo_description" in set_fields:
        seo["description"] = set_fields["seo_description"]  # type: ignore[assignment]
    result["seo"] = seo


def build_product_input(product_id: str, update: ProductUpdate) -> dict[str, Any]:
    """Build ProductInput for productUpdate mutation."""
    result: dict[str, Any] = {"id": product_id}
    set_fields = update.get_set_fields()

    _add_product_fields(result, set_fields)
    _add_seo_fields(result, set_fields)

    if "metafields" in set_fields:
        result["metafields"] = _build_metafield_inputs(set_fields["metafields"])  # type: ignore[arg-type]

    return result


_PRODUCT_CREATE_FIELD_MAPPING: dict[str, str] = {
    "description_html": "descriptionHtml",
    "handle": "handle",
    "vendor": "vendor",
    "product_type": "productType",
    "tags": "tags",
}


def _add_create_optional_fields(result: dict[str, Any], create: ProductCreate) -> None:
    """Add optional fields from ProductCreate if not None."""
    for model_field, graphql_field in _PRODUCT_CREATE_FIELD_MAPPING.items():
        value = getattr(create, model_field)
        if value is not None:
            result[graphql_field] = value


def _add_create_seo_fields(result: dict[str, Any], create: ProductCreate) -> None:
    """Add SEO fields from ProductCreate if present."""
    if create.seo_title is None and create.seo_description is None:
        return
    seo: dict[str, str] = {}
    if create.seo_title is not None:
        seo["title"] = create.seo_title
    if create.seo_description is not None:
        seo["description"] = create.seo_description
    result["seo"] = seo


def build_product_create_input(create: ProductCreate) -> dict[str, Any]:
    """Build ProductInput for productCreate mutation."""
    result: dict[str, Any] = {"title": create.title}
    _add_create_optional_fields(result, create)

    if create.status is not None:
        result["status"] = create.status.value

    _add_create_seo_fields(result, create)
    return result


def _convert_variant_field_value(value: Any) -> Any:
    """Convert variant field value to GraphQL-compatible format."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, InventoryPolicy):
        return value.value
    return value


def _build_variant_direct_fields(
    result: dict[str, Any],
    set_fields: dict[str, Any],
) -> None:
    """Add direct variant fields to result dict."""
    field_mapping = {
        "price": "price",
        "compare_at_price": "compareAtPrice",
        "barcode": "barcode",
        "inventory_policy": "inventoryPolicy",
        "taxable": "taxable",
        "tax_code": "taxCode",
        "image_id": "mediaId",
    }

    for model_field, graphql_field in field_mapping.items():
        if model_field in set_fields:
            result[graphql_field] = _convert_variant_field_value(set_fields[model_field])


def _build_measurement_input(set_fields: dict[str, Any]) -> dict[str, Any]:
    """Build measurement input for inventoryItem (weight fields)."""
    measurement: dict[str, Any] = {}

    if "weight" in set_fields:
        weight_value = set_fields["weight"]
        if isinstance(weight_value, Decimal):
            weight_value = float(weight_value)
        measurement["weight"] = {"value": weight_value}

    if "weight_unit" in set_fields:
        weight_unit = set_fields["weight_unit"]
        if isinstance(weight_unit, WeightUnit):
            weight_unit = weight_unit.value
        if "weight" not in measurement:
            measurement["weight"] = {}
        measurement["weight"]["unit"] = weight_unit

    return measurement


def _build_inventory_item_input(set_fields: dict[str, Any]) -> dict[str, Any]:
    """Build inventoryItem input (API 2024-04+)."""
    inventory_item: dict[str, Any] = {}

    field_mapping = {
        "sku": "sku",
        "requires_shipping": "requiresShipping",
        "harmonized_system_code": "harmonizedSystemCode",
        "country_code_of_origin": "countryCodeOfOrigin",
    }

    for model_field, graphql_field in field_mapping.items():
        if model_field in set_fields:
            inventory_item[graphql_field] = set_fields[model_field]

    measurement = _build_measurement_input(set_fields)
    if measurement:
        inventory_item["measurement"] = measurement

    return inventory_item


def _build_option_values_input(set_fields: dict[str, Any]) -> list[dict[str, str]]:
    """Build option values array for variant options."""
    option_values: list[dict[str, str]] = []
    option_fields = ["option1", "option2", "option3"]

    for i, opt_field in enumerate(option_fields, start=1):
        if opt_field in set_fields and set_fields[opt_field] is not None:
            option_values.append({"optionName": f"Option{i}", "name": set_fields[opt_field]})  # type: ignore[dict-item]

    return option_values


def build_variant_input(variant_id: str, update: VariantUpdate) -> dict[str, Any]:
    """Build ProductVariantsBulkInput for productVariantsBulkUpdate mutation.

    Converts a VariantUpdate model to the GraphQL input format,
    only including fields that are not UNSET.

    Note: API 2024-04+ moved sku, requiresShipping, harmonizedSystemCode,
    and countryCodeOfOrigin to the inventoryItem nested input.

    Args:
        variant_id: Variant GID.
        update: VariantUpdate with fields to update.

    Returns:
        Dictionary suitable for ProductVariantsBulkInput GraphQL type.
    """
    result: dict[str, Any] = {"id": variant_id}
    set_fields = update.get_set_fields()

    _build_variant_direct_fields(result, set_fields)

    inventory_item = _build_inventory_item_input(set_fields)
    if inventory_item:
        result["inventoryItem"] = inventory_item

    option_values = _build_option_values_input(set_fields)
    if option_values:
        result["optionValues"] = option_values

    if "metafields" in set_fields:
        result["metafields"] = _build_metafield_inputs(set_fields["metafields"])  # type: ignore[arg-type]

    return result


# =============================================================================
# Mutation Response Parsers
# =============================================================================


def parse_user_errors(user_errors: list[dict[str, Any]]) -> list[UpdateFailure]:
    """Parse userErrors from mutation response into UpdateFailure list.

    Args:
        user_errors: List of userErrors from GraphQL mutation response.

    Returns:
        List of UpdateFailure objects.
    """
    failures: list[UpdateFailure] = []
    for error in user_errors:
        field_path = error.get("field", [])
        field_str = ".".join(str(f) for f in field_path) if field_path else None
        failures.append(
            UpdateFailure(
                identifier=field_str or "unknown",
                error=error.get("message", "Unknown error"),
                error_code=error.get("code"),
                field=field_str,
            )
        )
    return failures


def parse_variant_from_mutation(variant_data: VariantMutationResult) -> ProductVariant:
    """Parse variant data from mutation response.

    Mutation responses have slightly different structure than query responses.

    Args:
        variant_data: Typed variant data from productVariantsBulkUpdate response.

    Returns:
        ProductVariant model.
    """
    # Mutation responses don't include currency, default to USD
    currency_code = CurrencyCode.USD

    # Convert selected options from mutation format to domain format
    selected_options = [SelectedOption(name=opt.name, value=opt.value) for opt in variant_data.selected_options]

    return ProductVariant(
        id=variant_data.id,
        title=variant_data.title,
        sku=variant_data.sku,
        barcode=variant_data.barcode,
        price=Money(amount=Decimal(variant_data.price), currency_code=currency_code),
        compare_at_price=parse_money(variant_data.compare_at_price, currency_code) if variant_data.compare_at_price else None,
        inventory_policy=parse_inventory_policy(variant_data.inventory_policy),
        taxable=variant_data.taxable,
        weight=None,  # Weight is not returned by the mutation
        selected_options=selected_options,
    )


def parse_inventory_level(data: dict[str, Any]) -> InventoryLevel:
    """Parse inventory level from mutation response.

    Args:
        data: Inventory data from response.

    Returns:
        InventoryLevel model.
    """
    return InventoryLevel(
        inventory_item_id=data.get("inventoryItemId", ""),
        location_id=data.get("locationId", ""),
        available=data.get("available", 0),
        updated_at=parse_datetime(data.get("updatedAt")),
    )


# =============================================================================
# Media/Image Parsers
# =============================================================================


def parse_staged_upload_target(data: dict[str, Any]) -> StagedUploadTarget:
    """Parse staged upload target from GraphQL response.

    Args:
        data: Staged target data from stagedUploadsCreate response.

    Returns:
        StagedUploadTarget with url, resource_url, and parameters.
    """
    from ..models._images import StagedUploadParameter, StagedUploadTarget

    params = [StagedUploadParameter(name=p["name"], value=p["value"]) for p in data.get("parameters", [])]
    return StagedUploadTarget(
        url=data["url"],
        resource_url=data["resourceUrl"],
        parameters=params,
    )


def parse_media_from_mutation(media_data: dict[str, Any]) -> dict[str, Any]:
    """Parse media data from productCreateMedia response.

    Args:
        media_data: Media data from mutation response.

    Returns:
        Dictionary with image_id, url, alt_text, and status.
    """
    # Handle case where image is None (not just missing)
    image_data: dict[str, Any] = media_data.get("image") or {}
    # Parse status with proper enum fallback
    raw_status = media_data.get("status")
    status = MediaStatus(raw_status) if raw_status else MediaStatus.PROCESSING
    return {
        "image_id": media_data["id"],
        "url": image_data.get("url"),
        "alt_text": media_data.get("alt") or image_data.get("altText"),
        "status": status,
    }


def parse_media_user_errors(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Parse mediaUserErrors from mutation response.

    Args:
        errors: List of mediaUserErrors from GraphQL response.

    Returns:
        List of error dictionaries with code, field, and message.
    """
    return [
        {
            "code": e.get("code", "UNKNOWN"),
            "field": ".".join(str(f) for f in e.get("field", [])) if e.get("field") else "",
            "message": e.get("message", "Unknown error"),
        }
        for e in errors
    ]


__all__ = [
    # Input builders
    "build_product_create_input",
    "build_product_input",
    "build_variant_input",
    # Response parsers
    "parse_datetime",
    "parse_graphql_errors",
    "parse_image",
    "parse_inventory_level",
    "parse_inventory_policy",
    "parse_media_from_mutation",
    "parse_media_user_errors",
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
    "parse_staged_upload_target",
    "parse_user_errors",
    "parse_variant",
    "parse_variant_from_mutation",
]
