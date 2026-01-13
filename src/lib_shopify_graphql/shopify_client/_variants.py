"""Variant update operations for Shopify API.

This module provides single variant and product update functionality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..application.ports import SKUResolverPort

from ..adapters.mutations import (
    PRODUCT_UPDATE_MUTATION,
    PRODUCT_VARIANTS_BULK_UPDATE_MUTATION,
)
from ..adapters.parsers import (
    build_product_input,
    build_variant_input,
    format_graphql_errors,
    parse_variant_from_mutation,
)
from ..exceptions import GraphQLError, GraphQLErrorEntry, GraphQLErrorLocation, ProductNotFoundError, SessionNotActiveError, VariantNotFoundError
from ..models import Product, ProductUpdate, ProductVariant, VariantUpdate
from ..models._operations import (
    GraphQLErrorData,
    ProductUpdateResponse,
    UserErrorData,
    VariantsBulkUpdateResponse,
)
from ._common import _get_session_sku_resolver, _normalize_product_gid, _resolve_variant_identifier
from ._products import get_product_by_id
from ._session import ShopifySession

logger = logging.getLogger(__name__)


def _convert_graphql_error_data_to_entry(error_data: GraphQLErrorData) -> GraphQLErrorEntry:
    """Convert a GraphQLErrorData Pydantic model to a GraphQLErrorEntry dataclass."""
    locations = None
    if error_data.locations:
        locations = tuple(GraphQLErrorLocation(line=loc.line, column=loc.column) for loc in error_data.locations)
    path = tuple(error_data.path) if error_data.path else None
    extensions = error_data.extensions.model_dump() if error_data.extensions else None
    return GraphQLErrorEntry(
        message=error_data.message,
        locations=locations,
        path=path,
        extensions=extensions,
    )


def _get_product_id_for_variant(session: ShopifySession, variant_gid: str) -> str:
    """Get the product ID for a variant by querying Shopify."""
    query = """
    query VariantProduct($id: ID!) {
        productVariant(id: $id) {
            product { id }
        }
    }
    """
    data = session.execute_graphql(query, variables={"id": variant_gid})
    product_data = data.get("data", {}).get("productVariant", {}).get("product")
    if product_data is None:
        raise VariantNotFoundError(variant_gid)
    return product_data["id"]


def _check_product_graphql_errors(response: ProductUpdateResponse) -> None:
    """Check for GraphQL errors in product update response."""
    if not response.has_graphql_errors:
        return
    error_data_list = response.errors or []
    errors = [_convert_graphql_error_data_to_entry(e) for e in error_data_list]
    raise GraphQLError(
        f"GraphQL errors: {format_graphql_errors(errors)}",
        errors=errors,
        query=PRODUCT_UPDATE_MUTATION,
    )


def _check_product_user_errors(user_errors: list[UserErrorData]) -> None:
    """Check for user errors in product update response."""
    if not user_errors:
        return
    first_error = user_errors[0]
    raise GraphQLError(f"Product update failed: {first_error.message}", query=PRODUCT_UPDATE_MUTATION)


def update_product(
    session: ShopifySession,
    product_id: str,
    update: ProductUpdate,
    *,
    sku_resolver: SKUResolverPort | None = None,
) -> Product:
    """Update product fields.

    Only fields with values (not UNSET) are sent to Shopify.
    Fields set to None are cleared on Shopify.

    Args:
        session: An active ShopifySession.
        product_id: Product GID or numeric ID.
        update: ProductUpdate with fields to update.
        sku_resolver: Optional SKU resolver for cache updates.
            If None, SKU cache is not updated after the operation.

    Returns:
        Updated Product object.

    Raises:
        SessionNotActiveError: If the session is not active.
        ProductNotFoundError: If the product does not exist.
        GraphQLError: If the mutation fails.

    Example:
        >>> from lib_shopify_graphql import login, update_product, ProductUpdate, ProductStatus
        >>> session = login(credentials)  # doctest: +SKIP
        >>> updated = update_product(  # doctest: +SKIP
        ...     session,
        ...     "gid://shopify/Product/123",
        ...     ProductUpdate(title="New Title", status=ProductStatus.ACTIVE),
        ... )
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    product_id = _normalize_product_gid(product_id)
    logger.info(f"Updating product '{product_id}'")

    try:
        product_input = build_product_input(product_id, update)
        raw_data = session.execute_graphql(PRODUCT_UPDATE_MUTATION, variables={"input": product_input})
        response = ProductUpdateResponse.model_validate(raw_data)

        _check_product_graphql_errors(response)
        mutation_data = response.mutation_data
        if mutation_data is not None:
            _check_product_user_errors(mutation_data.user_errors)
            if mutation_data.product is None:
                raise ProductNotFoundError(product_id)
        else:
            raise ProductNotFoundError(product_id)

        return get_product_by_id(session, product_id, sku_resolver=sku_resolver)

    except (ProductNotFoundError, GraphQLError):
        raise
    except Exception as exc:
        logger.error(f"Failed to update product '{product_id}': {exc}")
        raise GraphQLError(f"Failed to update product: {exc}", query=PRODUCT_UPDATE_MUTATION) from exc


