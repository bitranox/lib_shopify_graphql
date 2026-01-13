"""Pydantic models for Shopify GraphQL API data structures.

This package contains all data models used for Shopify API interactions:
    - :class:`ShopifyCredentials`: Credentials for client credentials grant auth.
    - :class:`Product`: Full product data from Shopify.
    - :class:`ProductVariant`: Product variant data.
    - :class:`ProductImage`: Product image data.
    - :class:`ProductOption`: Product option (size, color, etc.).
    - :class:`Metafield`: Custom metadata attached to resources.
    - :class:`Money`: Monetary value with currency.
    - :class:`PriceRange`: Min/max price range.
    - :class:`SEO`: Search engine optimization data.
    - :class:`ShopifySessionInfo`: Read-only session information.

Note:
    All models use ``frozen=True`` for immutability. Validation occurs at
    the boundary when data enters the system.
"""

from __future__ import annotations

# Core entity models
from ._entities import (
    SEO,
    Metafield,
    Money,
    PriceRange,
    Product,
    ProductImage,
    ProductMedia,
    ProductOption,
    ProductVariant,
    SelectedOption,
    ShopifyCredentials,
    ShopifySessionInfo,
)

# Enums
from ._enums import (
    CurrencyCode,
    InventoryPolicy,
    InventoryQuantityName,
    InventoryReason,
    MediaContentType,
    MediaStatus,
    MetafieldType,
    ProductStatus,
    WeightUnit,
)

# Image management models
from ._images import (
    ImageCreateFailure,
    ImageCreateResult,
    ImageCreateSuccess,
    ImageDeleteResult,
    ImageReorderResult,
    ImageSource,
    ImageUpdate,
    StagedUploadTarget,
)

# Internal utilities (Updatable is used internally but not exported in __all__)
from ._internal import UNSET, UnsetType  # noqa: F401
from ._internal import Updatable as Updatable

# Mutation/update models
from ._mutations import (
    MetafieldInput,
    ProductCreate,
    ProductUpdate,
    VariantUpdate,
)

# Operation request/result models
from ._operations import (
    BulkUpdateResult,
    DeleteProductResult,
    DuplicateProductResult,
    InventoryLevel,
    MetafieldDeleteFailure,
    MetafieldDeleteResult,
    MetafieldIdentifier,
    PageInfo,
    ProductConnection,
    ProductUpdateRequest,
    UpdateFailure,
    UpdateSuccess,
    VariantUpdateRequest,
)

__all__ = [
    # Sentinel for partial updates
    "UNSET",
    "UnsetType",
    # Enums
    "CurrencyCode",
    "InventoryPolicy",
    "InventoryQuantityName",
    "InventoryReason",
    "MediaContentType",
    "MediaStatus",
    "MetafieldType",
    "ProductStatus",
    "WeightUnit",
    # Read models
    "InventoryLevel",
    "Metafield",
    "Money",
    "PriceRange",
    "Product",
    "ProductImage",
    "ProductMedia",
    "ProductOption",
    "ProductVariant",
    "SEO",
    "SelectedOption",
    "ShopifyCredentials",
    "ShopifySessionInfo",
    # Update input models
    "MetafieldInput",
    "ProductCreate",
    "ProductUpdate",
    "VariantUpdate",
    # Request/result models
    "BulkUpdateResult",
    "ProductUpdateRequest",
    "UpdateFailure",
    "UpdateSuccess",
    "VariantUpdateRequest",
    # Metafield deletion models
    "MetafieldDeleteFailure",
    "MetafieldDeleteResult",
    "MetafieldIdentifier",
    # Pagination models
    "PageInfo",
    "ProductConnection",
    # Product lifecycle models
    "DeleteProductResult",
    "DuplicateProductResult",
    # Image management models
    "ImageCreateFailure",
    "ImageCreateResult",
    "ImageCreateSuccess",
    "ImageDeleteResult",
    "ImageReorderResult",
    "ImageSource",
    "ImageUpdate",
    "StagedUploadTarget",
]
