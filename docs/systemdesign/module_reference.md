# Module Reference: lib_shopify_graphql

## Status

Complete

## Scope

This document covers the complete architecture of `lib_shopify_graphql`, a Python library
for interacting with the Shopify GraphQL Admin API using Clean Architecture principles.

## Links & References

**Feature Requirements:** Shopify GraphQL API integration with Clean Architecture
**Task/Ticket:** N/A
**Pull Requests:** N/A
**Related Files:**

* src/lib_shopify_graphql/_compat.py
* src/lib_shopify_graphql/domain/__init__.py
* src/lib_shopify_graphql/application/__init__.py
* src/lib_shopify_graphql/application/ports.py
* src/lib_shopify_graphql/adapters/__init__.py
* src/lib_shopify_graphql/adapters/shopify_sdk.py
* src/lib_shopify_graphql/adapters/parsers.py
* src/lib_shopify_graphql/adapters/queries.py
* src/lib_shopify_graphql/adapters/mutations.py
* src/lib_shopify_graphql/adapters/constants.py
* src/lib_shopify_graphql/adapters/cache_json.py
* src/lib_shopify_graphql/adapters/cache_mysql.py
* src/lib_shopify_graphql/adapters/token_cache.py
* src/lib_shopify_graphql/adapters/sku_resolver.py
* src/lib_shopify_graphql/adapters/location_resolver.py
* src/lib_shopify_graphql/composition.py
* src/lib_shopify_graphql/shopify_client/__init__.py (package)
* src/lib_shopify_graphql/shopify_client/_common.py
* src/lib_shopify_graphql/shopify_client/_session.py
* src/lib_shopify_graphql/shopify_client/_products.py
* src/lib_shopify_graphql/shopify_client/_variants.py
* src/lib_shopify_graphql/shopify_client/_variants_bulk.py
* src/lib_shopify_graphql/shopify_client/_inventory.py
* src/lib_shopify_graphql/shopify_client/_images.py
* src/lib_shopify_graphql/shopify_client/_metafields.py
* src/lib_shopify_graphql/shopify_client/_cache.py
* src/lib_shopify_graphql/models/__init__.py (package)
* src/lib_shopify_graphql/models/_entities.py
* src/lib_shopify_graphql/models/_enums.py
* src/lib_shopify_graphql/models/_mutations.py
* src/lib_shopify_graphql/models/_operations.py
* src/lib_shopify_graphql/models/_images.py
* src/lib_shopify_graphql/models/_internal.py
* src/lib_shopify_graphql/exceptions.py
* src/lib_shopify_graphql/cli.py
* tests/test_shopify_client.py
* tests/test_cache.py
* tests/test_sku_resolver.py
* tests/test_token_cache.py
* tests/test_models.py
* tests/test_parsers.py
* tests/test_cli.py
* tests/test_integration.py

---

## Problem Statement

Interacting with the Shopify GraphQL Admin API requires proper session management,
authentication via OAuth 2.0 client credentials grant, and structured parsing of
GraphQL responses. The solution needed to be:

1. **Testable** - Allow mocking external dependencies without monkey-patching
2. **Maintainable** - Clear separation of concerns with layered architecture
3. **Extensible** - Easy to add new API operations
4. **Type-safe** - Full Pydantic validation at boundaries

## Solution Overview

The library implements **Clean Architecture** with three distinct layers:

```
┌─────────────────────────────────────────────────────────────┐
│  Composition Root (composition.py)                          │
│  - Wires adapters to ports                                  │
│  - Creates AdapterBundle for DI                             │
│  - Factory functions for cached providers                   │
├─────────────────────────────────────────────────────────────┤
│  Adapters Layer (adapters/)                                 │
│  - ShopifyTokenProvider, ShopifyGraphQLClient               │
│  - ShopifySessionManager                                    │
│  - CachedTokenProvider, CachedSKUResolver, LocationResolver │
│  - JsonFileCacheAdapter, MySQLCacheAdapter                  │
│  - parsers.py, queries.py, mutations.py                     │
│  - ONLY layer that imports `shopify` SDK                    │
├─────────────────────────────────────────────────────────────┤
│  Application Layer (application/)                           │
│  - ports.py: Protocol interfaces                            │
│  - TokenProviderPort, GraphQLClientPort, SessionManagerPort │
│  - CachePort, SKUResolverPort, LocationResolverPort         │
│  - No adapter or framework dependencies                     │
├─────────────────────────────────────────────────────────────┤
│  Domain Layer (domain/)                                     │
│  - Pure Python only (no Pydantic, no external libs)         │
│  - Core business rules and entities                         │
│  - Currently minimal (exceptions in outer layer)            │
└─────────────────────────────────────────────────────────────┘
```

**Key patterns:**
- Dependency Inversion Principle (DIP) via Protocol interfaces
- Composition Root for wiring adapters
- Dependency Injection via optional function parameters
- Cache-first strategy with fallback to Shopify API

---

## Architecture Integration

**Layer Dependencies (point inward only):**
- Composition Root -> Adapters -> Application -> Domain
- Domain has NO dependencies on outer layers
- Application ports define interfaces, adapters implement them

