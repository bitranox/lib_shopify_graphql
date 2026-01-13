"""GraphQL mutation strings for Shopify Admin API.

This module contains all GraphQL mutation definitions for updating
products, variants, inventory, and media.

Mutations:
    - :data:`PRODUCT_CREATE_MUTATION`: Create a new product.
    - :data:`PRODUCT_UPDATE_MUTATION`: Update product fields.
    - :data:`PRODUCT_DUPLICATE_MUTATION`: Duplicate an existing product.
    - :data:`PRODUCT_DELETE_MUTATION`: Delete a product.
    - :data:`PRODUCT_VARIANTS_BULK_UPDATE_MUTATION`: Update multiple variants.
    - :data:`INVENTORY_SET_QUANTITIES_MUTATION`: Set absolute inventory.
    - :data:`INVENTORY_ADJUST_QUANTITIES_MUTATION`: Adjust inventory delta.
    - :data:`METAFIELDS_DELETE_MUTATION`: Delete metafields from resources.
    - :data:`STAGED_UPLOADS_CREATE_MUTATION`: Create staged upload targets.
    - :data:`PRODUCT_CREATE_MEDIA_MUTATION`: Create product images/media.
    - :data:`PRODUCT_UPDATE_MEDIA_MUTATION`: Update media metadata.
    - :data:`PRODUCT_DELETE_MEDIA_MUTATION`: Delete product media.
    - :data:`PRODUCT_REORDER_MEDIA_MUTATION`: Reorder product media.
"""

from __future__ import annotations

# =============================================================================
# Product Mutations
# =============================================================================


PRODUCT_CREATE_MUTATION = """
mutation productCreate($input: ProductInput!) {
    productCreate(input: $input) {
        product {
            id
            title
            handle
            status
            descriptionHtml
            vendor
            productType
            tags
            createdAt
            updatedAt
            variants(first: 100) {
                nodes {
                    id
                    sku
                    title
                    price
                    inventoryQuantity
                }
            }
        }
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to create a new product.

Input structure:
```graphql
input ProductInput {
    title: String!  # Required: Product title
    descriptionHtml: String
    handle: String
    vendor: String
    productType: String
    tags: [String!]
    status: ProductStatus  # ACTIVE, ARCHIVED, DRAFT
    seo: SEOInput
}
```

Returns the created product with its default variant.
"""


PRODUCT_UPDATE_MUTATION = """
mutation ProductUpdate($input: ProductInput!) {
    productUpdate(input: $input) {
        product {
            id
            title
            handle
            status
            vendor
            productType
            descriptionHtml
            tags
            templateSuffix
            seo {
                title
                description
            }
            createdAt
            updatedAt
        }
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to update product fields.

Input structure:
```graphql
input ProductInput {
    id: ID!  # Required: Product GID
    title: String
    descriptionHtml: String
    handle: String
    vendor: String
    productType: String
    tags: [String!]
    status: ProductStatus  # ACTIVE, ARCHIVED, DRAFT
    seo: SEOInput
    templateSuffix: String
    giftCard: Boolean
    requiresSellingPlan: Boolean
    metafields: [MetafieldInput!]
    collectionsToJoin: [ID!]
    collectionsToLeave: [ID!]
    category: ID
}
```
"""


PRODUCT_VARIANTS_BULK_UPDATE_MUTATION = """
mutation ProductVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
    productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        product {
            id
            title
        }
        productVariants {
            id
            title
            sku
            barcode
            price
            compareAtPrice
            inventoryPolicy
            taxable
            selectedOptions {
                name
                value
            }
        }
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to update multiple product variants.

Input structure:
```graphql
input ProductVariantsBulkInput {
    id: ID!  # Required: Variant GID
    price: Money
    compareAtPrice: Money
    sku: String
    barcode: String
    inventoryPolicy: ProductVariantInventoryPolicy
    taxable: Boolean
    taxCode: String
    weight: Float
    weightUnit: WeightUnit
    requiresShipping: Boolean
    harmonizedSystemCode: String
    countryCodeOfOrigin: CountryCode
    inventoryItem: InventoryItemInput
    metafields: [MetafieldInput!]
    mediaId: ID
    optionValues: [VariantOptionValueInput!]
}
```
"""


