"""GraphQL query definitions for Shopify API.

This module contains GraphQL query builders for the Shopify client.
Query limits are configurable via the [graphql] section in config.

The limits control nested connection sizes to stay under Shopify's
query cost limit of 1000 points per request.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from lib_layered_config import Config


@dataclass(frozen=True)
class GraphQLLimits:
    """Configurable limits for GraphQL product query nested connections.

    These limits control how many items are fetched in each nested connection.
    Lower values reduce query cost but may truncate data.

    All attributes are prefixed with ``product_`` to allow future resource-specific
    limits (e.g., ``order_*``, ``customer_*``).

    Attributes:
        product_max_images: Maximum images per product (default: 20).
        product_max_media: Maximum media items per product (default: 20).
        product_max_options: Maximum product options (default: 10).
        product_max_metafields: Maximum metafields per product (default: 10).
        product_max_variants: Maximum variants per product (default: 20).
        product_max_variant_metafields: Maximum metafields per variant (default: 5).
        product_default_page_size: Default pagination size for manual pagination (default: 50).
        product_iter_page_size: Page size for iter_products/list_products (default: 250).
        product_warn_on_truncation: Log warnings when limits may truncate data (default: True).
    """

    product_max_images: int = 20
    product_max_media: int = 20
    product_max_options: int = 10
    product_max_metafields: int = 10
    product_max_variants: int = 20
    product_max_variant_metafields: int = 5
    product_default_page_size: int = 50
    product_iter_page_size: int = 250
    product_warn_on_truncation: bool = True

    @classmethod
    def from_config(cls, config: Config) -> GraphQLLimits:
        """Create limits from configuration.

        Args:
            config: Configuration object with [graphql] section.

        Returns:
            GraphQLLimits with values from config or defaults.
        """
        graphql_raw: Any = config.get("graphql", default={})
        graphql: dict[str, Any] = cast(dict[str, Any], graphql_raw) if isinstance(graphql_raw, dict) else {}

        def get_int(key: str, default: int) -> int:
            val: Any = graphql.get(key)
            if val is None:
                return default
            if isinstance(val, int):
                return val
            if isinstance(val, str):
                return int(val)
            return default

        def get_bool(key: str, default: bool) -> bool:
            val: Any = graphql.get(key)
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            # Handle string "true"/"false" from env vars
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes")
            return bool(val)

        return cls(
            product_max_images=get_int("product_max_images", cls.product_max_images),
            product_max_media=get_int("product_max_media", cls.product_max_media),
            product_max_options=get_int("product_max_options", cls.product_max_options),
            product_max_metafields=get_int("product_max_metafields", cls.product_max_metafields),
            product_max_variants=get_int("product_max_variants", cls.product_max_variants),
            product_max_variant_metafields=get_int("product_max_variant_metafields", cls.product_max_variant_metafields),
            product_default_page_size=get_int("product_default_page_size", cls.product_default_page_size),
            product_iter_page_size=get_int("product_iter_page_size", cls.product_iter_page_size),
            product_warn_on_truncation=get_bool("product_warn_on_truncation", cls.product_warn_on_truncation),
        )


# Default limits (used when no config is provided)
DEFAULT_LIMITS = GraphQLLimits()


@lru_cache(maxsize=1)
def get_limits_from_config() -> GraphQLLimits:
    """Get GraphQL limits from application config (cached).

    Returns:
        GraphQLLimits from config or defaults if config unavailable.
    """
    try:
        from ..config import get_config

        config = get_config()
        return GraphQLLimits.from_config(config)
    except Exception:
        return DEFAULT_LIMITS


def build_product_query(limits: GraphQLLimits | None = None) -> str:
    """Build GraphQL query for fetching full product details.

    Args:
        limits: Query limits. If None, uses config or defaults.

    Returns:
        GraphQL query string with configured limits.
    """
    if limits is None:
        limits = get_limits_from_config()

    return f"""