**Data Flow:**
1. User calls `login(credentials)` from `shopify_client.py`
2. Default adapters are used unless custom ones are injected
3. `TokenProviderPort.obtain_token()` gets OAuth access token
4. `SessionManagerPort.create_session()` creates Shopify session
5. Session is wrapped in `ShopifySession` dataclass
6. User calls `get_product_by_id(session, id)`
7. `GraphQLClientPort.execute()` runs GraphQL query
8. Response is parsed via `adapters/parsers.py`
9. `Product` Pydantic model is returned

**System Dependencies:**
* `ShopifyAPI` (>=12.7.0) - Official Shopify Python SDK
* `pydantic` - Data validation at boundaries
* `orjson` (>=3.10.0) - High-performance JSON serialization (3-10x faster than stdlib)
* `rich_click` - CLI with rich output
* `lib_cli_exit_tools` - Exit code helpers
* `lib_log_rich` - Structured logging
* `lib_layered_config` - Configuration management

---

## Core Components

### Compatibility Layer (_compat.py)

Provides backports for features not available in all supported Python versions.

**_compat.StrEnum**
* **Purpose:** Backport of StrEnum for Python 3.10 (added in 3.11)
* **Behavior:** On Python 3.11+, imports from stdlib; on 3.10, provides equivalent class
* **Usage:** All modules import StrEnum from `_compat`, not stdlib or define their own
* **Location:** src/lib_shopify_graphql/_compat.py

---

### Domain Layer (domain/)

Currently minimal. Pure Python entities and business rules will be added here as needed.

**domain/__init__.py**
* **Purpose:** Export domain entities (currently empty)
* **Constraints:** No imports from Pydantic, Shopify SDK, or outer layers
* **Location:** src/lib_shopify_graphql/domain/__init__.py

---

### Application Layer (application/)

Defines port interfaces (Protocols) that adapters must implement.

**application/ports.TokenProviderPort**
* **Purpose:** Abstract interface for obtaining OAuth access tokens
* **Method:** `obtain_token(shop_url, client_id, client_secret) -> tuple[str, datetime]`
* **Location:** src/lib_shopify_graphql/application/ports.py

**application/ports.GraphQLClientPort**
* **Purpose:** Abstract interface for executing GraphQL queries
* **Method:** `execute(query, variables) -> dict[str, Any]`
* **Location:** src/lib_shopify_graphql/application/ports.py

**application/ports.SessionManagerPort**
* **Purpose:** Abstract interface for session lifecycle management
* **Methods:**
  - `create_session(shop_url, api_version, access_token) -> Any`
  - `activate_session(session) -> None`
  - `clear_session() -> None`
* **Location:** src/lib_shopify_graphql/application/ports.py

**application/ports.CachePort**
* **Purpose:** Abstract interface for key-value cache operations
* **Methods:**
  - `get(key) -> str | None`
  - `set(key, value, ttl=None) -> None`
  - `delete(key) -> None`
  - `clear() -> None`
* **Location:** src/lib_shopify_graphql/application/ports.py

**application/ports.SKUResolverPort**
* **Purpose:** Abstract interface for resolving SKU to variant GID
* **Methods:**
  - `resolve(sku, shop_url) -> str | None`
  - `invalidate(sku, shop_url) -> None`
* **Location:** src/lib_shopify_graphql/application/ports.py

**application/ports.LocationResolverPort**
* **Purpose:** Abstract interface for resolving inventory location
* **Method:** `resolve(explicit_location=None) -> str`
* **Location:** src/lib_shopify_graphql/application/ports.py

---

### Adapters Layer (adapters/)

Concrete implementations that interface with external systems.

**adapters/shopify_sdk.ShopifyTokenProvider**
* **Purpose:** Obtain access tokens via OAuth 2.0 client credentials grant
* **Implements:** TokenProviderPort
* **Input:** shop_url, client_id, client_secret
* **Output:** Tuple of (access_token, expiration_datetime)
* **Location:** src/lib_shopify_graphql/adapters/shopify_sdk.py

**adapters/shopify_sdk.ShopifyGraphQLClient**
* **Purpose:** Execute GraphQL queries using Shopify SDK
* **Implements:** GraphQLClientPort
* **Input:** GraphQL query string, optional variables dict
* **Output:** Parsed JSON response as dict
* **Location:** src/lib_shopify_graphql/adapters/shopify_sdk.py

**adapters/shopify_sdk.ShopifySessionManager**
* **Purpose:** Manage Shopify API session state
* **Implements:** SessionManagerPort
* **Methods:** create_session, activate_session, clear_session
* **Location:** src/lib_shopify_graphql/adapters/shopify_sdk.py

**adapters/parsers.parse_product**
* **Purpose:** Parse GraphQL product response into Product model
* **Input:** Raw dict from GraphQL response, optional operation name for truncation warnings
* **Output:** Product Pydantic model
* **Side Effect:** Calls `_check_truncation()` to log warnings when limits may truncate data
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/parsers._check_truncation** (internal)
* **Purpose:** Check if nested collections may be truncated and log actionable warnings
* **Input:** product_data dict, product_id, operation name
* **Behavior:** Compares fetched counts against configured limits; logs warnings with:
  - Operation context (which function triggered the warning)
  - Product identification (title and ID)
  - Actionable recommendations (which config value to change)
  - Cost impact guidance (safe vs. cautious increases)
