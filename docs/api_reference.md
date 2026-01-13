## API Reference

### Core Functions

#### `login(credentials, *, token_provider=None, session_manager=None, graphql_client=None)`

Authenticate with Shopify using client credentials grant.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `credentials` | `ShopifyCredentials` | *required* | Credentials for authentication |
| `token_provider` | `TokenProviderPort \| None` | `None` | Custom token provider for DI (uses default if None) |
| `session_manager` | `SessionManagerPort \| None` | `None` | Custom session manager for DI (uses default if None) |
| `graphql_client` | `GraphQLClientPort \| None` | `None` | Custom GraphQL client for DI (uses default if None) |

**Returns:** `ShopifySession` - Active session for API calls.

**Raises:** `AuthenticationError` if authentication fails.

```python
from lib_shopify_graphql import login, ShopifyCredentials

credentials = ShopifyCredentials(
    shop_url="mystore.myshopify.com",
    client_id="your_client_id",
    client_secret="your_client_secret",
)
session = login(credentials)
```

---

#### `logout(session)`

Terminate an active Shopify session.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active session to terminate |

**Raises:** `SessionNotActiveError` if session is already inactive.

```python
from lib_shopify_graphql import logout

logout(session)
print(session.is_active)  # False
```

---

#### `get_product_by_id(session, product_id)`

Retrieve full product information by Shopify product ID.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Numeric ID or full GID |

**Returns:** `Product` - Full product data including variants and images.

**Raises:**
- `SessionNotActiveError` if session is not active
- `ProductNotFoundError` if product does not exist
- `GraphQLError` if query returns errors

```python
from lib_shopify_graphql import get_product_by_id

# By numeric ID
product = get_product_by_id(session, "123456789")

# By full GID
product = get_product_by_id(session, "gid://shopify/Product/123456789")

print(product.title)
print(product.status)  # ProductStatus.ACTIVE
print(len(product.variants))
```

---

#### `list_products(session, *, query=None, max_products=None, sku_resolver=None)`

Fetch all products with automatic pagination.

Convenience function that handles pagination internally and collects all products into a list. For shops with very large catalogs (10,000+ products), consider using `iter_products()` for memory efficiency or `list_products_paginated()` for manual control.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `query` | `str \| None` | `None` | Shopify search query (e.g., `"status:active"`) |
| `max_products` | `int \| None` | `None` | Maximum products to fetch (None = unlimited) |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | SKU resolver for cache updates |

**Returns:** `list[Product]` - List of all matching products.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if query returns errors

```python
from lib_shopify_graphql import list_products

# Fetch all products (auto-pagination)
products = list_products(session)
print(f"Got {len(products)} products")

# Filter with Shopify query syntax
active_products = list_products(session, query="status:active")
recent_updates = list_products(session, query="updated_at:>2024-01-01")

# Limit for safety on large shops
sample = list_products(session, max_products=100)
```

---

#### `list_products_paginated(session, *, first=50, after=None, query=None, sku_resolver=None)`

List products with manual cursor-based pagination.

Returns a single page of products with pagination info. Use for fine-grained control over pagination or when you need access to `PageInfo` metadata.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `first` | `int` | `50` | Number of products per page (1-250) |
| `after` | `str \| None` | `None` | Cursor for next page (from `page_info.end_cursor`) |
| `query` | `str \| None` | `None` | Shopify search query |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | SKU resolver for cache updates |

**Returns:** `ProductConnection` - Paginated result with products and page info.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if query returns errors

```python
from lib_shopify_graphql import list_products_paginated

# Get first page (default 50 products)
result = list_products_paginated(session)
print(f"Got {len(result.products)} products")

# Manual pagination loop
all_products = []
result = list_products_paginated(session, first=100)
all_products.extend(result.products)

while result.page_info.has_next_page:
    result = list_products_paginated(
        session,
        first=100,
        after=result.page_info.end_cursor,
    )
    all_products.extend(result.products)

print(f"Total products: {len(all_products)}")
```

---

#### `iter_products(session, *, query=None, sku_resolver=None)`

Iterate over all products with automatic pagination (memory efficient).

Generator that yields products one at a time. Ideal for large catalogs where loading all products into memory is impractical.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `query` | `str \| None` | `None` | Shopify search query |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | SKU resolver for cache updates |

**Yields:** `Product` - Products one at a time.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if query returns errors

```python
from lib_shopify_graphql import iter_products

# Process products one at a time (memory efficient)
for product in iter_products(session):
    print(f"Processing: {product.title}")
    # Process each product without loading all into memory

# Count products without storing them all
count = sum(1 for _ in iter_products(session, query="status:active"))
print(f"Active products: {count}")
```

**Query Syntax Examples:**
- `status:active` - Only active products
- `status:draft` - Only draft products
- `status:archived` - Only archived products
- `updated_at:>2024-01-01` - Updated after date
- `created_at:>=2024-06-01` - Created on or after date
- `vendor:MyVendor` - By vendor name
- `product_type:Shoes` - By product type
- `tag:sale` - Products with specific tag
- `title:*shirt*` - Title contains "shirt"
- `inventory_total:>0` - In stock products

---

#### `get_product_id_from_sku(session, sku, *, sku_resolver=None)`

Get all product GIDs for variants with a given SKU.

In Shopify, SKUs should typically be unique, but multiple variants (possibly on different products) can have the same SKU. This function returns ALL matching products.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `sku` | `str` | *required* | Variant SKU to look up |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | Custom SKU resolver (uses default if None) |

**Returns:** `list[str]` - List of product GIDs. Empty list if SKU not found.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if query fails

```python
from lib_shopify_graphql import get_product_id_from_sku

# Get all product GIDs for a SKU
product_ids = get_product_id_from_sku(session, "SKU-12345")

if not product_ids:
    print("SKU not found")
elif len(product_ids) == 1:
    # Single product - most common case
    product = get_product_by_id(session, product_ids[0])
    print(f"Found: {product.title}")
else:
    # Multiple products have this SKU (duplicates)
    print(f"Warning: {len(product_ids)} products have SKU 'SKU-12345'")
    for pid in product_ids:
        print(f"  - {pid}")
```

---

#### `get_product_by_sku(session, sku, *, sku_resolver=None)`

Retrieve product by variant SKU.

Fetches the full product that contains a variant with the given SKU. If the SKU matches variants on multiple different products, raises `AmbiguousSKUError`.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `sku` | `str` | *required* | Variant SKU to look up |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | Custom SKU resolver (uses default if None) |

**Returns:** `Product` - The product containing the variant with the given SKU.

