"""Public package surface for lib_shopify_graphql.

This package provides a Python interface for the Shopify GraphQL Admin API.

Architecture:
    This library follows Clean Architecture principles:
    - **Domain**: Pure exceptions and business rules
    - **Application**: Use cases and ports (Protocol interfaces)
    - **Adapters**: Shopify SDK implementations
    - **Composition**: Wiring adapters to ports

Core API:
    - :func:`login`: Authenticate with Shopify using client credentials grant.
    - :func:`logout`: Terminate an active Shopify session.
    - :func:`get_product_by_id`: Retrieve full product information.
    - :func:`create_product`: Create a new product.
    - :func:`duplicate_product`: Duplicate an existing product.
    - :func:`delete_product`: Delete a product permanently.
    - :func:`update_product`: Update product fields (partial update).
    - :func:`update_variant`: Update variant fields (partial update).
    - :func:`update_variants_bulk`: Bulk update multiple variants.
    - :func:`set_inventory`: Set absolute inventory quantity.
    - :func:`adjust_inventory`: Adjust inventory by delta.
    - :func:`delete_metafield`: Delete a single metafield.
    - :func:`delete_metafields`: Delete multiple metafields.
    - :func:`tokencache_clear`: Clear cached OAuth tokens.
    - :func:`skucache_clear`: Clear cached SKU-to-GID mappings.
    - :func:`cache_clear_all`: Clear all caches (tokens and SKU mappings).

Models:
    - :class:`ShopifyCredentials`: Credentials for authentication.
    - :class:`ShopifySession`: Active session wrapper.
    - :class:`Product`: Full product data.
    - :class:`ProductVariant`: Product variant data.
    - :class:`ProductImage`: Product image data.
    - :class:`ProductOption`: Product option definition.
    - :class:`Money`: Monetary value with currency.
    - :class:`PriceRange`: Min/max price range.
    - :class:`SEO`: Search engine optimization data.
    - :class:`Metafield`: Custom metadata attached to resources.

Product Creation Model:
    - :class:`ProductCreate`: Input model for creating a new product.

Product Lifecycle Results:
    - :class:`DuplicateProductResult`: Result of duplicating a product.
    - :class:`DeleteProductResult`: Result of deleting a product.

Partial Update Models:
    - :data:`UNSET`: Sentinel indicating field should not be updated.
    - :class:`ProductUpdate`: Partial update for product fields.
    - :class:`VariantUpdate`: Partial update for variant fields.
    - :class:`VariantUpdateRequest`: Update request with flexible identifier.
    - :class:`BulkUpdateResult`: Result of bulk update operations.
    - :class:`InventoryLevel`: Inventory level at a location.

Metafield Deletion Models:
    - :class:`MetafieldIdentifier`: Identifies a metafield for deletion.
    - :class:`MetafieldDeleteResult`: Result of metafield deletion.
    - :class:`MetafieldDeleteFailure`: A failed metafield deletion.

Exceptions:
    - :class:`ShopifyError`: Base exception for all Shopify operations.
    - :class:`AuthenticationError`: Authentication failed.
    - :class:`ProductNotFoundError`: Product not found.
    - :class:`VariantNotFoundError`: Variant not found.
    - :class:`AmbiguousSKUError`: SKU matches multiple variants.
    - :class:`SessionNotActiveError`: Session not active.
    - :class:`GraphQLError`: GraphQL query errors.

Ports (for dependency injection):
    - :class:`TokenProviderPort`: OAuth token provider interface.
    - :class:`GraphQLClientPort`: GraphQL client interface.
    - :class:`SessionManagerPort`: Session manager interface.
    - :class:`CachePort`: Key-value cache interface.
    - :class:`SKUResolverPort`: SKU to GID resolver interface.
    - :class:`LocationResolverPort`: Location resolver interface.

Adapters:
    - :class:`JsonFileCacheAdapter`: JSON file cache with filelock.
    - :class:`MySQLCacheAdapter`: MySQL-based cache.
    - :class:`CachedSKUResolver`: Cached SKU resolver implementation.
    - :class:`LocationResolver`: Location resolver with fallback.

Utilities:
    - :func:`get_config`: Load layered configuration.
    - :func:`print_info`: Display package metadata.
    - :func:`create_adapters`: Create adapter bundle for DI.
"""

from __future__ import annotations

# Package metadata
from .__init__conf__ import print_info

# Adapters
from .adapters import (
    DEFAULT_GRAPHQL_TIMEOUT_SECONDS,
    PYMYSQL_AVAILABLE,
    CachedSKUResolver,
    CachedTokenProvider,
    JsonFileCacheAdapter,
    LocationResolver,
    MySQLCacheAdapter,
)

# Application ports (for dependency injection)
from .application.ports import (
    CachePort,
    GraphQLClientPort,
    LocationResolverPort,
    SessionManagerPort,
    SKUResolverPort,
    TokenProviderPort,
)

# Composition root
from .composition import (
    AdapterBundle,
    create_adapters,
    create_cached_token_provider,
    get_default_adapters,
)

# Configuration
from .config import get_config

# Domain exceptions
from .exceptions import (
    AmbiguousSKUError,
    AuthenticationError,
    GraphQLError,
    GraphQLErrorEntry,
    GraphQLErrorLocation,
    GraphQLTimeoutError,
    ImageNotFoundError,
    ImageUploadError,
    ProductNotFoundError,
    SessionNotActiveError,
    ShopifyError,
    VariantNotFoundError,
)

