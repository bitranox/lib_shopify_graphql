"""Product query operations for Shopify API.

This module provides product retrieval and listing functionality.
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..application.ports import SKUResolverPort

from ..adapters.mutations import (
    PRODUCT_CREATE_MUTATION,
    PRODUCT_DELETE_MUTATION,
    PRODUCT_DUPLICATE_MUTATION,
)
from ..adapters.parsers import (
    build_product_create_input,
    format_graphql_errors,
    parse_graphql_errors,
    parse_product,
    parse_product_connection,
)
from ..adapters.queries import (
    PRODUCT_QUERY,
    PRODUCTS_LIST_QUERY,
    get_limits_from_config,
)
from ..exceptions import (
    AmbiguousSKUError,
    GraphQLError,
    ProductNotFoundError,
    SessionNotActiveError,
    VariantNotFoundError,
)
from ..models import (
    DeleteProductResult,
    DuplicateProductResult,
    PageInfo,
    Product,
    ProductConnection,
    ProductCreate,
    ProductStatus,
    ProductVariant,
)
from ..models._operations import UserErrorData
from ._common import _get_session_sku_resolver, _normalize_product_gid
from ._session import ShopifySession

logger = logging.getLogger(__name__)


def _validate_product_response(data: dict[str, Any], product_id: str) -> dict[str, Any]:
    """Validate GraphQL response and return product data or raise appropriate exception."""
    if "errors" in data:
        parsed_errors = parse_graphql_errors(data["errors"])
        raise GraphQLError(
            f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
            errors=parsed_errors,
            query=PRODUCT_QUERY,
        )
    product_data = data.get("data", {}).get("product")
    if product_data is None:
        raise ProductNotFoundError(product_id)
    return product_data


def get_product_by_id(
    session: ShopifySession,
    product_id: str,
    *,
    sku_resolver: SKUResolverPort | None = None,
) -> Product:
    """Retrieve full product information by Shopify product ID.

    Fetches complete product data including all variants and images
    using the Shopify GraphQL Admin API.

    Args:
        session: An active ShopifySession.
        product_id: Shopify product ID. Can be a numeric ID (e.g., '123456789')
            or a full GID (e.g., 'gid://shopify/Product/123456789').
        sku_resolver: Optional SKU resolver for cache updates. If provided,
            variant SKUs will be cached for faster SKU-to-GID lookups.

    Returns:
        A Product object containing all product information.

    Raises:
        SessionNotActiveError: If the session is not active.
        ProductNotFoundError: If the product does not exist.
        GraphQLError: If the GraphQL query returns errors.
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    shop_url = session.get_credentials().shop_url
    product_id = _normalize_product_gid(product_id)
    logger.info(f"Fetching product '{product_id}' from shop '{shop_url}'")

    try:
        data = session.execute_graphql(PRODUCT_QUERY, variables={"id": product_id})
        product_data = _validate_product_response(data, product_id)
        product = parse_product(product_data, operation="get_product_by_id")

        # Update SKU cache with product variants
        if sku_resolver is not None:
            sku_resolver.update_from_product(product, shop_url)

        logger.info(f"Successfully fetched product '{product.title}' ({product_id})")
        return product
    except (ProductNotFoundError, GraphQLError):
        raise
    except Exception as exc:
        logger.error(f"Failed to fetch product '{product_id}': {exc}")
        raise GraphQLError(f"Failed to fetch product: {exc}", query=PRODUCT_QUERY) from exc


def _clamp_page_size(first: int) -> int:
    """Clamp page size to valid range (1-250)."""
    return max(1, min(first, 250))


def _build_list_variables(first: int, after: str | None, query: str | None) -> dict[str, Any]:
    """Build GraphQL variables for list query."""
    variables: dict[str, Any] = {"first": first}
    if after is not None:
        variables["after"] = after
    if query is not None:
        variables["query"] = query
    return variables


def _check_list_errors(data: dict[str, Any]) -> None:
    """Check for and raise GraphQL errors from list response."""
    if "errors" not in data:
        return
    parsed_errors = parse_graphql_errors(data["errors"])
    raise GraphQLError(
        f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
        errors=parsed_errors,
        query=PRODUCTS_LIST_QUERY,
    )


