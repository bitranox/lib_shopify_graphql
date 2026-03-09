"""Truncation detection and warning system for Shopify GraphQL responses.

Checks if nested collections (images, media, variants, metafields) were
truncated by query limits and logs actionable warnings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...models._operations import TruncationInfo

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
    from ..queries import get_limits_from_config

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
    from ...models._operations import FieldTruncationInfo, TruncationFields, TruncationInfo
    from ..queries import get_limits_from_config

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


__all__ = [
    "_check_truncation",
    "_has_more_pages",
    "get_truncation_info",
]