* **Checks:** images, media, options, product metafields, variants, variant metafields
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/parsers.parse_graphql_errors**
* **Purpose:** Parse GraphQL error response into structured errors
* **Input:** Raw errors list from GraphQL response
* **Output:** List of GraphQLErrorEntry models
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/queries.GraphQLLimits**
* **Purpose:** Configurable limits for GraphQL query nested connections
* **Type:** Dataclass (frozen=True)
* **Attributes:** (all prefixed with `product_` for future extensibility)
  - `product_max_images` (int, default: 20) - Max images per product
  - `product_max_media` (int, default: 20) - Max media items per product
  - `product_max_options` (int, default: 10) - Max product options
  - `product_max_metafields` (int, default: 10) - Max metafields per product
  - `product_max_variants` (int, default: 20) - Max variants per product
  - `product_max_variant_metafields` (int, default: 5) - Max metafields per variant
  - `product_default_page_size` (int, default: 50) - Default page size for manual pagination
  - `product_iter_page_size` (int, default: 250) - Page size for auto-pagination
  - `product_warn_on_truncation` (bool, default: True) - Log warnings when limits may truncate data
* **Class Method:** `from_config(config)` - Create limits from configuration
* **Location:** src/lib_shopify_graphql/adapters/queries.py

**adapters/queries.build_product_query**
* **Purpose:** Build GraphQL query for fetching full product details with configurable limits
* **Input:** Optional GraphQLLimits (uses config defaults if None)
* **Output:** GraphQL query string
* **Location:** src/lib_shopify_graphql/adapters/queries.py

**adapters/queries.build_products_list_query**
* **Purpose:** Build GraphQL query for listing products with configurable limits
* **Input:** Optional GraphQLLimits (uses config defaults if None)
* **Output:** GraphQL query string
* **Location:** src/lib_shopify_graphql/adapters/queries.py

**adapters/queries.get_limits_from_config**
* **Purpose:** Get GraphQL limits from application config (cached)
* **Output:** GraphQLLimits from config or defaults
* **Location:** src/lib_shopify_graphql/adapters/queries.py

**adapters/queries.PRODUCT_QUERY**
* **Purpose:** GraphQL query string for fetching full product data (built with config limits)
* **Type:** Module-level constant string
* **Location:** src/lib_shopify_graphql/adapters/queries.py

**adapters/queries.PRODUCTS_LIST_QUERY**
* **Purpose:** GraphQL query string for listing products with pagination (built with config limits)
* **Type:** Module-level constant string
* **Location:** src/lib_shopify_graphql/adapters/queries.py

**adapters/parsers.parse_page_info**
* **Purpose:** Parse GraphQL pageInfo into PageInfo model
* **Input:** Raw dict from GraphQL response pageInfo field
* **Output:** PageInfo Pydantic model
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/parsers.parse_product_connection**
* **Purpose:** Parse GraphQL products connection into ProductConnection model
* **Input:** Raw dict from GraphQL products response
* **Output:** ProductConnection Pydantic model with list of products and page info
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/parsers.parse_variant_from_mutation**
* **Purpose:** Parse variant data from mutation response into ProductVariant model
* **Input:** VariantMutationResult typed model from GraphQL mutation response
* **Output:** ProductVariant Pydantic model
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/parsers.parse_staged_upload_target**
* **Purpose:** Parse staged upload response into typed StagedUploadTarget model
* **Input:** Raw dict from GraphQL stagedUploadsCreate response
* **Output:** StagedUploadTarget Pydantic model with typed parameters list
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/parsers.get_truncation_info**
* **Purpose:** Analyze a product for fields that may be truncated by GraphQL limits
* **Input:** Product model
* **Output:** TruncationInfo typed model with truncation analysis
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/parsers.build_product_input**
* **Purpose:** Build ProductInput dict for productUpdate mutation
* **Input:** product_id, ProductUpdate model
* **Output:** Dict suitable for GraphQL ProductInput type
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/parsers.build_variant_input**
* **Purpose:** Build VariantInput dict for variant mutations
* **Input:** variant_id, VariantUpdate model
* **Output:** Dict suitable for GraphQL ProductVariantInput type
* **Location:** src/lib_shopify_graphql/adapters/parsers.py

**adapters/mutations (constants)**
* **Purpose:** GraphQL mutation strings for write operations
* **Constants:**
  - `PRODUCT_UPDATE_MUTATION` - Update product fields
  - `PRODUCT_VARIANTS_BULK_UPDATE_MUTATION` - Bulk update variants
  - `INVENTORY_SET_QUANTITIES_MUTATION` - Set absolute inventory
  - `INVENTORY_ADJUST_QUANTITIES_MUTATION` - Adjust inventory by delta
  - `METAFIELDS_DELETE_MUTATION` - Delete metafields
  - `VARIANT_INVENTORY_ITEM_QUERY` - Get variant inventory item ID
* **Location:** src/lib_shopify_graphql/adapters/mutations.py