**Raises:**
- `SessionNotActiveError` if session is not active
- `VariantNotFoundError` if no variant has this SKU
- `AmbiguousSKUError` if SKU matches variants on multiple products
- `GraphQLError` if query fails

```python
from lib_shopify_graphql import get_product_by_sku

# Get product by SKU (returns full product, not just variant)
product = get_product_by_sku(session, "ABC-123")
print(f"Product: {product.title}")

# Find the specific variant
variant = next(v for v in product.variants if v.sku == "ABC-123")
print(f"Variant: {variant.title}, Price: {variant.price}")
```

---

#### `update_product(session, product_id, update)`

Update product fields. Only fields with values (not UNSET) are sent to Shopify.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Product GID or numeric ID |
| `update` | `ProductUpdate` | *required* | Fields to update |

**Returns:** `Product` - Updated product data.

**Raises:**
- `SessionNotActiveError` if session is not active
- `ProductNotFoundError` if product does not exist
- `GraphQLError` if mutation fails

> **Note:** Unlike `update_variant`, this function does not accept SKUs because SKUs are
> variant-level identifiers in Shopify. A product with multiple variants has multiple
> SKUs, making SKU-based product identification ambiguous.

```python
from lib_shopify_graphql import update_product, ProductUpdate, ProductStatus

updated = update_product(
    session,
    "gid://shopify/Product/123",
    ProductUpdate(
        title="New Title",
        status=ProductStatus.ACTIVE,
        tags=["sale", "featured"],
    ),
)
```

---

#### `update_variant(session, variant_id_or_sku, update, *, product_id=None, sku_resolver=None)`

Update a single variant by GID or SKU.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `variant_id_or_sku` | `str` | *required* | Variant GID, numeric ID, or SKU |
| `update` | `VariantUpdate` | *required* | Fields to update |
| `product_id` | `str \| None` | `None` | Product GID (auto-fetched if not provided) |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | Custom SKU resolver |

**Returns:** `ProductVariant` - Updated variant data.

**Raises:**
- `SessionNotActiveError` if session is not active
- `VariantNotFoundError` if variant does not exist
- `AmbiguousSKUError` if SKU matches multiple variants (use explicit GID instead)
- `GraphQLError` if mutation fails

> **Important:** SKUs in Shopify are NOT guaranteed to be unique. If a SKU matches
> multiple variants, an `AmbiguousSKUError` is raised. Use explicit variant GID instead.

```python
from decimal import Decimal
from lib_shopify_graphql import update_variant, VariantUpdate, AmbiguousSKUError

# Update by SKU (safe when SKU is unique)
try:
    updated = update_variant(
        session,
        "SKU-12345",
        VariantUpdate(price=Decimal("29.99"), barcode="123456789012"),
    )
except AmbiguousSKUError as e:
    print(f"SKU '{e.sku}' matches {len(e.variant_gids)} variants:")
    for gid in e.variant_gids:
        print(f"  - {gid}")
    print("Use explicit variant GID instead.")

# Update by GID, clear compare_at_price
updated = update_variant(
    session,
    "gid://shopify/ProductVariant/123",
    VariantUpdate(compare_at_price=None),  # Clears the field
)
```

---

#### `update_variants_bulk(session, product_id, updates, *, sku_resolver=None, allow_partial=True)`

Update multiple variants in one API call.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Product GID or numeric ID |
| `updates` | `list[VariantUpdateRequest]` | *required* | List of update requests |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | Custom SKU resolver |
| `allow_partial` | `bool` | `True` | If True, valid updates proceed even if some fail |

**Returns:** `BulkUpdateResult` - Result with succeeded and failed updates.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if mutation fails entirely

```python
from decimal import Decimal
from lib_shopify_graphql import (
    update_variants_bulk, VariantUpdate, VariantUpdateRequest
)

result = update_variants_bulk(
    session,
    "gid://shopify/Product/456",
    [
        VariantUpdateRequest(
            sku="SKU-001",
            update=VariantUpdate(price=Decimal("19.99")),
        ),
        VariantUpdateRequest(
            variant_id="gid://shopify/ProductVariant/789",
            update=VariantUpdate(barcode="123456789012"),
        ),
    ],
)

logger.info("Bulk update complete", extra={
    "updated": result.success_count,
    "failed": result.failure_count,
})

for failure in result.failed:
    logger.warning("Variant update failed", extra={
        "identifier": failure.identifier,
        "error": failure.error,
    })
```

---

#### `set_inventory(session, variant_id_or_sku, quantity, *, location_id=None, reason="correction", sku_resolver=None, location_resolver=None)`

Set absolute inventory quantity for a variant.

**Location Resolution Order:**
1. `location_id` parameter (explicit)
2. Config: `shopify.default_location_id`
3. Shop's primary location (auto-fetched)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `variant_id_or_sku` | `str` | *required* | Variant GID, numeric ID, or SKU |
| `quantity` | `int` | *required* | Absolute quantity to set |
| `location_id` | `str \| None` | `None` | Location GID override |
| `reason` | `str` | `"correction"` | Reason for the change |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | Custom SKU resolver |
| `location_resolver` | `LocationResolverPort \| None` | `None` | Custom location resolver |

**Returns:** `InventoryLevel` - New inventory level.

```python
from lib_shopify_graphql import set_inventory

# Set inventory at default location
level = set_inventory(session, "SKU-12345", quantity=100)

# Set inventory at specific location
level = set_inventory(
    session,
    "SKU-12345",
    quantity=50,
    location_id="gid://shopify/Location/123",
    reason="received",
)
```

---

#### `adjust_inventory(session, variant_id_or_sku, delta, *, location_id=None, reason="correction", sku_resolver=None, location_resolver=None)`

Adjust inventory by a delta (+5, -3, etc.).

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `variant_id_or_sku` | `str` | *required* | Variant GID, numeric ID, or SKU |
| `delta` | `int` | *required* | Amount to adjust (+/-) |
| `location_id` | `str \| None` | `None` | Location GID override |
| `reason` | `str` | `"correction"` | Reason for the change |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | Custom SKU resolver |
| `location_resolver` | `LocationResolverPort \| None` | `None` | Custom location resolver |

**Returns:** `InventoryLevel` - Adjusted inventory level.

```python
from lib_shopify_graphql import adjust_inventory

# Add 10 units
level = adjust_inventory(session, "SKU-12345", delta=10)

# Remove 5 units
level = adjust_inventory(session, "SKU-12345", delta=-5, reason="damaged")
```

---

### Product Lifecycle

#### `create_product(session, product, *, sku_resolver=None)`