# Data models
from .models import (
    SEO,
    UNSET,
    BulkUpdateResult,
    DeleteProductResult,
    DuplicateProductResult,
    ImageCreateFailure,
    ImageCreateResult,
    ImageCreateSuccess,
    ImageDeleteResult,
    ImageReorderResult,
    ImageSource,
    ImageUpdate,
    InventoryLevel,
    InventoryPolicy,
    InventoryQuantityName,
    InventoryReason,
    MediaStatus,
    Metafield,
    MetafieldDeleteFailure,
    MetafieldDeleteResult,
    MetafieldIdentifier,
    MetafieldInput,
    MetafieldType,
    Money,
    PageInfo,
    PriceRange,
    Product,
    ProductConnection,
    ProductCreate,
    ProductImage,
    ProductOption,
    ProductStatus,
    ProductUpdate,
    ProductVariant,
    SelectedOption,
    ShopifyCredentials,
    ShopifySessionInfo,
    StagedUploadTarget,
    UnsetType,
    UpdateFailure,
    UpdateSuccess,
    VariantUpdate,
    VariantUpdateRequest,
    WeightUnit,
)

# Shopify client API
from .shopify_client import (
    CacheCheckResult,
    CacheMismatch,
    ShopifySession,
    adjust_inventory,
    cache_clear_all,
    create_image,
    create_images,
    create_product,
    delete_image,
    delete_images,
    delete_metafield,
    delete_metafields,
    delete_product,
    duplicate_product,
    get_product_by_id,
    get_product_by_sku,
    get_product_id_from_sku,
    iter_products,
    list_products,
    list_products_paginated,
    login,
    logout,
    reorder_images,
    set_inventory,
    skucache_check,
    skucache_clear,
    skucache_rebuild,
    tokencache_clear,
    update_image,
    update_product,
    update_variant,
    update_variants_bulk,
)

__all__ = [
    # Shopify API - Session
    "login",
    "logout",
    "ShopifySession",
    # Shopify API - Create
    "create_product",
    # Shopify API - Read
    "get_product_by_id",
    "get_product_by_sku",
    "get_product_id_from_sku",
    "iter_products",
    "list_products",
    "list_products_paginated",
    # Shopify API - Duplicate
    "duplicate_product",
    # Shopify API - Update
    "update_product",
    "update_variant",
    "update_variants_bulk",
    "set_inventory",
    "adjust_inventory",
    # Shopify API - Delete
    "delete_image",
    "delete_images",
    "delete_metafield",
    "delete_metafields",
    "delete_product",
    # Shopify API - Images
    "create_image",
    "create_images",
    "reorder_images",
    "update_image",
    # Shopify API - Cache
    "CacheCheckResult",
    "CacheMismatch",
    "cache_clear_all",
    "skucache_check",
    "skucache_clear",
    "skucache_rebuild",
    "tokencache_clear",
    # Models - Read
    "ShopifyCredentials",
    "ShopifySessionInfo",
    "Product",
    "ProductVariant",
    "ProductImage",
    "ProductOption",
    "Money",
    "PriceRange",
    "SEO",
    "Metafield",
    "MetafieldType",
    "MediaStatus",
    "ProductStatus",
    "InventoryPolicy",
    "InventoryQuantityName",
    "InventoryReason",
    "SelectedOption",
    "WeightUnit",
    "InventoryLevel",
    # Models - Pagination
    "PageInfo",
    "ProductConnection",
    # Models - Create
    "ProductCreate",
    # Models - Partial Update
    "UNSET",
    "UnsetType",
    "ProductUpdate",
    "VariantUpdate",
    "MetafieldInput",
    "VariantUpdateRequest",
    "BulkUpdateResult",
    "UpdateSuccess",
    "UpdateFailure",
    # Models - Metafield Deletion
    "MetafieldIdentifier",
    "MetafieldDeleteResult",
    "MetafieldDeleteFailure",
    # Models - Product Lifecycle
    "DeleteProductResult",
    "DuplicateProductResult",
    # Models - Image Management
    "ImageCreateFailure",
    "ImageCreateResult",
    "ImageCreateSuccess",
    "ImageDeleteResult",
    "ImageReorderResult",
    "ImageSource",
    "ImageUpdate",
    "StagedUploadTarget",
    # Exceptions
    "ShopifyError",
    "AuthenticationError",
    "ProductNotFoundError",
    "VariantNotFoundError",
    "ImageNotFoundError",
    "ImageUploadError",
    "AmbiguousSKUError",
    "SessionNotActiveError",
    "GraphQLError",
    "GraphQLErrorEntry",
    "GraphQLErrorLocation",
    "GraphQLTimeoutError",
    # Configuration
    "get_config",
    "print_info",
    # Application ports (for dependency injection)
    "TokenProviderPort",
    "GraphQLClientPort",
    "SessionManagerPort",
    "CachePort",
    "SKUResolverPort",
    "LocationResolverPort",
    # Adapters
    "JsonFileCacheAdapter",
    "MySQLCacheAdapter",
    "CachedSKUResolver",
    "CachedTokenProvider",
    "LocationResolver",
    "PYMYSQL_AVAILABLE",
    "DEFAULT_GRAPHQL_TIMEOUT_SECONDS",
    # Composition
    "AdapterBundle",
    "create_adapters",
    "create_cached_token_provider",
    "get_default_adapters",
]