**adapters/cache_json.JsonFileCacheAdapter**
* **Purpose:** File-based cache with filelock for concurrent access
* **Implements:** CachePort
* **Features:** Safe for network shares, TTL support, atomic writes
* **Location:** src/lib_shopify_graphql/adapters/cache_json.py

**adapters/cache_mysql.MySQLCacheAdapter**
* **Purpose:** MySQL-based cache for distributed environments
* **Implements:** CachePort
* **Features:** Auto-creates database/tables, TTL support, cleanup_expired()
* **Class Method:** `from_url(connection_string, ...)` - Create from URL
* **Location:** src/lib_shopify_graphql/adapters/cache_mysql.py

**adapters/token_cache.CachedTokenProvider**
* **Purpose:** Token provider wrapper that caches OAuth tokens
* **Implements:** TokenProviderPort
* **Input:** CachePort, delegate TokenProviderPort, refresh_margin
* **Behavior:** Cache-first, refreshes before expiration
* **Location:** src/lib_shopify_graphql/adapters/token_cache.py

**adapters/sku_resolver.CachedSKUResolver**
* **Purpose:** SKU resolver with cache-first, Shopify-fallback strategy
* **Implements:** SKUResolverPort
* **Input:** CachePort, GraphQLClientPort, cache_ttl
* **Behavior:** Resolves SKU to variant GID, caches results
* **Location:** src/lib_shopify_graphql/adapters/sku_resolver.py

**adapters/location_resolver.LocationResolver**
* **Purpose:** Location resolver with fallback chain
* **Implements:** LocationResolverPort
* **Fallback:** explicit_location -> config default -> primary location (API call)
* **Location:** src/lib_shopify_graphql/adapters/location_resolver.py

**adapters/constants**
* **Purpose:** Default configuration values
* **Constants:**
  - `DEFAULT_GRAPHQL_TIMEOUT_SECONDS` (30.0) - GraphQL request timeout
  - `DEFAULT_LOCK_TIMEOUT_SECONDS` (10.0) - Filelock timeout for JSON cache
  - `DEFAULT_CACHE_RETRY_COUNT` (3) - Cache lock acquisition retries
  - `DEFAULT_TOKEN_EXPIRES_IN_SECONDS` (86400) - 24 hours
  - `DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS` (300) - 5 minutes
  - `DEFAULT_SKU_CACHE_TTL_SECONDS` (2592000) - 30 days
  - `DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS` (10)
  - `DEFAULT_MYSQL_PORT` (3306)
  - `DEFAULT_TOKEN_CACHE_TABLE` ("token_cache")
  - `DEFAULT_SKU_CACHE_TABLE` ("sku_cache")
  - `DEFAULT_CURRENCY_CODE` ("USD")
  - `CACHE_APP_NAME` ("lib-shopify-graphql")
* **Functions:**
  - `get_default_cache_dir()` - OS-appropriate cache directory
  - `get_default_token_cache_path()` - Default token cache file path
  - `get_default_sku_cache_path()` - Default SKU cache file path
* **Location:** src/lib_shopify_graphql/adapters/constants.py

---

### Composition Root (composition.py)

Wires adapters to ports for dependency injection.

**composition.create_adapters**
* **Purpose:** Factory function to create adapter bundle
* **Input:** Optional custom adapters (None uses defaults)
* **Output:** AdapterBundle TypedDict with all adapters
* **Location:** src/lib_shopify_graphql/composition.py

**composition.get_default_adapters**
* **Purpose:** Get singleton default adapter bundle
* **Output:** AdapterBundle with Shopify SDK implementations
* **Location:** src/lib_shopify_graphql/composition.py

**composition.AdapterBundle**
* **Purpose:** TypedDict containing all adapter instances
* **Fields:** token_provider, session_manager, graphql_client
* **Location:** src/lib_shopify_graphql/composition.py

**composition.create_cached_token_provider**
* **Purpose:** Factory for creating CachedTokenProvider with cache
* **Input:** Optional cache, cache_path, delegate, refresh_margin
* **Output:** CachedTokenProvider wrapping either provided or default delegate
* **Location:** src/lib_shopify_graphql/composition.py

---

### Public API (shopify_client.py)

Core functions exposed to users.

**shopify_client.login**
* **Purpose:** Authenticate with Shopify via client credentials grant
* **Input:** ShopifyCredentials, optional adapter overrides
* **Output:** ShopifySession wrapper
* **Raises:** AuthenticationError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.logout**
* **Purpose:** Terminate an active Shopify session
* **Input:** ShopifySession
* **Output:** None (session marked inactive)
* **Raises:** SessionNotActiveError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.get_product_by_id**
* **Purpose:** Fetch full product data by ID
* **Input:** ShopifySession, product_id (numeric or GID)
* **Output:** Product Pydantic model
* **Raises:** SessionNotActiveError, ProductNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.list_products**
* **Purpose:** List products with cursor-based pagination
* **Input:** ShopifySession, first (int, 1-250), after (cursor), query (Shopify search syntax)
* **Output:** ProductConnection Pydantic model with products and page_info
* **Raises:** SessionNotActiveError, GraphQLError
* **Query Examples:** `status:active`, `updated_at:>2024-01-01`, `vendor:MyVendor`, `tag:sale`
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.get_product_id_from_sku**
* **Purpose:** Get all product GIDs for variants with a given SKU
* **Input:** ShopifySession, sku, optional sku_resolver
* **Output:** List of product GID strings (empty if not found)
* **Note:** Returns all matching products - SKUs may exist on multiple variants/products
* **Raises:** SessionNotActiveError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_products.py