Create a new product in Shopify.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product` | `ProductCreate` | *required* | Product data for creation |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | SKU resolver for cache updates |

**Returns:** `Product` - The created product.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if mutation fails

```python
from lib_shopify_graphql import create_product, ProductCreate, ProductStatus

# Create a simple product
product = ProductCreate(
    title="New T-Shirt",
    description="A comfortable cotton t-shirt",
    vendor="My Brand",
    product_type="Apparel",
    status=ProductStatus.DRAFT,
)
created = create_product(session, product)
print(f"Created: {created.id}")
```

---

#### `duplicate_product(session, product_id, new_title, *, include_images=True, new_status=None, sku_resolver=None)`

Duplicate an existing product.

Creates a copy of an existing product with a new title. Useful for creating variants of existing products or templates.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | ID of product to duplicate |
| `new_title` | `str` | *required* | Title for the duplicated product |
| `include_images` | `bool` | `True` | Whether to copy images |
| `new_status` | `ProductStatus \| None` | `None` | Status for the new product |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | SKU resolver for cache updates |

**Returns:** `DuplicateProductResult` - Result with new product.

**Raises:**
- `SessionNotActiveError` if session is not active
- `ProductNotFoundError` if product doesn't exist
- `GraphQLError` if mutation fails

```python
from lib_shopify_graphql import duplicate_product, ProductStatus

# Duplicate with images
result = duplicate_product(session, "123456789", "Copy of My Product")
print(f"New product: {result.new_product.id}")

# Duplicate without images, as draft
result = duplicate_product(
    session,
    "123456789",
    "New Variant",
    include_images=False,
    new_status=ProductStatus.DRAFT,
)
```

---

#### `delete_product(session, product_id, *, sku_resolver=None)`

Delete a product permanently.

**WARNING:** This operation is irreversible. The product and all its variants, inventory, images, and associated data will be permanently deleted.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | ID of product to delete |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | SKU resolver for cache invalidation |

**Returns:** `DeleteProductResult` - Confirmation with deleted product ID.

**Raises:**
- `SessionNotActiveError` if session is not active
- `ProductNotFoundError` if product doesn't exist
- `GraphQLError` if deletion fails

```python
from lib_shopify_graphql import delete_product

# Delete product permanently
result = delete_product(session, "gid://shopify/Product/123456789")
print(f"Deleted: {result.deleted_product_id}")
```

---

### Image Operations

#### `create_image(session, product_id, source)`

Create a single product image.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Product GID or numeric ID |
| `source` | `ImageSource` | *required* | Image source (URL or file path) |

**Returns:** `ImageCreateSuccess` - Created image details.

**Raises:**
- `SessionNotActiveError` if session is not active
- `ImageUploadError` if file upload fails
- `GraphQLError` if mutation fails

```python
from lib_shopify_graphql import create_image, ImageSource

# Create from URL
success = create_image(
    session,
    product_id,
    ImageSource(url="https://example.com/image.jpg", alt_text="Front view"),
)
print(f"Image created: {success.image_id}")

# Create from local file
success = create_image(
    session,
    product_id,
    ImageSource(file_path="/path/to/image.jpg", alt_text="Back view"),
)
```

---

#### `create_images(session, product_id, sources)`

Create multiple product images in batch.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Product GID or numeric ID |
| `sources` | `list[ImageSource]` | *required* | List of image sources |

**Returns:** `ImageCreateResult` - Result with succeeded and failed lists.

**Raises:**
- `SessionNotActiveError` if session is not active

```python
from lib_shopify_graphql import create_images, ImageSource

result = create_images(session, product_id, [
    ImageSource(url="https://example.com/1.jpg", alt_text="Front"),
    ImageSource(url="https://example.com/2.jpg", alt_text="Back"),
    ImageSource(file_path="/local/3.jpg", alt_text="Side"),
])
print(f"Created: {result.success_count}, Failed: {result.failure_count}")

for failure in result.failed:
    print(f"Failed: {failure.source} - {failure.error}")
```

---

#### `update_image(session, product_id, image_id, update)`

Update image metadata (alt text).

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Product GID or numeric ID |
| `image_id` | `str` | *required* | Image/media GID or numeric ID |
| `update` | `ImageUpdate` | *required* | Fields to update |

**Returns:** `ImageCreateSuccess` - Updated image details.

**Raises:**
- `SessionNotActiveError` if session is not active
- `ImageNotFoundError` if image does not exist
- `ValueError` if no fields to update
- `GraphQLError` if mutation fails

```python
from lib_shopify_graphql import update_image, ImageUpdate

success = update_image(
    session,
    product_id,
    image_id,
    ImageUpdate(alt_text="Updated alt text for accessibility"),
)
print(f"Updated: {success.image_id}")
```

---

#### `delete_image(session, product_id, image_id)`

Delete a single product image.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Product GID or numeric ID |
| `image_id` | `str` | *required* | Image/media GID or numeric ID |

**Returns:** `ImageDeleteResult` - Result with deleted IDs.

**Raises:**
- `SessionNotActiveError` if session is not active
- `ImageNotFoundError` if image does not exist
- `GraphQLError` if mutation fails

```python
from lib_shopify_graphql import delete_image

result = delete_image(session, product_id, image_id)
print(f"Deleted media IDs: {result.deleted_media_ids}")
```

---

#### `delete_images(session, product_id, image_ids)`

Delete multiple product images.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Product GID or numeric ID |
| `image_ids` | `list[str]` | *required* | List of image/media GIDs or numeric IDs |

**Returns:** `ImageDeleteResult` - Result with deleted IDs.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if mutation fails

```python
from lib_shopify_graphql import delete_images

result = delete_images(session, product_id, [image_id_1, image_id_2, image_id_3])
print(f"Deleted {len(result.deleted_media_ids)} images")
```

---

#### `reorder_images(session, product_id, image_ids)`

Reorder product images.

Images will be reordered to match the order of the provided image_ids list. This is an async operation in Shopify.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `product_id` | `str` | *required* | Product GID or numeric ID |
| `image_ids` | `list[str]` | *required* | Image IDs in desired order |

**Returns:** `ImageReorderResult` - Result with job_id for tracking.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if mutation fails

```python
from lib_shopify_graphql import reorder_images