def _update_sku_cache_from_products(
    sku_resolver: SKUResolverPort,
    products: list[Product],
    shop_url: str,
) -> None:
    """Update SKU cache with variants from products."""
    for product in products:
        sku_resolver.update_from_product(product, shop_url)


def list_products_paginated(
    session: ShopifySession,
    *,
    first: int = 50,
    after: str | None = None,
    query: str | None = None,
    sku_resolver: SKUResolverPort | None = None,
) -> ProductConnection:
    """List products with manual cursor-based pagination.

    Fetches a single page of products. For automatic pagination, use
    :func:`list_products` or :func:`iter_products` instead.

    Args:
        session: An active ShopifySession.
        first: Number of products per page (max 250). Defaults to 50.
        after: Cursor for pagination. Use page_info.end_cursor from previous
            response to get the next page.
        query: Shopify search query string. Supports filters like:
            - "title:*shirt*" - Products with 'shirt' in title
            - "updated_at:>2024-01-01" - Products updated after date
            - "status:active" - Only active products
            - "vendor:Nike" - Products from specific vendor
        sku_resolver: Optional SKU resolver for cache updates. If provided,
            variant SKUs will be cached for faster SKU-to-GID lookups.

    Returns:
        ProductConnection with products list and pagination info.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the GraphQL query returns errors.
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    first = _clamp_page_size(first)
    variables = _build_list_variables(first, after, query)

    page_info_msg = "first page" if after is None else "next page"
    filter_msg = f', filter: "{query}"' if query else ""
    logger.info(f"Fetching products ({page_info_msg}, up to {first} products{filter_msg})...")

    try:
        data = session.execute_graphql(PRODUCTS_LIST_QUERY, variables=variables)
        _check_list_errors(data)

        products_data = data.get("data", {}).get("products")
        if products_data is None:
            return ProductConnection(products=[], page_info=PageInfo(has_next_page=False))

        result = parse_product_connection(products_data, operation="list_products_paginated")

        if sku_resolver is not None:
            _update_sku_cache_from_products(sku_resolver, result.products, session.get_credentials().shop_url)

        more_msg = ", more pages available" if result.page_info.has_next_page else ", no more pages"
        logger.info(f"Fetched {len(result.products)} products{more_msg}")
        return result

    except GraphQLError:
        raise
    except Exception as exc:
        logger.error(f"Failed to list products: {exc}")
        raise GraphQLError(f"Failed to list products: {exc}", query=PRODUCTS_LIST_QUERY) from exc


def iter_products(
    session: ShopifySession,
    *,
    query: str | None = None,
    sku_resolver: SKUResolverPort | None = None,
) -> Iterator[Product]:
    """Iterate over all products, fetching pages lazily.

    Memory efficient - fetches products in batches (default 250), yielding
    one product at a time. Ideal for processing large catalogs without
    loading all products into memory.

    The page size is configurable via [graphql] iter_page_size in config.

    Args:
        session: An active ShopifySession.
        query: Shopify search query string. Supports filters like:
            - "title:*shirt*" - Products with 'shirt' in title
            - "updated_at:>2024-01-01" - Products updated after date
            - "status:active" - Only active products
            - "vendor:Nike" - Products from specific vendor
        sku_resolver: Optional SKU resolver for cache updates. If provided,
            variant SKUs will be cached for faster SKU-to-GID lookups.

    Yields:
        Product objects one at a time.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the GraphQL query returns errors.

    Example:
        >>> for product in iter_products(session, query="status:active"):  # doctest: +SKIP
        ...     print(product.title)
    """
    limits = get_limits_from_config()
    page_size = limits.product_iter_page_size
    cursor: str | None = None
    while True:
        result = list_products_paginated(
            session,
            first=page_size,
            after=cursor,
            query=query,
            sku_resolver=sku_resolver,
        )
        yield from result.products
        if not result.page_info.has_next_page:
            break
        cursor = result.page_info.end_cursor


def list_products(
    session: ShopifySession,
    *,
    query: str | None = None,
    max_products: int | None = None,
    sku_resolver: SKUResolverPort | None = None,
) -> list[Product]:
    """Fetch all products, handling pagination automatically.

    Convenience function that collects all products into a list.
    For shops with very large catalogs (10,000+ products), consider using
    :func:`iter_products` for memory efficiency or :func:`list_products_paginated`
    for manual control.

    Args:
        session: An active ShopifySession.
        query: Shopify search query string. Supports filters like:
            - "title:*shirt*" - Products with 'shirt' in title
            - "updated_at:>2024-01-01" - Products updated after date
            - "status:active" - Only active products
            - "vendor:Nike" - Products from specific vendor
        max_products: Maximum number of products to fetch (None = unlimited).
            Use as a safety limit for large shops.
        sku_resolver: Optional SKU resolver for cache updates. If provided,
            variant SKUs will be cached for faster SKU-to-GID lookups.

    Returns:
        List of all matching products.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the GraphQL query returns errors.

    Example:
        >>> products = list_products(session, query="status:active")  # doctest: +SKIP
        >>> print(f"Found {len(products)} products")  # doctest: +SKIP
    """
    iterator = iter_products(session, query=query, sku_resolver=sku_resolver)
    if max_products is not None:
        return list(itertools.islice(iterator, max_products))
    return list(iterator)


def _query_variant_product(session: ShopifySession, variant_gid: str, sku: str) -> str | None:
    """Query single variant's parent product ID.

    Args:
        session: Active Shopify session.
        variant_gid: Variant GID to query.
        sku: Original SKU (for logging).

    Returns:
        Product GID if found, None on error.
    """
    query = """
    query VariantProduct($id: ID!) {
        productVariant(id: $id) {
            product { id }
        }
    }
    """
    try:
        data = session.execute_graphql(query, variables={"id": variant_gid})

        if "errors" in data:
            parsed_errors = parse_graphql_errors(data["errors"])
            logger.warning(
                f"GraphQL error resolving variant to product: sku='{sku}', variant_gid='{variant_gid}', errors={format_graphql_errors(parsed_errors)}"
            )
            return None

        product_data = data.get("data", {}).get("productVariant", {}).get("product")
        if product_data is None:
            logger.warning(f"Variant has no parent product: sku='{sku}', variant_gid='{variant_gid}'")
            return None

        product_id = product_data["id"]
        logger.debug(
            "Resolved variant to product",
            extra={"sku": sku, "variant_gid": variant_gid, "product_id": product_id},
        )
        return product_id

    except Exception as exc:
        logger.warning(f"Failed to resolve variant to product: sku='{sku}', variant_gid='{variant_gid}', error={exc}")
        return None


def get_product_id_from_sku(
    session: ShopifySession,
    sku: str,
    *,
    sku_resolver: SKUResolverPort | None = None,
) -> list[str]:
    """Get all product GIDs for variants with a given SKU.

    This function resolves a SKU to all variants that have it, then returns
    the parent product GIDs. Useful when you have a SKU and need to find
    which product(s) contain variants with that SKU.

    Note:
        In Shopify, SKUs should typically be unique, but multiple variants
        (possibly on different products) can have the same SKU. This function
        returns ALL matching products.

    Args:
        session: An active ShopifySession.
        sku: The variant SKU to look up.
        sku_resolver: Optional SKU resolver. If not provided, uses the
            session's resolver (auto-resolved from config at login).

    Returns:
        List of product GIDs (e.g., ["gid://shopify/Product/123"]).
        Returns empty list if SKU not found.

    Raises:
        SessionNotActiveError: If the session is not active.
        ValueError: If no SKU resolver is available.
        GraphQLError: If the query fails.

    Example:
        >>> from lib_shopify_graphql import login, get_product_id_from_sku
        >>> session = login(credentials)  # doctest: +SKIP
        >>> product_ids = get_product_id_from_sku(session, "ABC-123")  # doctest: +SKIP
        >>> if product_ids:  # doctest: +SKIP
        ...     for pid in product_ids:
        ...         print(f"Found product: {pid}")
        ... else:
        ...     print("SKU not found")
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    resolver = _get_session_sku_resolver(session, sku_resolver)
    if resolver is None:
        raise ValueError("No SKU resolver available. Enable SKU cache in config or provide sku_resolver parameter.")

    logger.debug("Resolving SKU to product IDs", extra={"sku": sku})

    # Resolve SKU to ALL variant GIDs
    variant_gids = resolver.resolve_all(sku)

    if not variant_gids:
        logger.info(f"SKU '{sku}' not found")
        return []

    # Use set to deduplicate (multiple variants on same product)
    product_ids: set[str] = set()

    for variant_gid in variant_gids:
        product_id = _query_variant_product(session, variant_gid, sku)
        if product_id:
            product_ids.add(product_id)

    result = list(product_ids)
    logger.info(f"Resolved SKU '{sku}' to {len(result)} product(s) from {len(variant_gids)} variant(s)")
    return result