**shopify_client.get_product_by_sku**
* **Purpose:** Get product by variant SKU
* **Input:** ShopifySession, sku, optional sku_resolver
* **Output:** Product Pydantic model
* **Raises:** SessionNotActiveError, ProductNotFoundError, AmbiguousSKUError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_products.py

**shopify_client.create_product**
* **Purpose:** Create a new product
* **Input:** ShopifySession, ProductCreate model
* **Output:** Created Product Pydantic model
* **Raises:** SessionNotActiveError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_products.py

**shopify_client.duplicate_product**
* **Purpose:** Duplicate an existing product
* **Input:** ShopifySession, product_id, new_title, include_images, new_status
* **Output:** DuplicateProductResult with new_product and original_product_id
* **Raises:** SessionNotActiveError, ProductNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_products.py

**shopify_client.delete_product**
* **Purpose:** Delete a product permanently
* **Input:** ShopifySession, product_id, optional sku_resolver (for cache invalidation)
* **Output:** DeleteProductResult with deleted_product_id and success flag
* **Raises:** SessionNotActiveError, ProductNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_products.py

**shopify_client.update_product**
* **Purpose:** Update product fields (partial update)
* **Input:** ShopifySession, product_id, ProductUpdate model
* **Output:** Updated Product Pydantic model
* **Raises:** SessionNotActiveError, ProductNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.update_variant**
* **Purpose:** Update a single variant by GID or SKU
* **Input:** ShopifySession, variant_id_or_sku, VariantUpdate, optional product_id, sku_resolver
* **Output:** Updated ProductVariant Pydantic model
* **Raises:** SessionNotActiveError, VariantNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.update_variants_bulk**
* **Purpose:** Update multiple variants in one API call
* **Input:** ShopifySession, product_id, list of VariantUpdateRequest, optional sku_resolver, allow_partial
* **Output:** BulkUpdateResult with succeeded and failed updates
* **Raises:** SessionNotActiveError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.set_inventory**
* **Purpose:** Set absolute inventory quantity for a variant
* **Input:** ShopifySession, variant_id_or_sku, quantity, optional location_id, reason
* **Output:** InventoryLevel Pydantic model
* **Raises:** SessionNotActiveError, VariantNotFoundError, GraphQLError
* **Location Resolution:** explicit -> config default -> primary location (API)
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.adjust_inventory**
* **Purpose:** Adjust inventory by delta (+/-)
* **Input:** ShopifySession, variant_id_or_sku, delta, optional location_id, reason
* **Output:** InventoryLevel Pydantic model
* **Raises:** SessionNotActiveError, VariantNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.delete_metafield**
* **Purpose:** Delete a single metafield by owner + namespace + key
* **Input:** ShopifySession, MetafieldIdentifier
* **Output:** MetafieldDeleteResult
* **Raises:** SessionNotActiveError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.delete_metafields**
* **Purpose:** Delete multiple metafields in one API call
* **Input:** ShopifySession, list of MetafieldIdentifier
* **Output:** List of MetafieldDeleteResult
* **Raises:** SessionNotActiveError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.tokencache_clear**
* **Purpose:** Clear all cached OAuth tokens
* **Input:** Optional CachePort (uses config default if None)
* **Output:** None
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.skucache_clear**
* **Purpose:** Clear all cached SKU-to-GID mappings
* **Input:** Optional CachePort (uses config default if None)
* **Output:** None
* **Location:** src/lib_shopify_graphql/shopify_client.py

**shopify_client.cache_clear_all**
* **Purpose:** Clear both token and SKU caches
* **Input:** Optional token_cache, sku_cache (uses config defaults if None)
* **Output:** None
* **Location:** src/lib_shopify_graphql/shopify_client/_cache.py

**shopify_client.skucache_rebuild**
* **Purpose:** Rebuild SKU cache by reading all products from Shopify
* **Input:** ShopifySession, sku_resolver, batch_size, query filter
* **Output:** Total number of variants cached
* **Location:** src/lib_shopify_graphql/shopify_client/_cache.py

**shopify_client.create_image**
* **Purpose:** Add an image to a product from URL or local file
* **Input:** ShopifySession, product_id, ImageSource
* **Output:** ImageCreateResult with image_id, url, status
* **Raises:** SessionNotActiveError, ProductNotFoundError, ImageUploadError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_images.py

**shopify_client.create_images**
* **Purpose:** Add multiple images to a product
* **Input:** ShopifySession, product_id, list of ImageSource
* **Output:** List of ImageCreateResult
* **Location:** src/lib_shopify_graphql/shopify_client/_images.py

**shopify_client.delete_image**
* **Purpose:** Delete an image from a product
* **Input:** ShopifySession, product_id, image_id
* **Output:** ImageDeleteResult with deleted_image_ids, deleted_media_ids
* **Raises:** SessionNotActiveError, ProductNotFoundError, ImageNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_images.py

