"""Mutation response parsers for Shopify GraphQL API.

Parses responses from product, variant, inventory, and media mutations
into typed models.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...models import (
    CurrencyCode,
    InventoryLevel,
    MediaStatus,
    Money,
    ProductVariant,
    SelectedOption,
    StagedUploadTarget,
    UpdateFailure,
)
from ...models._operations import VariantMutationResult
from ._products import parse_datetime, parse_inventory_policy, parse_money


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


def parse_staged_upload_target(data: dict[str, Any]) -> StagedUploadTarget:
    """Parse staged upload target from GraphQL response.

    Args:
        data: Staged target data from stagedUploadsCreate response.

    Returns:
        StagedUploadTarget with url, resource_url, and parameters.
    """
    from ...models._images import StagedUploadParameter, StagedUploadTarget

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
    "parse_inventory_level",
    "parse_media_from_mutation",
    "parse_media_user_errors",
    "parse_staged_upload_target",
    "parse_user_errors",
    "parse_variant_from_mutation",
]