def get_product_by_sku(
    session: ShopifySession,
    sku: str,
    *,
    sku_resolver: SKUResolverPort | None = None,
) -> Product:
    """Retrieve product by variant SKU.

    Fetches the full product that contains a variant with the given SKU.
    If the SKU matches variants on multiple different products, raises
    AmbiguousSKUError.

    Args:
        session: An active ShopifySession.
        sku: The variant SKU to look up.
        sku_resolver: Optional SKU resolver for cache. If not provided,
            a default resolver will be used.

    Returns:
        The Product containing the variant with the given SKU.

    Raises:
        SessionNotActiveError: If the session is not active.
        VariantNotFoundError: If no variant has this SKU.
        AmbiguousSKUError: If SKU matches variants on multiple products.
        GraphQLError: If the query fails.

    Example:
        >>> from lib_shopify_graphql import login, get_product_by_sku
        >>> session = login(credentials)  # doctest: +SKIP
        >>> product = get_product_by_sku(session, "ABC-123")  # doctest: +SKIP
        >>> print(f"Product: {product.title}")  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    logger.debug("Fetching product by SKU", extra={"sku": sku})

    # Get product IDs for this SKU
    product_ids = get_product_id_from_sku(session, sku, sku_resolver=sku_resolver)

    if not product_ids:
        raise VariantNotFoundError(sku, f"SKU not found: {sku}")

    if len(product_ids) > 1:
        raise AmbiguousSKUError(
            sku,
            product_ids,
            f"SKU '{sku}' exists on {len(product_ids)} different products",
        )

    return get_product_by_id(session, product_ids[0], sku_resolver=sku_resolver)


def _process_variant_for_cache(
    variant: ProductVariant,
    product: Product,
    seen_skus: dict[str, list[str]],
) -> bool:
    """Process a variant and track its SKU.

    Returns:
        True if variant has SKU, False otherwise.
    """
    if not variant.sku:
        logger.warning(f"Variant without SKU: product='{product.title}' ({product.id}), variant='{variant.title}' ({variant.id})")
        return False

    seen_skus.setdefault(variant.sku, []).append(variant.id)
    return True


def _log_duplicate_skus(seen_skus: dict[str, list[str]]) -> int:
    """Log duplicate SKUs and return count of duplicates."""
    duplicate_count = 0
    for sku, variant_ids in seen_skus.items():
        if len(variant_ids) > 1:
            duplicate_count += 1
            logger.warning(f"Duplicate SKU '{sku}' found in {len(variant_ids)} variants: {variant_ids}")
    return duplicate_count


def skucache_rebuild(
    session: ShopifySession,
    *,
    sku_resolver: SKUResolverPort | None = None,
    query: str | None = None,
) -> int:
    """Rebuild SKU cache by reading all products from the store.

    Iterates through all products and updates the SKU cache with every
    variant's SKU-to-GID mapping. Use this to rebuild the cache after
    bulk changes or verify cache consistency.

    Args:
        session: An active ShopifySession.
        sku_resolver: SKU resolver with cache to rebuild. Required.
        query: Optional Shopify query filter (e.g., "status:active").

    Returns:
        Total number of variants cached.

    Raises:
        SessionNotActiveError: If the session is not active.
        ValueError: If sku_resolver is not provided.
        GraphQLError: If the query fails.

    Example:
        >>> from lib_shopify_graphql import login, skucache_rebuild
        >>> session = login(credentials)  # doctest: +SKIP
        >>> count = skucache_rebuild(session, sku_resolver=resolver)  # doctest: +SKIP
        >>> print(f"Cached {count} variant SKUs")  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    if sku_resolver is None:
        raise ValueError("sku_resolver is required for skucache_rebuild")

    shop_url = session.get_credentials().shop_url
    total_variants = 0
    variants_without_sku = 0
    seen_skus: dict[str, list[str]] = {}

    filter_msg = f' with filter "{query}"' if query else ""
    logger.info(f"Starting cache rebuild for shop '{shop_url}'{filter_msg}")

    for product in iter_products(session, query=query, sku_resolver=sku_resolver):
        for variant in product.variants:
            total_variants += 1
            if not _process_variant_for_cache(variant, product, seen_skus):
                variants_without_sku += 1

    duplicate_count = _log_duplicate_skus(seen_skus)

    logger.info(f"Cache rebuild complete: {total_variants} variants, {variants_without_sku} without SKU, {duplicate_count} duplicate SKUs")
    return total_variants