**shopify_client.delete_images**
* **Purpose:** Delete multiple images from a product
* **Input:** ShopifySession, product_id, list of image_ids
* **Output:** ImageDeleteResult
* **Location:** src/lib_shopify_graphql/shopify_client/_images.py

**shopify_client.update_image**
* **Purpose:** Update image metadata (alt text)
* **Input:** ShopifySession, product_id, image_id, ImageUpdate
* **Output:** ImageCreateResult with updated metadata
* **Raises:** SessionNotActiveError, ProductNotFoundError, ImageNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_images.py

**shopify_client.reorder_images**
* **Purpose:** Reorder product images
* **Input:** ShopifySession, product_id, list of image_ids (in desired order)
* **Output:** ImageReorderResult with product_id and job_id
* **Raises:** SessionNotActiveError, ProductNotFoundError, GraphQLError
* **Location:** src/lib_shopify_graphql/shopify_client/_images.py

**shopify_client.ShopifySession**
* **Purpose:** Active session wrapper with API methods
* **Properties:** is_active, info
* **Methods:** is_token_expired, refresh_token, execute_graphql, get_credentials, clear_session
* **Location:** src/lib_shopify_graphql/shopify_client.py

---

### Data Models (models/)

Pydantic models for all Shopify data structures. Models are organized across submodules:
- `_entities.py` - Read models (Product, ProductVariant, etc.)
- `_enums.py` - Enumerations (ProductStatus, etc.)
- `_mutations.py` - Partial update models (ProductUpdate, VariantUpdate, etc.)
- `_operations.py` - Operation result models (BulkUpdateResult, etc.)
- `_images.py` - Image operation models (ImageSource, ImageCreateResult, etc.)
- `_internal.py` - Internal models (UNSET sentinel, etc.)

**Read Models:**

| Model | Purpose |
|-------|---------|
| ShopifyCredentials | OAuth credentials with validation |
| ShopifySessionInfo | Read-only session information |
| Product | Full product data with all relationships |
| ProductVariant | Variant with price, inventory, options |
| ProductImage | Image with URL and dimensions |
| ProductOption | Option definition (Size, Color, etc.) |
| Money | Monetary value with currency |
| PriceRange | Min/max variant prices |
| SEO | Search engine optimization data |
| Metafield | Custom metadata attached to resources |
| MetafieldInput | Metafield input for mutations |
| SelectedOption | Variant option selection |
| InventoryLevel | Inventory at a location |

**Pagination Models:**

| Model | Purpose |
|-------|---------|
| PageInfo | Pagination cursor info (has_next_page, end_cursor) |
| ProductConnection | Paginated product list result (products, page_info) |

**Product Lifecycle Models:**

| Model | Purpose |
|-------|---------|
| ProductCreate | Input model for creating a new product |
| DuplicateProductResult | Result of duplicating a product (new_product, original_product_id) |
| DeleteProductResult | Result of deleting a product (deleted_product_id, success) |

**Partial Update Models:**

| Model | Purpose |
|-------|---------|
| UNSET | Sentinel value - field should not be updated |
| UnsetType | Type for UNSET sentinel |
| ProductUpdate | Partial update for product fields (all fields default to UNSET) |
| VariantUpdate | Partial update for variant fields (all fields default to UNSET) |
| VariantUpdateRequest | Update request with flexible identifier (GID or SKU) |
| BulkUpdateResult | Result of bulk update operations |
| UpdateSuccess | Successful update with updated variant |
| UpdateFailure | Failed update with identifier and error |

**Image Operation Models:**

| Model | Purpose |
|-------|---------|
| ImageSource | Source for image creation (url or file_path, alt_text) |
| ImageUpdate | Update model for image metadata (alt_text) |
| ImageCreateResult | Result of image creation (image_id, url, alt_text, status) |
| ImageCreateSuccess | Successful image creation |
| ImageCreateFailure | Failed image creation with error |
| ImageDeleteResult | Result of image deletion (product_id, deleted_image_ids, deleted_media_ids) |
| ImageReorderResult | Result of image reorder (product_id, job_id) |
| StagedUploadTarget | Target for staged file uploads (parameters as typed list) |
| StagedUploadParameter | Typed parameter for staged uploads (name, value) |

**Truncation Analysis Models:**

| Model | Purpose |
|-------|---------|
| TruncationInfo | Full truncation analysis result (is_truncated, fields, messages) |
| TruncationFields | Container for field-level truncation info |
| FieldTruncationInfo | Per-field truncation details (count, limit, is_truncated) |

**GraphQL Response Models:**

| Model | Purpose |
|-------|---------|
| VariantMutationResult | Typed variant data from mutation response |
| VariantsBulkUpdateResponse | Typed bulk update response wrapper |
| GraphQLErrorLocation | Typed error location (line, column) |
| GraphQLErrorExtensions | Typed error extensions with extra="allow" |

**Internal TypedDicts:**

| TypedDict | Purpose |
|-----------|---------|
| _AdaptersCache | Type-safe storage for cached adapter instances |

**Metafield Deletion Models:**

