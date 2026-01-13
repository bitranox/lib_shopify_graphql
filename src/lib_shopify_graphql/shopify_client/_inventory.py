"""Inventory operations for Shopify API.

This module provides inventory set and adjust functionality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..application.ports import LocationResolverPort, SKUResolverPort

from ..adapters.mutations import (
    INVENTORY_ADJUST_QUANTITIES_MUTATION,
    INVENTORY_SET_QUANTITIES_MUTATION,
    VARIANT_INVENTORY_ITEM_QUERY,
)
from ..adapters.parsers import (
    format_graphql_errors,
    parse_graphql_errors,
)
from ..exceptions import GraphQLError, SessionNotActiveError, VariantNotFoundError
from ..models import InventoryLevel, InventoryQuantityName, InventoryReason
from ..models._operations import UserErrorData
from ._common import _get_session_sku_resolver, _resolve_variant_identifier
from ._session import ShopifySession

logger = logging.getLogger(__name__)


def _get_inventory_item_id(session: ShopifySession, variant_gid: str) -> str:
    """Get the inventory item ID for a variant."""
    data = session.execute_graphql(VARIANT_INVENTORY_ITEM_QUERY, variables={"id": variant_gid})
    variant_data = data.get("data", {}).get("productVariant")
    if variant_data is None:
        raise VariantNotFoundError(variant_gid)

    inventory_item = variant_data.get("inventoryItem")
    if inventory_item is None:
        raise GraphQLError(f"Variant {variant_gid} has no inventory item")

    return inventory_item["id"]


def _resolve_location(
    location_id: str | None,
    location_resolver: LocationResolverPort | None,
) -> str:
    """Resolve location ID to GID format.

    Args:
        location_id: Optional location ID override.
        location_resolver: Optional location resolver.

    Returns:
        Location GID.

    Raises:
        ValueError: If no location can be resolved.
    """
    if location_resolver:
        return location_resolver.resolve(location_id)
    if location_id:
        return location_id if location_id.startswith("gid://") else f"gid://shopify/Location/{location_id}"
    raise ValueError("No location_id provided and no location_resolver configured")


def _check_inventory_graphql_errors(data: dict[str, Any], query: str) -> None:
    """Check for GraphQL-level errors in inventory response."""
    if "errors" not in data:
        return
    parsed_errors = parse_graphql_errors(data["errors"])
    raise GraphQLError(
        f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
        errors=parsed_errors,
        query=query,
    )


def _check_inventory_user_errors(user_errors: list[UserErrorData], query: str, operation: str) -> None:
    """Check for user errors in inventory mutation response.

    Args:
        user_errors: Parsed user errors from mutation response.
        query: GraphQL query string for error context.
        operation: Operation name for error message (e.g., "update", "adjust").

    Raises:
        GraphQLError: If any user errors are present.
    """
    if not user_errors:
        return
    first_error = user_errors[0]
    field_path = ".".join(first_error.field) if first_error.field else "unknown"
    raise GraphQLError(
        f"Inventory {operation} failed on field '{field_path}': {first_error.message}",
        query=query,
    )


def _build_set_quantities_input(
    inventory_item_id: str,
    location_id: str,
    quantity: int,
    reason: InventoryReason,
) -> dict[str, Any]:
    """Build input for inventorySetQuantities mutation."""
    return {
        "name": InventoryQuantityName.AVAILABLE.value,
        "reason": reason.value,
        "ignoreCompareQuantity": True,
        "quantities": [
            {
                "inventoryItemId": inventory_item_id,
                "locationId": location_id,
                "quantity": quantity,
            }
        ],
    }


def _build_adjust_quantities_input(
    inventory_item_id: str,
    location_id: str,
    delta: int,
    reason: InventoryReason,
) -> dict[str, Any]:
    """Build input for inventoryAdjustQuantities mutation."""
    return {
        "name": InventoryQuantityName.AVAILABLE.value,
        "reason": reason.value,
        "changes": [
            {
                "inventoryItemId": inventory_item_id,
                "locationId": location_id,
                "delta": delta,
            }
        ],
    }


def set_inventory(
    session: ShopifySession,
    variant_id_or_sku: str,
    quantity: int,
    *,
    location_id: str | None = None,
    reason: InventoryReason = InventoryReason.CORRECTION,
    sku_resolver: SKUResolverPort | None = None,
    location_resolver: LocationResolverPort | None = None,
) -> InventoryLevel:
    """Set absolute inventory quantity for a variant.

    Location resolution order:
    1. location_id parameter
    2. Config: shopify.default_location_id (via location_resolver)
    3. Shop's primary location (auto-fetched)

    Args:
        session: An active ShopifySession.
        variant_id_or_sku: Variant GID, numeric ID, or SKU.
        quantity: Absolute quantity to set.
        location_id: Optional location GID override.
        reason: Reason for the change. Defaults to CORRECTION.
        sku_resolver: Optional SKU resolver override. If not provided, uses the
            session's resolver (auto-resolved from config at login).
        location_resolver: Custom location resolver.

    Returns:
        InventoryLevel with the new quantity.

    Raises:
        SessionNotActiveError: If the session is not active.
        VariantNotFoundError: If the variant does not exist.
        AmbiguousSKUError: If the SKU matches multiple variants.
        ValueError: If no location can be resolved.
        GraphQLError: If the mutation fails.

    Example:
        >>> from lib_shopify_graphql import login, set_inventory, InventoryReason
        >>> session = login(credentials)  # doctest: +SKIP
        >>> level = set_inventory(session, "ABC-123", 50)  # doctest: +SKIP
        >>> print(f"New quantity: {level.available}")  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    shop_url = session.get_credentials().shop_url
    resolver = _get_session_sku_resolver(session, sku_resolver)
    variant_gid = _resolve_variant_identifier(variant_id_or_sku, shop_url, resolver)
    resolved_location = _resolve_location(location_id, location_resolver)

    logger.info(f"Setting inventory for variant '{variant_gid}' to {quantity} at location '{resolved_location}'")

    try:
        inventory_item_id = _get_inventory_item_id(session, variant_gid)
        input_data = _build_set_quantities_input(inventory_item_id, resolved_location, quantity, reason)
        data = session.execute_graphql(INVENTORY_SET_QUANTITIES_MUTATION, variables={"input": input_data})

        _check_inventory_graphql_errors(data, INVENTORY_SET_QUANTITIES_MUTATION)
        mutation_data = data.get("data", {}).get("inventorySetQuantities", {})
        raw_user_errors = mutation_data.get("userErrors", [])
        parsed_user_errors = [UserErrorData.model_validate(e) for e in raw_user_errors]
        _check_inventory_user_errors(parsed_user_errors, INVENTORY_SET_QUANTITIES_MUTATION, "update")

        return InventoryLevel(inventory_item_id=inventory_item_id, location_id=resolved_location, available=quantity)

    except (VariantNotFoundError, GraphQLError):
        raise
    except Exception as exc:
        logger.error(f"Failed to set inventory for variant '{variant_id_or_sku}': {exc}")
        raise GraphQLError(f"Failed to set inventory: {exc}", query=INVENTORY_SET_QUANTITIES_MUTATION) from exc


