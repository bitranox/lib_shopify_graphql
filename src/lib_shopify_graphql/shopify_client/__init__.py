"""Shopify GraphQL client for app authentication.

This package provides the core API for interacting with Shopify:
    - :func:`login`: Authenticate with Shopify using app credentials.
    - :func:`logout`: Terminate an active Shopify session.
    - :func:`get_product_by_id`: Retrieve full product information.
    - :class:`ShopifySession`: Active session wrapper.

Authentication:
    Uses OAuth 2.0 **Client Credentials Grant** for apps created via
    https://dev.shopify.com/dashboard. Requires client_id and client_secret.

Architecture:
    This module implements use cases that depend on application ports
    (Protocols), not on concrete implementations. The default Shopify
    SDK adapters are wired at import time for convenience.

Note:
    This library uses direct HTTP requests to Shopify's GraphQL Admin API.
    REST API is deprecated as of October 2024.
"""

from __future__ import annotations

# Cache operations
from ._cache import (
    CacheCheckResult,
    CacheMismatch,
    cache_clear_all,
    skucache_check,
    skucache_clear,
    tokencache_clear,
)

# Image operations
from ._images import (
    create_image,
    create_images,
    delete_image,
    delete_images,
    reorder_images,
    update_image,
)

# Inventory operations
from ._inventory import adjust_inventory, set_inventory

# Metafield operations
from ._metafields import delete_metafield, delete_metafields

# Product operations
from ._products import (
    create_product,
    delete_product,
    duplicate_product,
    get_product_by_id,
    get_product_by_sku,
    get_product_id_from_sku,
    iter_products,
    list_products,
    list_products_paginated,
    skucache_rebuild,
)

# Session management
from ._session import ShopifySession, login, logout

# Variant operations
from ._variants import update_product, update_variant
from ._variants_bulk import update_variants_bulk

__all__ = [
    "ShopifySession",
    # Cache operations
    "CacheCheckResult",
    "CacheMismatch",
    "cache_clear_all",
    "skucache_check",
    "skucache_clear",
    "skucache_rebuild",
    "tokencache_clear",
    # Create operations
    "create_product",
    # Delete operations
    "delete_metafield",
    "delete_metafields",
    "delete_product",
    # Duplicate operations
    "duplicate_product",
    # Read operations
    "get_product_by_id",
    "get_product_by_sku",
    "get_product_id_from_sku",
    "iter_products",
    "list_products",
    "list_products_paginated",
    # Session operations
    "login",
    "logout",
    # Update operations
    "adjust_inventory",
    "set_inventory",
    "update_product",
    "update_variant",
    "update_variants_bulk",
    # Image operations
    "create_image",
    "create_images",
    "delete_image",
    "delete_images",
    "reorder_images",
    "update_image",
]