PRODUCT_DUPLICATE_MUTATION = """
mutation productDuplicate($productId: ID!, $newTitle: String!, $includeImages: Boolean, $newStatus: ProductStatus) {
    productDuplicate(
        productId: $productId
        newTitle: $newTitle
        includeImages: $includeImages
        newStatus: $newStatus
    ) {
        newProduct {
            id
            title
            handle
            status
            descriptionHtml
            vendor
            productType
            tags
            createdAt
            updatedAt
            variants(first: 100) {
                nodes {
                    id
                    sku
                    title
                    price
                    inventoryQuantity
                }
            }
        }
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to duplicate an existing product.

Args:
    productId: ID of the product to duplicate (GID format).
    newTitle: Title for the duplicated product.
    includeImages: Whether to copy product images (default: false).
    newStatus: Status for new product (ACTIVE, DRAFT, ARCHIVED).

Returns the newly created product with all its variants.
"""


PRODUCT_DELETE_MUTATION = """
mutation productDelete($input: ProductDeleteInput!) {
    productDelete(input: $input) {
        deletedProductId
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to delete a product permanently.

WARNING: This operation is irreversible. All variants, inventory,
and associated data will be deleted.

Input structure:
```graphql
input ProductDeleteInput {
    id: ID!  # Required: Product GID to delete
}
```

Returns the ID of the deleted product.
"""


# =============================================================================
# Inventory Mutations
# =============================================================================


INVENTORY_SET_QUANTITIES_MUTATION = """
mutation InventorySetQuantities($input: InventorySetQuantitiesInput!) {
    inventorySetQuantities(input: $input) {
        inventoryAdjustmentGroup {
            createdAt
            reason
            referenceDocumentUri
            changes {
                name
                delta
            }
        }
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to set absolute inventory quantity.

Input structure:
```graphql
input InventorySetQuantitiesInput {
    name: String!  # Name for the change (e.g., "available")
    reason: String!  # Reason for the change
    ignoreCompareQuantity: Boolean  # Skip optimistic locking
    quantities: [InventoryQuantityInput!]!
}

input InventoryQuantityInput {
    inventoryItemId: ID!
    locationId: ID!
    quantity: Int!
}
```

Common reasons:
- "correction" - Manual stock count correction
- "received" - Stock received from supplier
- "damaged" - Stock damaged and removed
- "shrinkage" - Stock loss due to theft/loss
- "promotion_or_donation" - Given away
"""


INVENTORY_ADJUST_QUANTITIES_MUTATION = """
mutation InventoryAdjustQuantities($input: InventoryAdjustQuantitiesInput!) {
    inventoryAdjustQuantities(input: $input) {
        inventoryAdjustmentGroup {
            createdAt
            reason
            changes {
                name
                delta
            }
        }
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to adjust inventory by a delta.

Input structure:
```graphql
input InventoryAdjustQuantitiesInput {
    name: String!  # Name for the change (e.g., "available")
    reason: String!  # Reason for the change
    changes: [InventoryAdjustItemInput!]!
}

input InventoryAdjustItemInput {
    inventoryItemId: ID!
    locationId: ID!
    delta: Int!  # Positive to add, negative to remove
}
```
"""


# =============================================================================
# Helper Query for Inventory Item ID
# =============================================================================


VARIANT_INVENTORY_ITEM_QUERY = """
query VariantInventoryItem($id: ID!) {
    productVariant(id: $id) {
        id
        sku
        inventoryItem {
            id
            tracked
        }
    }
}
"""
"""GraphQL query to get inventory item ID for a variant.

Required before inventory mutations, as they use inventoryItemId not variantId.
"""


# =============================================================================
# Metafield Mutations
# =============================================================================


METAFIELDS_DELETE_MUTATION = """
mutation metafieldsDelete($metafields: [MetafieldIdentifierInput!]!) {
    metafieldsDelete(metafields: $metafields) {
        deletedMetafields {
            ownerId
            namespace
            key
        }
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to delete metafields from resources.

Input structure:
```graphql
input MetafieldIdentifierInput {
    ownerId: ID!       # Owner GID (Product, Variant, etc.)
    namespace: String! # Metafield namespace
    key: String!       # Metafield key
}
```

The mutation is idempotent - deleting a non-existent metafield does not error.
Returns the list of successfully deleted metafields and any user errors.
"""


# =============================================================================
# Media/Image Mutations
# =============================================================================