# =============================================================================
# Product Lifecycle Operations
# =============================================================================


def _check_create_graphql_errors(data: dict[str, Any]) -> None:
    """Check for GraphQL errors in create response."""
    if "errors" not in data:
        return
    parsed_errors = parse_graphql_errors(data["errors"])
    raise GraphQLError(
        f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
        errors=parsed_errors,
        query=PRODUCT_CREATE_MUTATION,
    )


def _check_create_user_errors(user_errors: list[UserErrorData]) -> None:
    """Check for user errors in create response."""
    if not user_errors:
        return
    error_messages = "; ".join(f"{e.field or ['unknown']}: {e.message}" for e in user_errors)
    raise GraphQLError(f"Product creation failed: {error_messages}", query=PRODUCT_CREATE_MUTATION)


def create_product(
    session: ShopifySession,
    product: ProductCreate,
    *,
    sku_resolver: SKUResolverPort | None = None,
) -> Product:
    """Create a new product in Shopify.

    Args:
        session: An active ShopifySession.
        product: ProductCreate with product data.
        sku_resolver: Optional SKU resolver for cache updates. If provided,
            new variant SKUs will be cached for faster lookups.

    Returns:
        The created Product.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the mutation fails.
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    shop_url = session.get_credentials().shop_url
    logger.info(f"Creating product '{product.title}' in shop '{shop_url}'")

    try:
        product_input = build_product_create_input(product)
        data = session.execute_graphql(PRODUCT_CREATE_MUTATION, variables={"input": product_input})

        _check_create_graphql_errors(data)

        result = data.get("data", {}).get("productCreate", {})
        raw_user_errors = result.get("userErrors", [])
        user_errors = [UserErrorData.model_validate(e) for e in raw_user_errors]
        _check_create_user_errors(user_errors)

        product_data = result.get("product")
        if product_data is None:
            raise GraphQLError("Product creation returned no product data", query=PRODUCT_CREATE_MUTATION)

        created_product = parse_product(product_data, operation="create_product")

        if sku_resolver is not None:
            sku_resolver.update_from_product(created_product, shop_url)

        logger.info(f"Product created successfully: '{created_product.title}' ({created_product.id})")
        return created_product

    except GraphQLError:
        raise
    except Exception as exc:
        logger.error(f"Failed to create product '{product.title}': {exc}")
        raise GraphQLError(f"Failed to create product: {exc}", query=PRODUCT_CREATE_MUTATION) from exc


def _build_duplicate_variables(
    product_gid: str,
    new_title: str,
    include_images: bool,
    new_status: ProductStatus | None,
) -> dict[str, Any]:
    """Build variables for duplicate mutation."""
    variables: dict[str, Any] = {
        "productId": product_gid,
        "newTitle": new_title,
        "includeImages": include_images,
    }
    if new_status is not None:
        variables["newStatus"] = new_status.value
    return variables


def _check_duplicate_graphql_errors(data: dict[str, Any], product_gid: str) -> None:
    """Check for GraphQL errors in duplicate response."""
    if "errors" not in data:
        return
    parsed_errors = parse_graphql_errors(data["errors"])
    error_msg = format_graphql_errors(parsed_errors)
    if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
        raise ProductNotFoundError(product_gid)
    raise GraphQLError(f"GraphQL errors: {error_msg}", errors=parsed_errors, query=PRODUCT_DUPLICATE_MUTATION)


def _check_duplicate_user_errors(user_errors: list[UserErrorData], product_gid: str) -> None:
    """Check for user errors in duplicate response."""
    if not user_errors:
        return
    error_messages = "; ".join(f"{e.field or ['unknown']}: {e.message}" for e in user_errors)
    if "not found" in error_messages.lower():
        raise ProductNotFoundError(product_gid)
    raise GraphQLError(f"Product duplication failed: {error_messages}", query=PRODUCT_DUPLICATE_MUTATION)


def duplicate_product(
    session: ShopifySession,
    product_id: str,
    new_title: str,
    *,
    include_images: bool = True,
    new_status: ProductStatus | None = None,
    sku_resolver: SKUResolverPort | None = None,
) -> DuplicateProductResult:
    """Duplicate an existing product.

    Creates a copy of an existing product with a new title.

    Args:
        session: An active ShopifySession.
        product_id: ID of the product to duplicate.
        new_title: Title for the duplicated product.
        include_images: Whether to copy images. Defaults to True.
        new_status: Optional status for the new product.
        sku_resolver: Optional SKU resolver for cache updates. If provided,
            new variant SKUs will be cached for faster lookups.

    Returns:
        DuplicateProductResult with the new product.

    Raises:
        SessionNotActiveError: If the session is not active.
        ProductNotFoundError: If the product doesn't exist.
        GraphQLError: If the mutation fails.
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    shop_url = session.get_credentials().shop_url
    product_gid = _normalize_product_gid(product_id)

    logger.info(f"Duplicating product '{product_gid}' with new title '{new_title}'")

    try:
        variables = _build_duplicate_variables(product_gid, new_title, include_images, new_status)
        data = session.execute_graphql(PRODUCT_DUPLICATE_MUTATION, variables=variables)

        _check_duplicate_graphql_errors(data, product_gid)

        result = data.get("data", {}).get("productDuplicate", {})
        raw_user_errors = result.get("userErrors", [])
        user_errors = [UserErrorData.model_validate(e) for e in raw_user_errors]
        _check_duplicate_user_errors(user_errors, product_gid)

        new_product_data = result.get("newProduct")
        if new_product_data is None:
            raise GraphQLError("Product duplication returned no product data", query=PRODUCT_DUPLICATE_MUTATION)

        new_product = parse_product(new_product_data, operation="duplicate_product")

        if sku_resolver is not None:
            sku_resolver.update_from_product(new_product, shop_url)

        logger.info(f"Product duplicated successfully: {product_gid} -> {new_product.id}")
        return DuplicateProductResult(new_product=new_product, original_product_id=product_gid)

    except (ProductNotFoundError, GraphQLError):
        raise
    except Exception as exc:
        logger.error(f"Failed to duplicate product '{product_gid}': {exc}")
        raise GraphQLError(f"Failed to duplicate product: {exc}", query=PRODUCT_DUPLICATE_MUTATION) from exc


