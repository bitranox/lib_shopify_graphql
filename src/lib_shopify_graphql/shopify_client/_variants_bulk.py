"""Bulk variant update operations for Shopify API.

This module provides bulk variant update functionality with refactored helpers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..application.ports import SKUResolverPort

from ..adapters.mutations import PRODUCT_VARIANTS_BULK_UPDATE_MUTATION
from ..adapters.parsers import (
    build_variant_input,
    format_graphql_errors,
    parse_graphql_errors,
    parse_variant_from_mutation,
)
from ..exceptions import GraphQLError, SessionNotActiveError, VariantNotFoundError
from ..models import BulkUpdateResult, UpdateFailure, UpdateSuccess, VariantUpdateRequest
from ..models._operations import UserErrorData, VariantMutationResult, VariantsBulkUpdateResponse
from ._common import _get_session_sku_resolver, _normalize_product_gid, _normalize_variant_gid, _resolve_variant_identifier
from ._session import ShopifySession

logger = logging.getLogger(__name__)


def _resolve_and_build_variant_inputs(
    updates: list[VariantUpdateRequest],
    shop_url: str,
    sku_resolver: SKUResolverPort | None,
) -> tuple[list[dict[str, Any]], dict[str, str], list[UpdateFailure]]:
    """Resolve identifiers and build variant inputs.

    Args:
        updates: List of update requests.
        shop_url: Shop URL for SKU resolution.
        sku_resolver: Optional SKU resolver.

    Returns:
        Tuple of (variant_inputs, identifier_map, failed_updates).
    """
    variant_inputs: list[dict[str, Any]] = []
    identifier_map: dict[str, str] = {}  # variant_gid -> original identifier
    failed: list[UpdateFailure] = []

    for req in updates:
        identifier = req.variant_id or req.sku or "unknown"
        try:
            if req.variant_id:
                variant_gid = _normalize_variant_gid(req.variant_id)
            elif req.sku:
                variant_gid = _resolve_variant_identifier(req.sku, shop_url, sku_resolver)
            else:
                failed.append(UpdateFailure(identifier=identifier, error="No identifier provided"))
                continue

            variant_input = build_variant_input(variant_gid, req.update)
            variant_inputs.append(variant_input)
            identifier_map[variant_gid] = identifier
        except VariantNotFoundError as exc:
            failed.append(UpdateFailure(identifier=identifier, error=str(exc)))

    return variant_inputs, identifier_map, failed


def _extract_identifier_from_error(
    field_path: list[Any],
    variant_inputs: list[dict[str, Any]],
    identifier_map: dict[str, str],
) -> str:
    """Extract identifier from error field path."""
    if not field_path or len(field_path) <= 1 or field_path[0] != "variants":
        return "unknown"

    idx = field_path[1]
    if not isinstance(idx, int) or idx >= len(variant_inputs):
        return "unknown"

    variant_gid = str(variant_inputs[idx].get("id", ""))
    return identifier_map.get(variant_gid, variant_gid)


def _process_mutation_user_errors(
    user_errors: list[UserErrorData],
    variant_inputs: list[dict[str, Any]],
    identifier_map: dict[str, str],
) -> list[UpdateFailure]:
    """Process user errors from mutation response.

    Args:
        user_errors: Parsed user errors from GraphQL response.
        variant_inputs: Original variant inputs for identifier extraction.
        identifier_map: Map of variant GID to original identifier.

    Returns:
        List of UpdateFailure objects.
    """
    failed: list[UpdateFailure] = []

    for error in user_errors:
        field_path = error.field
        identifier = _extract_identifier_from_error(field_path, variant_inputs, identifier_map)

        failed.append(
            UpdateFailure(
                identifier=str(identifier),
                error=error.message,
                error_code=error.code,
                field=".".join(str(f) for f in field_path) if field_path else None,
            )
        )

    return failed


def _process_mutation_successes(
    variants_data: list[VariantMutationResult],
    identifier_map: dict[str, str],
) -> list[UpdateSuccess]:
    """Process successful updates from mutation response.

    Args:
        variants_data: Typed variant data from GraphQL response.
        identifier_map: Map of variant GID to original identifier.

    Returns:
        List of UpdateSuccess objects.
    """
    succeeded: list[UpdateSuccess] = []

    for variant_data in variants_data:
        variant_gid = variant_data.id
        identifier = identifier_map.get(variant_gid, variant_gid)
        variant = parse_variant_from_mutation(variant_data)
        succeeded.append(UpdateSuccess(identifier=str(identifier), variant=variant))

    return succeeded


def _check_bulk_graphql_errors(data: dict[str, Any]) -> None:
    """Check for GraphQL errors in bulk update response."""
    if "errors" not in data:
        return
    parsed_errors = parse_graphql_errors(data["errors"])
    raise GraphQLError(
        f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
        errors=parsed_errors,
        query=PRODUCT_VARIANTS_BULK_UPDATE_MUTATION,
    )


def _update_sku_cache_for_successes(
    sku_resolver: SKUResolverPort,
    succeeded: list[UpdateSuccess],
    product_gid: str,
    shop_url: str,
) -> None:
    """Update SKU cache for all successful variant updates."""
    for success in succeeded:
        if success.variant is not None:
            sku_resolver.update_from_variant(variant_gid=success.variant.id, product_gid=product_gid, sku=success.variant.sku, shop_url=shop_url)


def update_variants_bulk(
    session: ShopifySession,
    product_id: str,
    updates: list[VariantUpdateRequest],
    *,
    sku_resolver: SKUResolverPort | None = None,
) -> BulkUpdateResult:
    """Update multiple variants in one API call.

    Args:
        session: An active ShopifySession.
        product_id: Product GID or numeric ID.
        updates: List of VariantUpdateRequest objects.
        sku_resolver: Optional SKU resolver override. If not provided, uses the
            session's resolver (auto-resolved from config at login).
            Also used for cache updates after successful mutations.

    Returns:
        BulkUpdateResult with succeeded and failed updates.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the mutation fails.
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    shop_url = session.get_credentials().shop_url
    product_gid = _normalize_product_gid(product_id)
    resolver = _get_session_sku_resolver(session, sku_resolver)
    logger.info(f"Bulk updating {len(updates)} variant(s) for product '{product_gid}'")

    variant_inputs, identifier_map, failed = _resolve_and_build_variant_inputs(updates, shop_url, resolver)

    if not variant_inputs:
        return BulkUpdateResult(succeeded=[], failed=failed)

    try:
        raw_data = session.execute_graphql(
            PRODUCT_VARIANTS_BULK_UPDATE_MUTATION,
            variables={"productId": product_gid, "variants": variant_inputs},
        )

        _check_bulk_graphql_errors(raw_data)

        response = VariantsBulkUpdateResponse.model_validate(raw_data)
        mutation_data = response.mutation_data

        if mutation_data is not None:
            failed.extend(_process_mutation_user_errors(mutation_data.user_errors, variant_inputs, identifier_map))
            succeeded = _process_mutation_successes(mutation_data.product_variants, identifier_map)
        else:
            succeeded = []

        if resolver is not None:
            _update_sku_cache_for_successes(resolver, succeeded, product_gid, shop_url)

        return BulkUpdateResult(succeeded=succeeded, failed=failed)

    except GraphQLError:
        raise
    except Exception as exc:
        logger.error("Failed to bulk update variants", extra={"product_id": product_gid, "error": str(exc)})
        raise GraphQLError(f"Failed to bulk update variants: {exc}", query=PRODUCT_VARIANTS_BULK_UPDATE_MUTATION) from exc


__all__ = [
    "update_variants_bulk",
]