# Reorder images: put image_3 first, then image_1, then image_2
result = reorder_images(session, product_id, [image_3, image_1, image_2])
print(f"Reorder job: {result.job_id}")
```

---

### Metafield Operations

#### `delete_metafield(session, owner_id, namespace, key)`

Delete a single metafield by owner + namespace + key.

This operation is idempotent - deleting a non-existent metafield returns False (not an error).

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `owner_id` | `str` | *required* | Owner GID (e.g., `gid://shopify/Product/123`) |
| `namespace` | `str` | *required* | Metafield namespace (e.g., `custom`) |
| `key` | `str` | *required* | Metafield key within the namespace |

**Returns:** `bool` - True if deleted, False if didn't exist.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if deletion fails with an error

```python
from lib_shopify_graphql import delete_metafield

# Delete a product metafield
deleted = delete_metafield(
    session,
    owner_id="gid://shopify/Product/123",
    namespace="custom",
    key="warranty_months",
)
if deleted:
    print("Metafield deleted")
else:
    print("Metafield didn't exist")
```

---

#### `delete_metafields(session, metafields)`

Delete multiple metafields in one API call.

Deletes metafields identified by owner + namespace + key. The operation is partially idempotent - deleting non-existent metafields is not an error.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `metafields` | `list[MetafieldIdentifier]` | *required* | Metafields to delete |

**Returns:** `MetafieldDeleteResult` - Result with deleted and failed lists.

**Raises:**
- `SessionNotActiveError` if session is not active
- `GraphQLError` if entire mutation fails

```python
from lib_shopify_graphql import delete_metafields, MetafieldIdentifier

result = delete_metafields(session, [
    MetafieldIdentifier(
        owner_id="gid://shopify/Product/123",
        namespace="custom",
        key="old_field_1",
    ),
    MetafieldIdentifier(
        owner_id="gid://shopify/Product/123",
        namespace="custom",
        key="old_field_2",
    ),
])
print(f"Deleted: {result.deleted_count}, Failed: {result.failed_count}")
```

---

### Cache Operations

#### `skucache_rebuild(session, *, sku_resolver=None, query=None)`

Rebuild SKU cache by reading all products from the store.

Iterates through all products and updates the SKU cache with every variant's SKU-to-GID mapping. Use this to rebuild the cache after bulk changes or verify cache consistency.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `ShopifySession` | *required* | Active Shopify session |
| `sku_resolver` | `SKUResolverPort \| None` | `None` | SKU resolver with cache (required) |
| `query` | `str \| None` | `None` | Shopify query filter (e.g., `status:active`) |

**Returns:** `int` - Total number of variants cached.

**Raises:**
- `SessionNotActiveError` if session is not active
- `ValueError` if sku_resolver is not provided
- `GraphQLError` if query fails

```python
from lib_shopify_graphql import skucache_rebuild

# Rebuild entire SKU cache
count = skucache_rebuild(session, sku_resolver=resolver)
print(f"Cached {count} variant SKUs")

# Rebuild only for active products
count = skucache_rebuild(session, sku_resolver=resolver, query="status:active")
```

---

### Models

#### `ShopifyCredentials`

Credentials for Shopify API authentication via Client Credentials Grant.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `shop_url` | `str` | *required* | Store URL (e.g., 'mystore.myshopify.com' or 'shop.example.com') |
| `api_version` | `str` | `"2026-01"` | Shopify API version (format: YYYY-MM) |
| `client_id` | `str` | *required* | OAuth client ID from Dev Dashboard |
| `client_secret` | `str` | *required* | OAuth client secret from Dev Dashboard |

```python
from lib_shopify_graphql import ShopifyCredentials

# Minimal (uses default API version 2026-01)
credentials = ShopifyCredentials(
    shop_url="mystore.myshopify.com",
    client_id="your_client_id",
    client_secret="your_client_secret",
)

# Custom domain with explicit API version
credentials = ShopifyCredentials(
    shop_url="shop.example.com",  # Custom domain supported
    api_version="2025-01",
    client_id="your_client_id",
    client_secret="your_client_secret",
)
```

---

#### `ShopifySession`

Active Shopify session wrapper with API methods.

| Property/Method | Type | Description |
|-----------------|------|-------------|
| `is_active` | `bool` | Whether session is currently active |
| `info` | `ShopifySessionInfo` | Read-only session information |
| `is_token_expired()` | `bool` | Check if access token has expired |
| `refresh_token()` | `None` | Refresh access token using stored credentials |
| `execute_graphql(query, variables=None)` | `dict[str, Any]` | Execute raw GraphQL query |
| `get_credentials()` | `ShopifyCredentials` | Get credentials used for this session |

```python
# Check session status
print(session.is_active)  # True
print(session.info.shop_url)  # mystore.myshopify.com
print(session.info.token_expiration)  # datetime when token expires

# Check/refresh token
if session.is_token_expired():
    session.refresh_token()

# Execute raw GraphQL query
result = session.execute_graphql("{ shop { name } }")
print(result["data"]["shop"]["name"])
```

---

#### `ShopifySessionInfo`

Read-only information about an active Shopify session.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `shop_url` | `str` | *required* | Connected store URL |
| `api_version` | `str` | *required* | API version in use |
| `is_active` | `bool` | `True` | Whether session is active |
| `token_expiration` | `datetime \| None` | `None` | When access token expires |

---

#### `Product`

Full Shopify product data.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | `str` | *required* | Shopify GID (e.g., 'gid://shopify/Product/123') |
| `legacy_resource_id` | `str \| None` | `None` | REST API numeric ID |
| `title` | `str` | *required* | Product title |
| `description` | `str \| None` | `None` | Plain text description |
| `description_html` | `str \| None` | `None` | HTML formatted description |
| `handle` | `str` | *required* | URL-friendly identifier |
| `vendor` | `str \| None` | `None` | Product vendor/manufacturer |
| `product_type` | `str \| None` | `None` | Product category/type |
| `status` | `ProductStatus` | *required* | Publication status (ACTIVE, ARCHIVED, DRAFT) |
| `tags` | `list[str]` | `[]` | List of product tags |
| `created_at` | `datetime` | *required* | Creation timestamp |
| `updated_at` | `datetime` | *required* | Last modification timestamp |
| `published_at` | `datetime \| None` | `None` | Publication timestamp |
| `variants` | `list[ProductVariant]` | `[]` | List of product variants |
| `images` | `list[ProductImage]` | `[]` | List of product images |
| `featured_image` | `ProductImage \| None` | `None` | Primary display image |
| `options` | `list[ProductOption]` | `[]` | Product options (Size, Color, etc.) |
| `seo` | `SEO \| None` | `None` | SEO metadata |
| `price_range` | `PriceRange \| None` | `None` | Min/max variant prices |
| `total_inventory` | `int \| None` | `None` | Total inventory across variants |
| `tracks_inventory` | `bool` | `True` | Whether inventory is tracked |
| `has_only_default_variant` | `bool` | `False` | True if only one default variant |
| `has_out_of_stock_variants` | `bool` | `False` | True if any variants out of stock |
| `is_gift_card` | `bool` | `False` | Whether this is a gift card |
| `online_store_url` | `str \| None` | `None` | URL on online store |
| `online_store_preview_url` | `str \| None` | `None` | Preview URL |
| `template_suffix` | `str \| None` | `None` | Theme template suffix |
| `metafields` | `list[Metafield]` | `[]` | Custom metadata |