query GetProduct($id: ID!) {{
  product(id: $id) {{
    id
    legacyResourceId
    title
    description
    descriptionHtml
    handle
    vendor
    productType
    status
    tags
    createdAt
    updatedAt
    publishedAt
    totalInventory
    tracksInventory
    hasOnlyDefaultVariant
    hasOutOfStockVariants
    isGiftCard
    onlineStoreUrl
    onlineStorePreviewUrl
    templateSuffix
    featuredImage {{
      id
      url
      altText
      width
      height
    }}
    images(first: {limits.product_max_images}) {{
      pageInfo {{
        hasNextPage
      }}
      nodes {{
        id
        url
        altText
        width
        height
      }}
    }}
    media(first: {limits.product_max_media}) {{
      pageInfo {{
        hasNextPage
      }}
      nodes {{
        id
        alt
        mediaContentType
        status
        ... on MediaImage {{
          image {{
            url
            width
            height
          }}
        }}
      }}
    }}
    options(first: {limits.product_max_options}) {{
      id
      name
      position
      values
    }}
    seo {{
      title
      description
    }}
    priceRangeV2 {{
      minVariantPrice {{
        amount
        currencyCode
      }}
      maxVariantPrice {{
        amount
        currencyCode
      }}
    }}
    metafields(first: {limits.product_max_metafields}) {{
      pageInfo {{
        hasNextPage
      }}
      nodes {{
        id
        namespace
        key
        value
        type
        createdAt
        updatedAt
      }}
    }}
    variants(first: {limits.product_max_variants}) {{
      pageInfo {{
        hasNextPage
      }}
      nodes {{
        id
        title
        displayName
        sku
        barcode
        price
        compareAtPrice
        inventoryQuantity
        inventoryPolicy
        availableForSale
        taxable
        position
        createdAt
        updatedAt
        image {{
          id
          url
          altText
          width
          height
        }}
        selectedOptions {{
          name
          value
        }}
        metafields(first: {limits.product_max_variant_metafields}) {{
          pageInfo {{
            hasNextPage
          }}
          nodes {{
            id
            namespace
            key
            value
            type
            createdAt
            updatedAt
          }}
        }}
      }}
    }}
  }}
}}
"""


def build_products_list_query(limits: GraphQLLimits | None = None) -> str:
    """Build GraphQL query for listing products with pagination.

    Args:
        limits: Query limits. If None, uses config or defaults.

    Returns:
        GraphQL query string with configured limits.
    """
    if limits is None:
        limits = get_limits_from_config()

    return f"""
query ListProducts($first: Int!, $after: String, $query: String) {{
  products(first: $first, after: $after, query: $query) {{
    pageInfo {{
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }}
    nodes {{
      id
      legacyResourceId
      title
      description
      descriptionHtml
      handle
      vendor
      productType
      status
      tags
      createdAt
      updatedAt
      publishedAt
      totalInventory
      tracksInventory
      hasOnlyDefaultVariant
      hasOutOfStockVariants
      isGiftCard
      onlineStoreUrl
      onlineStorePreviewUrl
      templateSuffix
      featuredImage {{
        id
        url
        altText
        width
        height
      }}
      images(first: {limits.product_max_images}) {{
        pageInfo {{
          hasNextPage
        }}
        nodes {{
          id
          url
          altText
          width
          height
        }}
      }}
      options(first: {limits.product_max_options}) {{
        id
        name
        position
        values
      }}
      seo {{
        title
        description
      }}
      priceRangeV2 {{
        minVariantPrice {{
          amount
          currencyCode
        }}
        maxVariantPrice {{
          amount
          currencyCode
        }}
      }}
      metafields(first: {limits.product_max_metafields}) {{
        pageInfo {{
          hasNextPage
        }}
        nodes {{
          id
          namespace
          key
          value
          type
          createdAt
          updatedAt
        }}
      }}
      variants(first: {limits.product_max_variants}) {{
        pageInfo {{
          hasNextPage
        }}
        nodes {{
          id
          title
          displayName
          sku
          barcode
          price
          compareAtPrice
          inventoryQuantity
          inventoryPolicy
          availableForSale
          taxable
          position
          createdAt
          updatedAt
          image {{
            id
            url
            altText
            width
            height
          }}
          selectedOptions {{
            name
            value
          }}
          metafields(first: {limits.product_max_variant_metafields}) {{
            pageInfo {{
              hasNextPage
            }}
            nodes {{
              id
              namespace
              key
              value
              type
              createdAt
              updatedAt
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""


# Module-level query strings built with config limits on first import
# Use build_product_query() / build_products_list_query() for dynamic rebuilds
PRODUCT_QUERY: str = build_product_query()
PRODUCTS_LIST_QUERY: str = build_products_list_query()


__all__ = [
    "GraphQLLimits",
    "DEFAULT_LIMITS",
    "get_limits_from_config",
    "build_product_query",
    "build_products_list_query",
    "PRODUCT_QUERY",
    "PRODUCTS_LIST_QUERY",
]