def _check_variant_graphql_errors(response: VariantsBulkUpdateResponse) -> None:
    """Check for GraphQL errors in variant update response."""
    if not response.has_graphql_errors:
        return
    error_data_list = response.errors or []
    errors = [_convert_graphql_error_data_to_entry(e) for e in error_data_list]
    raise GraphQLError(
        f"GraphQL errors: {format_graphql_errors(errors)}",
        errors=errors,
        query=PRODUCT_VARIANTS_BULK_UPDATE_MUTATION,
    )


def _check_variant_user_errors(user_errors: list[UserErrorData]) -> None:
    """Check for user errors in variant update response."""
    if not user_errors:
        return
    first_error = user_errors[0]
    raise GraphQLError(f"Variant update failed: {first_error.message}", query=PRODUCT_VARIANTS_BULK_UPDATE_MUTATION)


def update_variant(
    session: ShopifySession,
    variant_id_or_sku: str,
    update: VariantUpdate,
    *,
    product_id: str | None = None,
    sku_resolver: SKUResolverPort | None = None,
) -> ProductVariant:
    """Update a single variant.

    Args:
        session: An active ShopifySession.
        variant_id_or_sku: Variant GID, numeric ID, or SKU.
        update: VariantUpdate with fields to update.
        product_id: Optional product GID (queried if not provided).
        sku_resolver: Optional SKU resolver override. If not provided, uses the
            session's resolver (auto-resolved from config at login).

    Returns:
        Updated ProductVariant object.

    Raises:
        SessionNotActiveError: If the session is not active.
        VariantNotFoundError: If variant not found or SKU cannot be resolved.
        GraphQLError: If the mutation fails.
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    shop_url = session.get_credentials().shop_url
    resolver = _get_session_sku_resolver(session, sku_resolver)
    variant_gid = _resolve_variant_identifier(variant_id_or_sku, shop_url, resolver)
    logger.info(f"Updating variant '{variant_gid}' (identifier='{variant_id_or_sku}')")

    try:
        if product_id is None:
            product_id = _get_product_id_for_variant(session, variant_gid)

        product_gid = _normalize_product_gid(product_id)
        variant_input = build_variant_input(variant_gid, update)

        raw_data = session.execute_graphql(
            PRODUCT_VARIANTS_BULK_UPDATE_MUTATION,
            variables={"productId": product_gid, "variants": [variant_input]},
        )
        response = VariantsBulkUpdateResponse.model_validate(raw_data)

        _check_variant_graphql_errors(response)

        mutation_data = response.mutation_data
        if mutation_data is None:
            raise VariantNotFoundError(variant_id_or_sku)

        _check_variant_user_errors(mutation_data.user_errors)

        variants = mutation_data.product_variants
        if not variants:
            raise VariantNotFoundError(variant_id_or_sku)

        updated_variant = parse_variant_from_mutation(variants[0])

        if resolver is not None:
            resolver.update_from_variant(variant_gid=updated_variant.id, product_gid=product_gid, sku=updated_variant.sku, shop_url=shop_url)

        return updated_variant

    except (VariantNotFoundError, GraphQLError):
        raise
    except Exception as exc:
        logger.error("Failed to update variant", extra={"variant_id": variant_id_or_sku, "error": str(exc)})
        raise GraphQLError(f"Failed to update variant: {exc}", query=PRODUCT_VARIANTS_BULK_UPDATE_MUTATION) from exc


__all__ = [
    "update_product",
    "update_variant",
]