```python
product = get_product_by_id(session, "123456789")

print(product.id)           # gid://shopify/Product/123456789
print(product.title)        # "My Product"
print(product.handle)       # "my-product"
print(product.status)       # ProductStatus.ACTIVE
print(product.vendor)       # "My Vendor"
print(product.tags)         # ["tag1", "tag2"]
print(product.created_at)   # datetime object

# Access variants
for variant in product.variants:
    print(f"{variant.title}: {variant.price.amount} {variant.price.currency_code}")
    print(f"  SKU: {variant.sku}")
    print(f"  Inventory: {variant.inventory_quantity}")

# Access images
for image in product.images:
    print(f"{image.url} ({image.width}x{image.height})")
```

---

#### `ProductVariant`

Product variant data from Shopify.

| Attribute            | Type                      | Default    | Description                         |
|----------------------|---------------------------|------------|-------------------------------------|
| `id`                 | `str`                     | *required* | Shopify GID for the variant         |
| `title`              | `str`                     | *required* | Variant title (e.g., 'Small / Red') |
| `display_name`       | `str \| None`             | `None`     | Full display name                   |
| `sku`                | `str \| None`             | `None`     | Stock keeping unit                  |
| `barcode`            | `str \| None`             | `None`     | Barcode (UPC, ISBN, etc.)           |
| `price`              | `Money`                   | *required* | Current price                       |
| `compare_at_price`   | `Money \| None`           | `None`     | Original price for discount         |
| `inventory_quantity` | `int \| None`             | `None`     | Available inventory count           |
| `inventory_policy`   | `InventoryPolicy \| None` | `None`     | Policy when out of stock            |
| `available_for_sale` | `bool`                    | `True`     | Whether variant can be purchased    |
| `taxable`            | `bool`                    | `True`     | Whether variant is taxable          |
| `position`           | `int`                     | `1`        | Display order (1-indexed)           |
| `created_at`         | `datetime \| None`        | `None`     | Creation timestamp                  |
| `updated_at`         | `datetime \| None`        | `None`     | Last modification timestamp         |
| `image`              | `ProductImage \| None`    | `None`     | Variant-specific image              |
| `selected_options`   | `list[SelectedOption]`    | `[]`       | Selected option name/value pairs    |
| `metafields`         | `list[Metafield]`         | `[]`       | Custom metadata                     |

---

#### `ProductImage`

Product image data from Shopify.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | `str` | *required* | Shopify GID for the image |
| `url` | `str` | *required* | Full URL to the image |
| `alt_text` | `str \| None` | `None` | Alternative text for accessibility |
| `width` | `int \| None` | `None` | Image width in pixels |
| `height` | `int \| None` | `None` | Image height in pixels |

---

#### `ProductOption`

Product option definition (e.g., Size, Color).

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | `str` | *required* | Shopify GID for the option |
| `name` | `str` | *required* | Option name (e.g., 'Size', 'Color') |
| `position` | `int` | *required* | Display order (1-indexed) |
| `values` | `list[str]` | `[]` | List of option values |

---

#### `Money`

Monetary value with currency code.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `amount` | `Decimal` | *required* | Decimal amount |
| `currency_code` | `str` | *required* | ISO 4217 currency code (3 chars) |

```python
from decimal import Decimal
from lib_shopify_graphql import Money

price = Money(amount=Decimal("19.99"), currency_code="USD")
print(f"{price.amount} {price.currency_code}")  # 19.99 USD
```

---

#### `PriceRange`

Price range for a product (min and max variant prices).

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_variant_price` | `Money` | *required* | Lowest price among variants |
| `max_variant_price` | `Money` | *required* | Highest price among variants |

---

#### `SEO`

Search engine optimization data.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | `str \| None` | `None` | SEO title |
| `description` | `str \| None` | `None` | SEO meta description |

---

#### `Metafield`

Custom metadata attached to a Shopify resource.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | `str` | *required* | Shopify GID for the metafield |
| `namespace` | `str` | *required* | Container grouping (e.g., 'custom') |
| `key` | `str` | *required* | Unique identifier within namespace |
| `value` | `str` | *required* | Data stored as string |
| `type` | `MetafieldType` | *required* | Data type enum |
| `created_at` | `datetime \| None` | `None` | Creation timestamp |
| `updated_at` | `datetime \| None` | `None` | Last modification timestamp |

---

#### `SelectedOption`

A product variant's selected option (e.g., Size: Large).

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | *required* | Option name (e.g., 'Size') |
| `value` | `str` | *required* | Selected value (e.g., 'Large') |

---

### Pagination Models

#### `PageInfo`

Pagination cursor information from Shopify GraphQL connections.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `has_next_page` | `bool` | *required* | Whether more results exist |
| `has_previous_page` | `bool` | `False` | Whether previous results exist |
| `start_cursor` | `str \| None` | `None` | Cursor for first item |
| `end_cursor` | `str \| None` | `None` | Cursor for last item (use with `after`) |

```python
from lib_shopify_graphql import list_products_paginated

result = list_products_paginated(session, first=50)

# Check if more pages exist
if result.page_info.has_next_page:
    next_page = list_products_paginated(
        session,
        first=50,
        after=result.page_info.end_cursor,
    )
```

---

#### `ProductConnection`

Paginated product list result from `list_products_paginated()`.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `products` | `list[Product]` | `[]` | Products in this page |
| `page_info` | `PageInfo` | *required* | Pagination information |
| `total_count` | `int \| None` | `None` | Total products (if available) |

```python
from lib_shopify_graphql import list_products_paginated

# Get all products with pagination
all_products = []
result = list_products_paginated(session, first=100)

while True:
    all_products.extend(result.products)
    if not result.page_info.has_next_page:
        break
    result = list_products_paginated(session, first=100, after=result.page_info.end_cursor)

print(f"Fetched {len(all_products)} products")
```

---

### Partial Update Models

#### `UNSET`

Singleton sentinel indicating a field should not be updated.

```python
from lib_shopify_graphql import UNSET, VariantUpdate