def adjust_inventory(
    session: ShopifySession,
    variant_id_or_sku: str,
    delta: int,
    *,
    location_id: str | None = None,
    reason: InventoryReason = InventoryReason.CORRECTION,
    sku_resolver: SKUResolverPort | None = None,
    location_resolver: LocationResolverPort | None = None,
) -> InventoryLevel:
    """Adjust inventory by a delta (+5, -3, etc.).

    Location resolution order:
    1. location_id parameter
    2. Config: shopify.default_location_id (via location_resolver)
    3. Shop's primary location (auto-fetched)

    Args:
        session: An active ShopifySession.
        variant_id_or_sku: Variant GID, numeric ID, or SKU.
        delta: Amount to adjust (positive to add, negative to remove).
        location_id: Optional location GID override.
        reason: Reason for the change. Defaults to CORRECTION.
        sku_resolver: Optional SKU resolver override. If not provided, uses the
            session's resolver (auto-resolved from config at login).
        location_resolver: Custom location resolver.

    Returns:
        InventoryLevel with available=None (mutation does not return new quantity).
        Use set_inventory() if you need to know the resulting quantity.

    Raises:
        SessionNotActiveError: If the session is not active.
        VariantNotFoundError: If the variant does not exist.
        AmbiguousSKUError: If the SKU matches multiple variants.
        ValueError: If no location can be resolved.
        GraphQLError: If the mutation fails.

    Example:
        >>> from lib_shopify_graphql import login, adjust_inventory, InventoryReason
        >>> session = login(credentials)  # doctest: +SKIP
        >>> level = adjust_inventory(session, "ABC-123", -5)  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    shop_url = session.get_credentials().shop_url
    resolver = _get_session_sku_resolver(session, sku_resolver)
    variant_gid = _resolve_variant_identifier(variant_id_or_sku, shop_url, resolver)
    resolved_location = _resolve_location(location_id, location_resolver)

    logger.info(f"Adjusting inventory for variant '{variant_gid}' by {delta:+d} at location '{resolved_location}'")

    try:
        inventory_item_id = _get_inventory_item_id(session, variant_gid)
        input_data = _build_adjust_quantities_input(inventory_item_id, resolved_location, delta, reason)
        data = session.execute_graphql(INVENTORY_ADJUST_QUANTITIES_MUTATION, variables={"input": input_data})

        _check_inventory_graphql_errors(data, INVENTORY_ADJUST_QUANTITIES_MUTATION)
        mutation_data = data.get("data", {}).get("inventoryAdjustQuantities", {})
        raw_user_errors = mutation_data.get("userErrors", [])
        parsed_user_errors = [UserErrorData.model_validate(e) for e in raw_user_errors]
        _check_inventory_user_errors(parsed_user_errors, INVENTORY_ADJUST_QUANTITIES_MUTATION, "adjust")

        return InventoryLevel(inventory_item_id=inventory_item_id, location_id=resolved_location, available=None)

    except (VariantNotFoundError, GraphQLError):
        raise
    except Exception as exc:
        logger.error("Failed to adjust inventory", extra={"variant_id": variant_id_or_sku, "error": str(exc)})
        raise GraphQLError(f"Failed to adjust inventory: {exc}", query=INVENTORY_ADJUST_QUANTITIES_MUTATION) from exc


__all__ = [
    "adjust_inventory",
    "set_inventory",
]