def _collect_variant_skus(session: ShopifySession, product_gid: str) -> list[str]:
    """Collect variant SKUs from a product for cache invalidation."""
    try:
        product = get_product_by_id(session, product_gid)
        return [v.sku for v in product.variants if v.sku]
    except ProductNotFoundError:
        return []  # Product already deleted or never existed


def _check_delete_graphql_errors(data: dict[str, Any], product_gid: str) -> None:
    """Check for GraphQL-level errors and raise appropriate exceptions."""
    if "errors" not in data:
        return

    parsed_errors = parse_graphql_errors(data["errors"])
    error_msg = format_graphql_errors(parsed_errors)

    if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
        raise ProductNotFoundError(product_gid)

    raise GraphQLError(
        f"GraphQL errors: {error_msg}",
        errors=parsed_errors,
        query=PRODUCT_DELETE_MUTATION,
    )


def _check_delete_user_errors(user_errors: list[UserErrorData], product_gid: str) -> None:
    """Check for user errors and raise appropriate exceptions."""
    if not user_errors:
        return

    error_messages = "; ".join(f"{e.field or ['unknown']}: {e.message}" for e in user_errors)

    if "not found" in error_messages.lower():
        raise ProductNotFoundError(product_gid)

    raise GraphQLError(f"Product deletion failed: {error_messages}", query=PRODUCT_DELETE_MUTATION)