# Price is set, barcode defaults to UNSET
update = VariantUpdate(price=Decimal("29.99"))
update.barcode is UNSET  # True - field won't be sent to Shopify
```

---

#### `VariantUpdate`

Partial update for variant fields. All fields default to `UNSET`.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `price` | `Updatable[Decimal]` | `UNSET` | Variant price |
| `compare_at_price` | `Updatable[Decimal]` | `UNSET` | Original price (for discount display) |
| `cost` | `Updatable[Decimal]` | `UNSET` | Unit cost |
| `sku` | `Updatable[str]` | `UNSET` | Stock keeping unit |
| `barcode` | `Updatable[str]` | `UNSET` | Barcode (UPC, ISBN, etc.) |
| `inventory_policy` | `Updatable[InventoryPolicy]` | `UNSET` | Out-of-stock policy |
| `weight` | `Updatable[Decimal]` | `UNSET` | Weight value |
| `weight_unit` | `Updatable[WeightUnit]` | `UNSET` | Weight unit |
| `requires_shipping` | `Updatable[bool]` | `UNSET` | Whether shipping is required |
| `taxable` | `Updatable[bool]` | `UNSET` | Whether taxable |
| `tax_code` | `Updatable[str]` | `UNSET` | Tax code |
| `fulfillment_service` | `Updatable[str]` | `UNSET` | Fulfillment service |
| `option1` | `Updatable[str]` | `UNSET` | First option value |
| `option2` | `Updatable[str]` | `UNSET` | Second option value |
| `option3` | `Updatable[str]` | `UNSET` | Third option value |
| `image_id` | `Updatable[str]` | `UNSET` | Associated image GID |
| `metafields` | `Updatable[list[MetafieldInput]]` | `UNSET` | Metafield updates |
| `harmonized_system_code` | `Updatable[str]` | `UNSET` | HS code for customs |
| `country_code_of_origin` | `Updatable[str]` | `UNSET` | Country of origin |

```python
from decimal import Decimal
from lib_shopify_graphql import VariantUpdate, UNSET

# Update only price and barcode
update = VariantUpdate(
    price=Decimal("29.99"),
    barcode="123456789012",
)

# Clear compare_at_price (remove sale)
update = VariantUpdate(compare_at_price=None)

# Get only fields that will be sent
update.get_set_fields()  # {"compare_at_price": None}
```

---

#### `ProductUpdate`

Partial update for product fields. All fields default to `UNSET`.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | `Updatable[str]` | `UNSET` | Product title |
| `description_html` | `Updatable[str]` | `UNSET` | HTML description |
| `handle` | `Updatable[str]` | `UNSET` | URL handle |
| `vendor` | `Updatable[str]` | `UNSET` | Vendor name |
| `product_type` | `Updatable[str]` | `UNSET` | Product type |
| `tags` | `Updatable[list[str]]` | `UNSET` | Product tags (replaces all) |
| `status` | `Updatable[ProductStatus]` | `UNSET` | Publication status |
| `seo_title` | `Updatable[str]` | `UNSET` | SEO title |
| `seo_description` | `Updatable[str]` | `UNSET` | SEO description |
| `template_suffix` | `Updatable[str]` | `UNSET` | Theme template suffix |
| `gift_card` | `Updatable[bool]` | `UNSET` | Is gift card |
| `collections_to_join` | `Updatable[list[str]]` | `UNSET` | Collection GIDs to add |
| `collections_to_leave` | `Updatable[list[str]]` | `UNSET` | Collection GIDs to remove |
| `category` | `Updatable[str]` | `UNSET` | Product category ID |
| `metafields` | `Updatable[list[MetafieldInput]]` | `UNSET` | Metafield updates |
| `requires_selling_plan` | `Updatable[bool]` | `UNSET` | Requires subscription |

```python
from lib_shopify_graphql import ProductUpdate, ProductStatus

update = ProductUpdate(
    title="Updated Title",
    status=ProductStatus.ACTIVE,
    tags=["new", "sale"],  # Replaces all existing tags
)
```

---

#### `VariantUpdateRequest`

Request to update a variant with flexible identifier.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `variant_id` | `str \| None` | `None` | Variant GID or numeric ID |
| `sku` | `str \| None` | `None` | SKU (resolved via cache) |
| `update` | `VariantUpdate` | *required* | Fields to update |
| `location_id` | `str \| None` | `None` | Location override for inventory |

> Either `variant_id` or `sku` must be provided.

```python
from lib_shopify_graphql import VariantUpdateRequest, VariantUpdate

# By SKU
req = VariantUpdateRequest(
    sku="SKU-123",
    update=VariantUpdate(price=Decimal("19.99")),
)

# By GID
req = VariantUpdateRequest(
    variant_id="gid://shopify/ProductVariant/123",
    update=VariantUpdate(barcode="123456789012"),
)
```

---

#### `BulkUpdateResult`

Result of a bulk update operation.

| Property | Type | Description |
|----------|------|-------------|
| `succeeded` | `list[UpdateSuccess]` | Successful updates |
| `failed` | `list[UpdateFailure]` | Failed updates |
| `success_count` | `int` | Number of successes |
| `failure_count` | `int` | Number of failures |
| `all_succeeded` | `bool` | True if no failures |

```python
result = update_variants_bulk(session, product_id, requests)

if not result.all_succeeded:
    for failure in result.failed:
        logger.warning("Update failed", extra={
            "identifier": failure.identifier,
            "error": failure.error,
        })