| Model | Purpose |
|-------|---------|
| MetafieldIdentifier | Identifies a metafield (owner_gid, namespace, key) |
| MetafieldDeleteResult | Result of metafield deletion (identifier, success, error) |
| MetafieldDeleteFailure | A failed metafield deletion with error details |

**Enums:**

| Enum | Values |
|------|--------|
| ProductStatus | ACTIVE, ARCHIVED, DRAFT |
| InventoryPolicy | DENY, CONTINUE |
| MetafieldType | Various Shopify metafield types |
| WeightUnit | GRAMS, KILOGRAMS, OUNCES, POUNDS |
| InventoryQuantityName | AVAILABLE, COMMITTED, DAMAGED, etc. |
| InventoryReason | correction, cycle_count_available, etc. |

---

### Exceptions (exceptions.py)

All exceptions inherit from ShopifyError for easy catching.

| Exception | Purpose | Attributes |
|-----------|---------|------------|
| ShopifyError | Base exception | message |
| AuthenticationError | Auth failed | message, shop_url |
| ProductNotFoundError | Product not found | product_id, message |
| VariantNotFoundError | Variant not found | variant_id, sku, message |
| AmbiguousSKUError | SKU matches multiple variants | sku, variant_ids, message |
| ImageNotFoundError | Image not found | image_id, product_id, message |
| ImageUploadError | Image upload failed | message, source |
| SessionNotActiveError | Session inactive | message |
| GraphQLError | Query errors | message, errors, query |
| GraphQLTimeoutError | Timeout on GraphQL | message, timeout_seconds |
| GraphQLErrorEntry | Structured error | message, locations, path, extensions |
| GraphQLErrorLocation | Error location | line, column |

---

### CLI Components

**cli.py**
* **Purpose:** Rich-click CLI with comprehensive product and image management commands
* **Location:** src/lib_shopify_graphql/cli.py

**CLI Commands:**

| Command | Description |
|---------|-------------|
| `info` | Display package metadata |
| `health` | Check Shopify API connectivity and credentials |
| `config` | Display current merged configuration |
| `config-deploy` | Deploy configuration files to target locations |
| `test-limits` | Analyze ALL products to detect GraphQL query limit truncation |
| `get-product` | Retrieve a product by ID |
| `create-product` | Create a new product (via options or --json) |
| `duplicate-product` | Duplicate an existing product |
| `delete-product` | Delete a product permanently |
| `update-product` | Update product fields (partial update) |
| `add-image` | Add image(s) to a product from URL or local file |
| `delete-image` | Delete an image from a product |
| `update-image` | Update image metadata (alt text) |
| `reorder-images` | Reorder product images |
| `tokencache-clear` | Clear cached OAuth access tokens |
| `skucache-clear` | Clear cached SKU-to-GID mappings |
| `cache-clear-all` | Clear all caches (tokens and SKU mappings) |
| `skucache-rebuild` | Rebuild SKU cache by reading all products from Shopify |
| `skucache-check` | Check SKU cache consistency against Shopify |

**Global Options:**

| Option | Description |
|--------|-------------|
| `--traceback` | Show full Python traceback on errors |
| `--profile` | Load configuration from a named profile |
| `--help` | Show help message |

---

## Implementation Details

**Data Architecture Enforcement (v2.0.0):**

All `dict[str, Any]` types at module boundaries have been replaced with typed Pydantic models:

* **GraphQL Error Handling:** `GraphQLErrorLocation` and `GraphQLErrorExtensions` provide typed access to error details
* **Mutation Responses:** `VariantMutationResult` and `VariantsBulkUpdateResponse` wrap mutation response data
* **Truncation Analysis:** `TruncationInfo`, `TruncationFields`, `FieldTruncationInfo` provide typed analysis results
* **Staged Uploads:** `StagedUploadTarget.parameters` uses `list[StagedUploadParameter]` instead of `dict[str, str]`
* **Adapter Cache:** `_AdaptersCache` TypedDict replaces `dict[str, Any]` for cached adapters

**Compatibility Shims:**

All StrEnum compatibility code is consolidated in `_compat.py`. No other module should define its own StrEnum shim.

**Architecture Enforcement:**

Enforced via import-linter with 4 contracts:

```toml
[tool.importlinter]
root_package = "lib_shopify_graphql"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Clean Architecture layers"
type = "layers"
layers = [
  "lib_shopify_graphql.adapters",
  "lib_shopify_graphql.application",
  "lib_shopify_graphql.domain",
]

[[tool.importlinter.contracts]]
name = "Domain has no framework dependencies"
type = "forbidden"
source_modules = ["lib_shopify_graphql.domain"]
forbidden_modules = ["shopify", "pydantic"]

[[tool.importlinter.contracts]]
name = "Application ports have no adapter dependencies"
type = "forbidden"
source_modules = ["lib_shopify_graphql.application.ports"]
forbidden_modules = ["shopify", "lib_shopify_graphql.adapters"]
```

**Key Configuration:**
* Shopify credentials via environment or config file
* API version defaults to 2026-01 (configurable per credentials)
* Tokens valid for 24 hours (auto-refresh available)
* GraphQL query limits configurable via `[graphql]` section in config

**GraphQL Query Limits (`[graphql]` section):**

Shopify's GraphQL Admin API enforces a query cost limit of 1000 points per request.
These limits control nested connection sizes to stay under the limit.

