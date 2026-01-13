"""Adapters layer - implementations of application ports.

This layer contains concrete implementations that interface with
external systems:
    - Shopify SDK adapter for API communication
    - GraphQL query and mutation definitions
    - Cache adapters (JSON file, MySQL)
    - SKU and location resolvers

Adapters implement the ports defined in the application layer
and are wired at the composition root.

Note:
    GraphQL queries, mutations, limits, and query builders are internal
    implementation details and not exported in the public API. Import them
    directly from their submodules if needed:

        from lib_shopify_graphql.adapters.queries import (
            GraphQLLimits, build_product_query, get_limits_from_config,
        )
        from lib_shopify_graphql.adapters.mutations import (
            PRODUCT_UPDATE_MUTATION, ...
        )
        from lib_shopify_graphql.adapters.parsers import (
            parse_product, ...
        )
"""

from __future__ import annotations

from .cache_json import JsonFileCacheAdapter
from .cache_mysql import PYMYSQL_AVAILABLE, MySQLCacheAdapter
from .constants import (
    DEFAULT_GRAPHQL_TIMEOUT_SECONDS,
    get_default_cache_dir,
    get_default_sku_cache_path,
    get_default_token_cache_path,
)
from .location_resolver import LocationResolver
from .shopify_sdk import (
    ShopifyGraphQLClient,
    ShopifySessionManager,
    ShopifyTokenProvider,
)
from .sku_resolver import CachedSKUResolver
from .token_cache import CachedTokenProvider

__all__ = [
    # Public constants
    "DEFAULT_GRAPHQL_TIMEOUT_SECONDS",
    "PYMYSQL_AVAILABLE",
    # Cache path helpers
    "get_default_cache_dir",
    "get_default_sku_cache_path",
    "get_default_token_cache_path",
    # Shopify SDK adapters
    "ShopifyGraphQLClient",
    "ShopifySessionManager",
    "ShopifyTokenProvider",
    # Cache adapters
    "JsonFileCacheAdapter",
    "MySQLCacheAdapter",
    # Token caching
    "CachedTokenProvider",
    # Resolvers
    "CachedSKUResolver",
    "LocationResolver",
]