```

---

#### `InventoryLevel`

Inventory level at a specific location.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `inventory_item_id` | `str` | *required* | Inventory item GID |
| `location_id` | `str` | *required* | Location GID |
| `available` | `int` | *required* | Available quantity |
| `updated_at` | `datetime \| None` | `None` | Last update time |

---

### Enums

#### `ProductStatus`

Product publication status in Shopify.

| Value | Description |
|-------|-------------|
| `ACTIVE` | Product is visible to customers |
| `ARCHIVED` | Product is hidden and not for sale |
| `DRAFT` | Product is being prepared and not yet published |

---

#### `InventoryPolicy`

Policy for selling when out of stock.

| Value | Description |
|-------|-------------|
| `DENY` | Stop selling when out of stock |
| `CONTINUE` | Continue selling when out of stock |

---

#### `MetafieldType`

Shopify metafield data types.

| Value | Description |
|-------|-------------|
| `SINGLE_LINE_TEXT_FIELD` | Single line text |
| `MULTI_LINE_TEXT_FIELD` | Multi-line text |
| `NUMBER_INTEGER` | Integer number |
| `NUMBER_DECIMAL` | Decimal number |
| `BOOLEAN` | True/False value |
| `DATE` | Date without time |
| `DATE_TIME` | Date with time |
| `JSON` | JSON object |
| `COLOR` | Color value |
| `URL` | URL value |
| `MONEY` | Monetary value |
| `DIMENSION` | Physical dimension |
| `VOLUME` | Volume measurement |
| `WEIGHT` | Weight measurement |
| `RATING` | Rating value |
| `FILE_REFERENCE` | Reference to a file |
| `PRODUCT_REFERENCE` | Reference to a product |
| `VARIANT_REFERENCE` | Reference to a variant |
| `COLLECTION_REFERENCE` | Reference to a collection |
| `PAGE_REFERENCE` | Reference to a page |
| `METAOBJECT_REFERENCE` | Reference to a metaobject |
| `LIST_SINGLE_LINE_TEXT_FIELD` | List of single line text |
| `LIST_FILE_REFERENCE` | List of file references |
| `RICH_TEXT_FIELD` | Rich text content |

---

### Exceptions

All exceptions inherit from `ShopifyError` for easy catching.

#### `ShopifyError`

Base exception for all Shopify API operations.

```python
try:
    result = some_shopify_operation()
except ShopifyError as e:
    print(f"Shopify operation failed: {e}")
```

---

#### `AuthenticationError`

Authentication with Shopify failed.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error description |
| `shop_url` | `str \| None` | Shop URL that failed authentication |

```python
try:
    session = login(credentials)
except AuthenticationError as e:
    print(f"Auth failed for {e.shop_url}: {e.message}")
```

---

#### `ProductNotFoundError`

Product with given ID does not exist.

| Attribute | Type | Description |
|-----------|------|-------------|
| `product_id` | `str` | The product ID that was not found |
| `message` | `str` | Human-readable error description |

```python
try:
    product = get_product_by_id(session, "invalid-id")
except ProductNotFoundError as e:
    print(f"Product not found: {e.product_id}")
```

---

#### `VariantNotFoundError`

Variant with given ID or SKU does not exist.

| Attribute | Type | Description |
|-----------|------|-------------|
| `identifier` | `str` | The variant ID or SKU that was not found |
| `message` | `str` | Human-readable error description |

```python
try:
    update_variant(session, "INVALID-SKU", update)
except VariantNotFoundError as e:
    print(f"Variant not found: {e.identifier}")
```

---

#### `AmbiguousSKUError`

SKU matches multiple variants. Raised when a SKU lookup returns more than one
variant, indicating the SKU is not unique in the Shopify store.

> **Background:** SKUs in Shopify are NOT enforced to be unique. Multiple variants
> (potentially across different products) can share the same SKU. When this occurs,
> operations by SKU are ambiguous and you must use the explicit variant GID instead.

| Attribute | Type | Description |
|-----------|------|-------------|
| `sku` | `str` | The ambiguous SKU |
| `variant_gids` | `list[str]` | List of variant GIDs that match this SKU |
| `message` | `str` | Human-readable error description |

```python
from lib_shopify_graphql import update_variant, AmbiguousSKUError

try:
    update_variant(session, "SHARED-SKU", update)
except AmbiguousSKUError as e:
    print(f"SKU '{e.sku}' is ambiguous - matches {len(e.variant_gids)} variants:")
    for gid in e.variant_gids:
        print(f"  - {gid}")
    # Use explicit GID instead:
    update_variant(session, e.variant_gids[0], update)  # Update first match
```

---

#### `SessionNotActiveError`

Session is not active or has been logged out.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error description |

```python
try:
    product = get_product_by_id(session, "123")
except SessionNotActiveError as e:
    logger.error("Session error", extra={"message": e.message})
```

---

#### `GraphQLError`

GraphQL query returned errors.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error description |
| `errors` | `list[GraphQLErrorEntry]` | Structured error entries |
| `query` | `str \| None` | The query that caused the error |

```python
try:
    product = get_product_by_id(session, "123")
except GraphQLError as e:
    logger.error("GraphQL error", extra={
        "message": e.message,
        "errors": [
            {
                "message": err.message,
                "code": err.extensions.get("code") if err.extensions else None,
                "path": err.path,
            }
            for err in e.errors
        ],
    })
```

---

#### `GraphQLErrorEntry`

Structured GraphQL error entry.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Error description |
| `locations` | `list[GraphQLErrorLocation] \| None` | Query locations |
| `path` | `list[str \| int] \| None` | Field path |
| `extensions` | `dict[str, object] \| None` | Additional metadata |

---

#### `GraphQLErrorLocation`

Location within a GraphQL query where an error occurred.

| Attribute | Type | Description |
|-----------|------|-------------|
| `line` | `int` | Line number (1-indexed) |
| `column` | `int` | Column number (1-indexed) |

---

#### `GraphQLTimeoutError`

GraphQL query exceeded the configured timeout.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error description |
| `timeout` | `float` | The timeout value that was exceeded (seconds) |
| `query` | `str \| None` | The query that timed out |

```python
from lib_shopify_graphql import GraphQLTimeoutError, DEFAULT_GRAPHQL_TIMEOUT_SECONDS

# Default timeout is 30 seconds (DEFAULT_GRAPHQL_TIMEOUT_SECONDS)
try:
    product = get_product_by_id(session, "123")
except GraphQLTimeoutError as e:
    logger.error("Query timed out", extra={
        "timeout": e.timeout,
        "query_preview": e.query[:100] if e.query else None,
    })
```

---

### Dependency Injection (Ports & Adapters)

The library uses Clean Architecture with Protocol-based ports for testability.

#### `TokenProviderPort`

Protocol for obtaining OAuth access tokens.

```python
class TokenProviderPort(Protocol):
    def obtain_token(
        self,
        shop_url: str,
        client_id: str,
        client_secret: str,
    ) -> tuple[str, datetime]: ...
```

---

#### `GraphQLClientPort`

Protocol for executing GraphQL queries.

```python
class GraphQLClientPort(Protocol):
    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
```

---

#### `SessionManagerPort`

Protocol for managing API session state.

```python
class SessionManagerPort(Protocol):
    def create_session(
        self,
        shop_url: str,
        api_version: str,
        access_token: str,
    ) -> Any: ...

    def activate_session(self, session: Any) -> None: ...

    def clear_session(self) -> None: ...
