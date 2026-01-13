"""Common utilities for Shopify client operations.

This module provides shared helpers for GID normalization, identifier resolution,
and default adapter access. These utilities are used across all client submodules.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from ..application.ports import (
        GraphQLClientPort,
        SessionManagerPort,
        SKUResolverPort,
        TokenProviderPort,
    )
    from ._session import ShopifySession

from ..exceptions import VariantNotFoundError

logger = logging.getLogger(__name__)

# LRU cache sizes for GID normalization functions
_GID_CACHE_SIZE = 2048
_MEDIA_GID_CACHE_SIZE = 512


class _AdaptersCache(TypedDict):
    """Type-safe cache for default adapters."""

    token_provider: TokenProviderPort
    session_manager: SessionManagerPort
    graphql_client: GraphQLClientPort


# Default adapters are lazily loaded from composition.py.
# This avoids coupling this module to concrete adapter implementations.
_default_adapters_cache: _AdaptersCache | None = None
_default_adapters_lock = threading.Lock()


def _ensure_adapters_cache() -> _AdaptersCache:
    """Ensure the adapters cache is initialized and return it.

    Uses double-checked locking for thread-safe lazy initialization.

    Returns:
        The initialized adapters cache.
    """
    global _default_adapters_cache
    if _default_adapters_cache is None:
        with _default_adapters_lock:
            # Double-check after acquiring lock (another thread may have initialized)
            if _default_adapters_cache is None:
                # Import here to avoid circular imports
                from ..composition import get_default_adapters

                bundle = get_default_adapters()
                _default_adapters_cache = {
                    "token_provider": bundle["token_provider"],
                    "session_manager": bundle["session_manager"],
                    "graphql_client": bundle["graphql_client"],
                }
    return _default_adapters_cache


def _get_default_token_provider() -> TokenProviderPort:
    """Get the default token provider with proper type."""
    return _ensure_adapters_cache()["token_provider"]


def _get_default_session_manager() -> SessionManagerPort:
    """Get the default session manager with proper type."""
    return _ensure_adapters_cache()["session_manager"]


def _get_default_graphql_client() -> GraphQLClientPort:
    """Get the default GraphQL client with proper type."""
    return _ensure_adapters_cache()["graphql_client"]


@lru_cache(maxsize=_GID_CACHE_SIZE)
def _normalize_gid(resource_id: str, resource_type: str) -> str:
    """Normalize resource ID to GID format.

    Args:
        resource_id: Resource ID (numeric or full GID).
        resource_type: Shopify resource type (e.g., 'Product', 'ProductVariant').

    Returns:
        Full GID format (e.g., 'gid://shopify/Product/123').
    """
    if resource_id.startswith("gid://"):
        return resource_id
    return f"gid://shopify/{resource_type}/{resource_id}"


def _normalize_product_gid(product_id: str) -> str:
    """Normalize product ID to GID format."""
    return _normalize_gid(product_id, "Product")


def _normalize_variant_gid(variant_id: str) -> str:
    """Normalize variant ID to GID format."""
    return _normalize_gid(variant_id, "ProductVariant")


def _normalize_owner_gid(owner_id: str) -> str:
    """Normalize owner ID to GID format. Assumes Product for numeric IDs."""
    return _normalize_gid(owner_id, "Product")


@lru_cache(maxsize=_MEDIA_GID_CACHE_SIZE)
def _normalize_media_gid(media_id: str) -> str:
    """Normalize media/image ID to GID format.

    Converts ProductImage GIDs to MediaImage GIDs since the media mutations
    require MediaImage format.

    Args:
        media_id: Media ID (numeric, ProductImage GID, or MediaImage GID).

    Returns:
        Full GID format (e.g., 'gid://shopify/MediaImage/123').
    """
    if media_id.startswith("gid://shopify/ProductImage/"):
        # Convert ProductImage GID to MediaImage GID
        numeric_id = media_id.split("/")[-1]
        return f"gid://shopify/MediaImage/{numeric_id}"
    if media_id.startswith("gid://"):
        return media_id
    return f"gid://shopify/MediaImage/{media_id}"


def _resolve_variant_identifier(
    identifier: str,
    shop_url: str,
    sku_resolver: SKUResolverPort | None,
) -> str:
    """Resolve variant identifier (GID or SKU) to a GID.

    Args:
        identifier: Variant GID, numeric ID, or SKU.
        shop_url: Shopify store URL for SKU resolution.
        sku_resolver: Optional SKU resolver for SKU lookups.

    Returns:
        Variant GID.

    Raises:
        VariantNotFoundError: If SKU cannot be resolved.
    """
    # Already a GID or numeric ID
    if identifier.startswith("gid://") or identifier.isdigit():
        return _normalize_variant_gid(identifier)

    # Try SKU resolution
    if sku_resolver is None:
        raise VariantNotFoundError(identifier, f"Cannot resolve SKU '{identifier}': no SKU resolver configured")

    gid = sku_resolver.resolve(identifier, shop_url)
    if gid is None:
        raise VariantNotFoundError(identifier, f"SKU not found: {identifier}")

    return gid


def _get_session_sku_resolver(
    session: ShopifySession,
    explicit_resolver: SKUResolverPort | None,
) -> SKUResolverPort | None:
    """Get SKU resolver from session or explicit parameter.

    Priority:
    1. Explicit parameter (allows user override)
    2. Session-attached resolver (auto-resolved from config at login)
    3. None (no resolver available)

    Args:
        session: Active ShopifySession.
        explicit_resolver: Optional explicit resolver to use instead of session's.

    Returns:
        SKU resolver if available, None otherwise.
    """
    if explicit_resolver is not None:
        return explicit_resolver
    return getattr(session, "_sku_resolver", None)


__all__ = [
    "_ensure_adapters_cache",
    "_get_default_graphql_client",
    "_get_default_session_manager",
    "_get_default_token_provider",
    "_get_session_sku_resolver",
    "_normalize_gid",
    "_normalize_media_gid",
    "_normalize_owner_gid",
    "_normalize_product_gid",
    "_normalize_variant_gid",
    "_resolve_variant_identifier",
    "logger",
]