STAGED_UPLOADS_CREATE_MUTATION = """
mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
    stagedUploadsCreate(input: $input) {
        stagedTargets {
            url
            resourceUrl
            parameters {
                name
                value
            }
        }
        userErrors {
            field
            message
        }
    }
}
"""
"""GraphQL mutation to create staged upload targets for file uploads.

This is step 1 of the 2-step upload process for local files.
After getting the staged target, upload the file to the URL,
then use resourceUrl in productCreateMedia.

Input structure:
```graphql
input StagedUploadInput {
    filename: String!      # Original filename
    mimeType: String!      # MIME type (image/jpeg, image/png, etc.)
    fileSize: String!      # File size in bytes as string
    resource: StagedUploadTargetGenerateUploadResource!  # IMAGE, VIDEO, etc.
}
```
"""


PRODUCT_CREATE_MEDIA_MUTATION = """
mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
    productCreateMedia(productId: $productId, media: $media) {
        media {
            id
            alt
            mediaContentType
            status
            ... on MediaImage {
                id
                image {
                    url
                    altText
                    width
                    height
                }
            }
        }
        mediaUserErrors {
            code
            field
            message
        }
        product {
            id
        }
    }
}
"""
"""GraphQL mutation to create media (images) for a product.

Input structure:
```graphql
input CreateMediaInput {
    alt: String                    # Alt text for the media
    mediaContentType: MediaContentType!  # IMAGE, VIDEO, etc.
    originalSource: String!        # URL of the media source
}
```

Note: For local file uploads, use the resourceUrl from stagedUploadsCreate.
"""


PRODUCT_UPDATE_MEDIA_MUTATION = """
mutation productUpdateMedia($productId: ID!, $media: [UpdateMediaInput!]!) {
    productUpdateMedia(productId: $productId, media: $media) {
        media {
            id
            alt
            mediaContentType
            ... on MediaImage {
                id
                image {
                    url
                    altText
                    width
                    height
                }
            }
        }
        mediaUserErrors {
            code
            field
            message
        }
        product {
            id
        }
    }
}
"""
"""GraphQL mutation to update media metadata (e.g., alt text).

Input structure:
```graphql
input UpdateMediaInput {
    id: ID!        # Media GID to update
    alt: String    # New alt text
}
```
"""


PRODUCT_DELETE_MEDIA_MUTATION = """
mutation productDeleteMedia($productId: ID!, $mediaIds: [ID!]!) {
    productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
        deletedMediaIds
        deletedProductImageIds
        mediaUserErrors {
            code
            field
            message
        }
        product {
            id
        }
    }
}
"""
"""GraphQL mutation to delete media from a product.

Args:
    productId: Product GID.
    mediaIds: List of media GIDs to delete.

Returns the deleted media IDs and any errors.
"""


PRODUCT_REORDER_MEDIA_MUTATION = """
mutation productReorderMedia($id: ID!, $moves: [MoveInput!]!) {
    productReorderMedia(id: $id, moves: $moves) {
        job {
            id
        }
        mediaUserErrors {
            code
            field
            message
        }
    }
}
"""
"""GraphQL mutation to reorder media on a product.

This operation is asynchronous - returns a job ID.

Input structure:
```graphql
input MoveInput {
    id: ID!             # Media GID to move
    newPosition: String!  # New 0-based position (UnsignedInt64 as string)
}
```
"""


__all__ = [
    "INVENTORY_ADJUST_QUANTITIES_MUTATION",
    "INVENTORY_SET_QUANTITIES_MUTATION",
    "METAFIELDS_DELETE_MUTATION",
    "PRODUCT_CREATE_MEDIA_MUTATION",
    "PRODUCT_CREATE_MUTATION",
    "PRODUCT_DELETE_MEDIA_MUTATION",
    "PRODUCT_DELETE_MUTATION",
    "PRODUCT_DUPLICATE_MUTATION",
    "PRODUCT_REORDER_MEDIA_MUTATION",
    "PRODUCT_UPDATE_MEDIA_MUTATION",
    "PRODUCT_UPDATE_MUTATION",
    "PRODUCT_VARIANTS_BULK_UPDATE_MUTATION",
    "STAGED_UPLOADS_CREATE_MUTATION",
    "VARIANT_INVENTORY_ITEM_QUERY",
]