```

---

#### `create_adapters(...)`

Create a bundle of adapters for dependency injection.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `token_provider` | `TokenProviderPort \| None` | `None` | Custom token provider |
| `session_manager` | `SessionManagerPort \| None` | `None` | Custom session manager |
| `graphql_client` | `GraphQLClientPort \| None` | `None` | Custom GraphQL client |

**Returns:** `AdapterBundle` - TypedDict with all adapters.

```python
from lib_shopify_graphql import login, create_adapters

# Using defaults
adapters = create_adapters()
session = login(credentials, **adapters)

# Using custom adapter for testing
class FakeTokenProvider:
    def obtain_token(self, shop_url, client_id, client_secret):
        return ("fake_token", datetime.now() + timedelta(hours=24))

adapters = create_adapters(token_provider=FakeTokenProvider())
session = login(credentials, **adapters)
```

---

#### `CachePort`

Protocol for key-value cache implementations.

```python
class CachePort(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...
```

---

#### `SKUResolverPort`

Protocol for resolving SKU to variant GID.

> **Important:** The `resolve()` method raises `AmbiguousSKUError` if the SKU
> matches multiple variants. Use `resolve_all()` to get all matches without error.

```python
class SKUResolverPort(Protocol):
    def resolve(self, sku: str, shop_url: str) -> str | None:
        """Resolve SKU to GID. Raises AmbiguousSKUError if multiple matches."""
        ...
    def resolve_all(self, sku: str) -> list[str]:
        """Resolve SKU to ALL matching GIDs (no error on multiple matches)."""
        ...
    def invalidate(self, sku: str, shop_url: str) -> None: ...
```

---

#### `LocationResolverPort`

Protocol for resolving inventory location.

```python
class LocationResolverPort(Protocol):
    def resolve(self, explicit_location: str | None = None) -> str: ...
```

---

### Cache Adapters

#### `JsonFileCacheAdapter`

File-based cache with filelock for concurrent access (safe for network shares).

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cache_path` | `Path` | *required* | Path to JSON cache file |
| `lock_timeout` | `float` | `10.0` | Filelock timeout in seconds |

```python
from pathlib import Path
from lib_shopify_graphql import JsonFileCacheAdapter

cache = JsonFileCacheAdapter(
    Path("/var/cache/shopify/sku_cache.json"),
    lock_timeout=15.0,
)

cache.set("key", "value", ttl=3600)  # Expires in 1 hour
cache.get("key")  # "value"
cache.delete("key")
cache.clear()
```

---

#### `MySQLCacheAdapter`

MySQL-based cache for distributed/multi-machine environments.

**Automatic database and table creation**: On first use, the adapter creates the database (if `auto_create_database=True`) and cache table automatically.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"localhost"` | MySQL server hostname |
| `port` | `int` | `3306` | MySQL server port |
| `user` | `str` | *required* | MySQL username |
| `password` | `str` | *required* | MySQL password |
| `database` | `str` | *required* | Database name (created if needed) |
| `table_name` | `str` | `"sku_cache"` | Cache table name |
| `connect_timeout` | `int` | `10` | Connection timeout in seconds |
| `auto_create_database` | `bool` | `True` | Create database if not exists |

**Class Methods:**

| Method | Description |
|--------|-------------|
| `from_url(connection_string, ...)` | Create from connection URL |

```python
from lib_shopify_graphql import MySQLCacheAdapter

# From connection URL (recommended)
cache = MySQLCacheAdapter.from_url(
    "mysql://shopify_app:secret@localhost:3306/shopify_cache",
    table_name="token_cache",
    auto_create_database=True,
)

# From parameters
cache = MySQLCacheAdapter(
    host="localhost",
    port=3306,
    user="shopify_app",
    password="secret",
    database="shopify_cache",
    table_name="sku_cache",
)

cache.set("key", "value", ttl=86400)
cache.get("key")
cache.cleanup_expired()  # Remove expired entries
```

**Connection String Format:**
```
mysql://user:password@host:port/database
```

**Requires**: `pip install lib_shopify_graphql[mysql]` for MySQL support.

---

#### `CachedTokenProvider`

Token provider that caches OAuth tokens to reduce authentication requests.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cache` | `CachePort` | *required* | Cache adapter |
| `delegate` | `TokenProviderPort` | *required* | Underlying token provider |
| `refresh_margin` | `int` | `300` | Refresh token this many seconds before expiration |

```python
from lib_shopify_graphql import (
    CachedTokenProvider, JsonFileCacheAdapter,
    create_cached_token_provider,
)
from lib_shopify_graphql.adapters import ShopifyTokenProvider

# Using factory function (recommended)
cache = JsonFileCacheAdapter(Path("/var/cache/shopify/token_cache.json"))
token_provider = create_cached_token_provider(cache=cache)

# Direct instantiation
token_provider = CachedTokenProvider(
    cache=cache,
    delegate=ShopifyTokenProvider(),
    refresh_margin=300,
)

# Use with login
session = login(credentials, token_provider=token_provider)
```

---

#### `CachedSKUResolver`

SKU resolver with cache-first, Shopify-fallback strategy.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cache` | `CachePort` | *required* | Cache adapter |
| `graphql_client` | `GraphQLClientPort` | *required* | GraphQL client |
| `cache_ttl` | `int` | `2592000` | Cache TTL in seconds (30 days) |

```python
from lib_shopify_graphql import CachedSKUResolver, JsonFileCacheAdapter

cache = JsonFileCacheAdapter(Path("/var/cache/shopify/sku_cache.json"))
# Note: graphql_client is obtained from session.graphql_client
sku_resolver = CachedSKUResolver(
    cache=cache,
    graphql_client=session.graphql_client,
    cache_ttl=86400,
)

# Use with update functions
update_variant(
    session, "SKU-12345", update,
    sku_resolver=sku_resolver,
)
```

---

#### `LocationResolver`

Location resolver with fallback chain: explicit -> config -> primary location.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `graphql_client` | `GraphQLClientPort` | *required* | GraphQL client |
| `default_location_id` | `str \| None` | `None` | Configured default location |

```python
from lib_shopify_graphql import LocationResolver

location_resolver = LocationResolver(
    graphql_client=session.graphql_client,
    default_location_id="gid://shopify/Location/123",  # From config
)

# Use with inventory functions
set_inventory(
    session, "SKU-12345", 100,
    location_resolver=location_resolver,
)
```

---

#### `get_default_adapters()`

Get the singleton default adapter bundle.

**Returns:** `AdapterBundle` with Shopify SDK implementations.

```python
from lib_shopify_graphql import get_default_adapters

adapters = get_default_adapters()
# Returns same instance on subsequent calls
```

---