All product-related settings are prefixed with `product_` to allow future resource-specific limits (e.g., `order_*`, `customer_*`).

| Setting | Default | Environment Variable | Description |
|---------|---------|---------------------|-------------|
| `product_max_images` | 20 | `GRAPHQL__PRODUCT_MAX_IMAGES` | Max images per product |
| `product_max_media` | 20 | `GRAPHQL__PRODUCT_MAX_MEDIA` | Max media items per product |
| `product_max_options` | 10 | `GRAPHQL__PRODUCT_MAX_OPTIONS` | Max product options |
| `product_max_metafields` | 10 | `GRAPHQL__PRODUCT_MAX_METAFIELDS` | Max metafields per product |
| `product_max_variants` | 20 | `GRAPHQL__PRODUCT_MAX_VARIANTS` | Max variants per product |
| `product_max_variant_metafields` | 5 | `GRAPHQL__PRODUCT_MAX_VARIANT_METAFIELDS` | Max metafields per variant |
| `product_default_page_size` | 50 | `GRAPHQL__PRODUCT_DEFAULT_PAGE_SIZE` | Default page size for manual pagination |
| `product_iter_page_size` | 250 | `GRAPHQL__PRODUCT_ITER_PAGE_SIZE` | Page size for auto-pagination |
| `product_warn_on_truncation` | true | `GRAPHQL__PRODUCT_WARN_ON_TRUNCATION` | Log warnings when limits may truncate data |

**Cost Impact by Operation:**
* `get_product_by_id`: Single product query - safe to increase limits
* `list_products_paginated`: Cost = `page_size × nested_items` - increase cautiously
* `iter_products`: Uses `product_iter_page_size` (default 250) - same cost considerations
* `skucache_rebuild`: Only needs variants for SKU mapping - images/media not needed

**Error Handling Strategy:**
* All Shopify errors inherit from ShopifyError
* GraphQL errors include structured error entries
* Exceptions preserve context (shop_url, product_id, query)

---

## Testing Approach

**Unit Tests:**
* Mock adapters injected via DI (no monkey-patching)
* Test files in `tests/` mirror source structure
* Coverage threshold: 85% (unit tests), 50% (integration tests)
* Combined coverage (all tests): ~92%

**Test Commands:**
* `make test` - Unit tests with linting/type-check (88%+ coverage)
* `make test-slow` - Integration tests against live Shopify (`-m integration`)
* Run all tests: `COVERAGE_FILE=/tmp/.coverage pytest --cov=src/lib_shopify_graphql` (~92%)

**Key Test Files:**
* `tests/test_shopify_client.py` - Core API tests
* `tests/test_models.py` - Model validation tests
* `tests/test_cli.py` - CLI command tests (includes test-limits command tests)
* `tests/test_integration.py` - Integration tests against live Shopify shop

**Testing Pattern:**
```python
# Create mock adapters
mock_token = MagicMock()
mock_token.obtain_token.return_value = ("token", expiration)
mock_session_mgr = MagicMock()
mock_graphql = MagicMock()

# Inject via login parameters
session = login(
    credentials,
    token_provider=mock_token,
    session_manager=mock_session_mgr,
    graphql_client=mock_graphql,
)
```

---

## Known Issues & Future Improvements

**Current Limitations:**
* Domain layer is minimal (exceptions use Pydantic at boundary)
* Only product-related operations implemented (orders, customers pending)

**Implemented Features:**
* Product CRUD operations (`create_product`, `get_product_by_id`, `update_product`, `delete_product`, `duplicate_product`)
* Product listing with cursor-based pagination (`list_products`)
* SKU-based product lookup (`get_product_by_sku`, `get_product_id_from_sku`)
* Product and variant partial updates (`update_product`, `update_variant`, `update_variants_bulk`)
* Inventory management (`set_inventory`, `adjust_inventory`)
* Image management (`create_image`, `delete_image`, `update_image`, `reorder_images`)
* Metafield deletion (`delete_metafield`, `delete_metafields`)
* Token and SKU caching (JSON file and MySQL backends)
* Cache rebuild utility (`skucache_rebuild`)
* Full CLI with product and image commands

**Future Enhancements:**
* Add order query use cases
* Add customer query use cases
* Add sync subpackage for export/import (JSON, CSV, MySQL)
* Add webhook handling
* Add rate limit handling with backoff

---

## Documentation & Resources

**Internal References:**
* README.md - Full API documentation with parameter tables
* CLAUDE.md - Development guidelines with architecture overview
* INSTALL.md - Installation options
* DEVELOPMENT.md - Developer workflow

**External References:**
* Shopify GraphQL Admin API: https://shopify.dev/docs/api/admin-graphql
* ShopifyAPI Python: https://github.com/Shopify/shopify_python_api
* Clean Architecture: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html

---

**Created:** 2026-01-08
**Last Updated:** 2026-01-13
**Review Cycle:** Evaluate during feature additions

---

## Instructions for Use

1. Update this document when adding new use cases or API operations
2. Keep module descriptions in sync with code changes
3. Extend the architecture section when adding new layers or patterns
4. Run `make test` to verify import-linter contracts after changes