def _invalidate_sku_cache(
    sku_resolver: SKUResolverPort,
    variant_skus: list[str],
    shop_url: str,
) -> None:
    """Invalidate SKU cache entries for deleted variants."""
    for sku in variant_skus:
        try:
            sku_resolver.invalidate(sku, shop_url)
        except Exception as cache_exc:
            logger.warning(f"Failed to invalidate SKU cache entry: sku='{sku}', error={cache_exc}")


def delete_product(
    session: ShopifySession,
    product_id: str,
    *,
    sku_resolver: SKUResolverPort | None = None,
) -> DeleteProductResult:
    """Delete a product permanently.

    WARNING: This operation is irreversible. The product and all its
    variants, inventory, images, and associated data will be permanently
    deleted.

    Args:
        session: An active ShopifySession.
        product_id: ID of the product to delete. Can be numeric or GID format.
        sku_resolver: Optional SKU resolver. If provided, SKU cache entries
            for deleted variants will be invalidated.

    Returns:
        DeleteProductResult confirming the deletion.

    Raises:
        SessionNotActiveError: If the session is not active.
        ProductNotFoundError: If the product doesn't exist.
        GraphQLError: If the deletion fails.

    Example:
        >>> result = delete_product(session, "gid://shopify/Product/123456789")  # doctest: +SKIP
        >>> print(result.deleted_product_id)  # doctest: +SKIP
        gid://shopify/Product/123456789
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    shop_url = session.get_credentials().shop_url
    product_gid = _normalize_product_gid(product_id)

    # Collect variant SKUs before deletion for cache invalidation
    variant_skus = _collect_variant_skus(session, product_gid) if sku_resolver else []

    logger.info(f"Deleting product '{product_gid}' from shop '{shop_url}'")

    try:
        data = session.execute_graphql(
            PRODUCT_DELETE_MUTATION,
            variables={"input": {"id": product_gid}},
        )

        _check_delete_graphql_errors(data, product_gid)

        result = data.get("data", {}).get("productDelete", {})
        raw_user_errors = result.get("userErrors", [])
        user_errors = [UserErrorData.model_validate(e) for e in raw_user_errors]
        _check_delete_user_errors(user_errors, product_gid)

        deleted_id = result.get("deletedProductId")
        if deleted_id is None:
            raise GraphQLError("Product deletion returned no deleted ID", query=PRODUCT_DELETE_MUTATION)

        if sku_resolver and variant_skus:
            _invalidate_sku_cache(sku_resolver, variant_skus, shop_url)
            logger.info(f"Product deleted successfully: {deleted_id}, cleared {len(variant_skus)} SKU cache entries")
        else:
            logger.info(f"Product deleted successfully: {deleted_id}")

        return DeleteProductResult(deleted_product_id=deleted_id)

    except (ProductNotFoundError, GraphQLError):
        raise
    except Exception as exc:
        logger.error(f"Failed to delete product '{product_gid}': {exc}")
        raise GraphQLError(f"Failed to delete product: {exc}", query=PRODUCT_DELETE_MUTATION) from exc


__all__ = [
    "create_product",
    "delete_product",
    "duplicate_product",
    "get_product_by_id",
    "get_product_by_sku",
    "get_product_id_from_sku",
    "iter_products",
    "list_products",
    "list_products_paginated",
    "skucache_rebuild",
]
