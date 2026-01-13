"""Request and result models for Shopify operations.

This module contains models for:
    - Update request/result models
    - Inventory models
    - Pagination models
    - Metafield deletion models
    - GraphQL response models for typed parsing
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from ._entities import Product, ProductVariant
from ._mutations import ProductUpdate, VariantUpdate


class VariantUpdateRequest(BaseModel):
    """Request to update a variant with flexible identifier.

    Either ``variant_id`` or ``sku`` must be provided to identify the variant.

    Attributes:
        variant_id: Variant GID or numeric ID.
        sku: SKU (resolved to GID via cache/Shopify lookup).
        update: Fields to update.
        location_id: Optional location override for inventory operations.

    Example:
        >>> from decimal import Decimal
        >>> from lib_shopify_graphql import VariantUpdate, VariantUpdateRequest
        >>> # Update by SKU
        >>> req = VariantUpdateRequest(
        ...     sku="ABC-123",
        ...     update=VariantUpdate(price=Decimal("29.99")),
        ... )
        >>> # Update by GID
        >>> req = VariantUpdateRequest(
        ...     variant_id="gid://shopify/ProductVariant/123456",
        ...     update=VariantUpdate(barcode="123456789012"),
        ... )
    """

    model_config = ConfigDict(frozen=True)

    variant_id: str | None = None
    sku: str | None = None
    update: VariantUpdate
    location_id: str | None = None

    @model_validator(mode="after")
    def require_identifier(self) -> Self:
        """Validate that at least one identifier is provided."""
        if not self.variant_id and not self.sku:
            msg = "Either variant_id or sku must be provided"
            raise ValueError(msg)
        return self


class ProductUpdateRequest(BaseModel):
    """Request to update a product.

    Attributes:
        product_id: Product GID or numeric ID.
        update: Fields to update.
    """

    model_config = ConfigDict(frozen=True)

    product_id: str
    update: ProductUpdate


class UpdateSuccess(BaseModel):
    """Result of a successful update operation.

    Attributes:
        identifier: The GID or SKU used to identify the resource.
        variant: Updated variant data (if variant update).
        product: Updated product data (if product update).
    """

    model_config = ConfigDict(frozen=True)

    identifier: str
    variant: ProductVariant | None = None
    product: Product | None = None


class UpdateFailure(BaseModel):
    """Result of a failed update operation.

    Attributes:
        identifier: The GID or SKU that failed.
        error: Human-readable error message.
        error_code: Shopify error code (if available).
        field: Field that caused the error (if known).
    """

    model_config = ConfigDict(frozen=True)

    identifier: str
    error: str
    error_code: str | None = None
    field: str | None = None


class BulkUpdateResult(BaseModel):
    """Result of a bulk update operation.

    Attributes:
        succeeded: List of successful updates.
        failed: List of failed updates.

    Example:
        >>> result = update_variants_bulk(session, product_id, requests)  # doctest: +SKIP
        >>> logger.info("Bulk update", extra={"updated": result.success_count})  # doctest: +SKIP
        >>> for failure in result.failed:  # doctest: +SKIP
        ...     logger.warning("Failed", extra={"id": failure.identifier})  # doctest: +SKIP
    """

    model_config = ConfigDict(frozen=True)

    succeeded: list[UpdateSuccess] = Field(default_factory=list[UpdateSuccess])
    failed: list[UpdateFailure] = Field(default_factory=list[UpdateFailure])

    @property
    def success_count(self) -> int:
        """Number of successful updates."""
        return len(self.succeeded)

    @property
    def failure_count(self) -> int:
        """Number of failed updates."""
        return len(self.failed)

    @property
    def all_succeeded(self) -> bool:
        """Whether all updates succeeded."""
        return len(self.failed) == 0


class InventoryLevel(BaseModel):
    """Inventory level at a specific location.

    Attributes:
        inventory_item_id: Shopify GID for the inventory item.
        location_id: Shopify GID for the location.
        available: Available quantity at this location. May be None if the
            operation doesn't return the actual quantity (e.g., adjust_inventory).
        updated_at: When the inventory was last updated.
    """

    model_config = ConfigDict(frozen=True)

    inventory_item_id: str
    location_id: str
    available: int | None = None
    updated_at: datetime | None = None


# =============================================================================
# Pagination Models
# =============================================================================


class PageInfo(BaseModel):
    """Pagination cursor information from Shopify GraphQL connections.

    Used with cursor-based pagination to navigate through large result sets.

    Attributes:
        has_next_page: Whether there are more items after the current page.
        has_previous_page: Whether there are items before the current page.
        start_cursor: Cursor pointing to the first item in the current page.
        end_cursor: Cursor pointing to the last item in the current page.

    Example:
        >>> page = PageInfo(has_next_page=True, end_cursor="abc123")
        >>> page.has_next_page
        True
    """

    model_config = ConfigDict(frozen=True)

    has_next_page: bool
    has_previous_page: bool = False
    start_cursor: str | None = None
    end_cursor: str | None = None


class ProductConnection(BaseModel):
    """Paginated product list result from Shopify GraphQL.

    Represents a page of products with pagination metadata.

    Attributes:
        products: List of products in the current page.
        page_info: Pagination cursor information.
        total_count: Total number of products matching the query (if available).

    Example:
        >>> result = list_products(session, first=50)  # doctest: +SKIP
        >>> for product in result.products:  # doctest: +SKIP
        ...     print(product.title)  # doctest: +SKIP
        >>> if result.page_info.has_next_page:  # doctest: +SKIP
        ...     next_page = list_products(session, after=result.page_info.end_cursor)  # doctest: +SKIP
    """

    model_config = ConfigDict(frozen=True)

    products: list[Product] = Field(default_factory=list[Product])
    page_info: PageInfo
    total_count: int | None = None


# =============================================================================
# Metafield Deletion Models
# =============================================================================


class MetafieldIdentifier(BaseModel):
    """Identifies a metafield for deletion.

    Metafields are uniquely identified by owner + namespace + key.

    Attributes:
        owner_id: Owner GID (e.g., 'gid://shopify/Product/123' or
            'gid://shopify/ProductVariant/456').
        namespace: Metafield namespace (e.g., 'custom', 'inventory').
        key: Metafield key within the namespace.

    Example:
        >>> identifier = MetafieldIdentifier(
        ...     owner_id="gid://shopify/Product/123",
        ...     namespace="custom",
        ...     key="warranty_months",
        ... )
        >>> identifier.namespace
        'custom'
    """

    model_config = ConfigDict(frozen=True)

    owner_id: str = Field(
        ...,
        description="Owner GID (Product, Variant, etc.)",
    )
    namespace: str = Field(
        ...,
        min_length=1,
        description="Metafield namespace",
    )
    key: str = Field(
        ...,
        min_length=1,
        description="Metafield key within the namespace",
    )


class MetafieldDeleteFailure(BaseModel):
    """A failed metafield deletion.

    Attributes:
        identifier: The metafield that failed to delete.
        error: Human-readable error message.
        error_code: Shopify error code (if available).

    Example:
        >>> failure = MetafieldDeleteFailure(
        ...     identifier=MetafieldIdentifier(
        ...         owner_id="gid://shopify/Product/123",
        ...         namespace="custom",
        ...         key="invalid_field",
        ...     ),
        ...     error="Metafield not found",
        ...     error_code="NOT_FOUND",
        ... )
        >>> failure.error_code
        'NOT_FOUND'
    """

    model_config = ConfigDict(frozen=True)

    identifier: MetafieldIdentifier
    error: str
    error_code: str | None = None


class MetafieldDeleteResult(BaseModel):
    """Result of bulk metafield deletion.

    Attributes:
        deleted: List of successfully deleted metafield identifiers.
        failed: List of failed deletions with error details.

    Example:
        >>> result = delete_metafields(session, identifiers)  # doctest: +SKIP
        >>> logger.info(
        ...     "Deletion complete",
        ...     extra={"deleted": result.deleted_count, "failed": result.failed_count},
        ... )  # doctest: +SKIP
    """

    model_config = ConfigDict(frozen=True)

    deleted: list[MetafieldIdentifier] = Field(default_factory=list[MetafieldIdentifier])
    failed: list[MetafieldDeleteFailure] = Field(default_factory=list[MetafieldDeleteFailure])

    @property
    def deleted_count(self) -> int:
        """Number of successfully deleted metafields."""
        return len(self.deleted)

    @property
    def failed_count(self) -> int:
        """Number of failed deletions."""
        return len(self.failed)

    @property
    def all_succeeded(self) -> bool:
        """Whether all deletions succeeded."""
        return len(self.failed) == 0


# =============================================================================
# Product Lifecycle Models
# =============================================================================


class DuplicateProductResult(BaseModel):
    """Result of duplicating a product.

    Attributes:
        new_product: The newly created duplicate product.
        original_product_id: GID of the source product that was duplicated.

    Example:
        >>> result = duplicate_product(session, product_id, "Copy of Product")  # doctest: +SKIP
        >>> logger.info(
        ...     "Product duplicated",
        ...     extra={"original": result.original_product_id, "new": result.new_product.id},
        ... )  # doctest: +SKIP
    """

    model_config = ConfigDict(frozen=True)

    new_product: Product
    original_product_id: str


class DeleteProductResult(BaseModel):
    """Result of deleting a product.

    WARNING: Product deletion is irreversible. All variants, inventory,
    and associated data are permanently removed.

    Attributes:
        deleted_product_id: GID of the deleted product.
        success: Always True if no exception was raised.

    Example:
        >>> result = delete_product(session, product_id)  # doctest: +SKIP
        >>> logger.info("Product deleted", extra={"id": result.deleted_product_id})  # doctest: +SKIP
    """

    model_config = ConfigDict(frozen=True)

    deleted_product_id: str
    success: bool = True


# =============================================================================
# GraphQL Response Models (Internal)
# =============================================================================


class UserErrorData(BaseModel):
    """Parsed user error from GraphQL mutation response.

    Represents a single userError entry from mutation responses,
    providing typed access to error details.

    Attributes:
        field: Path to the field that caused the error (may be empty).
            Shopify returns field names as strings and array indices may be
            integers - these are normalized to strings during validation.
        message: Human-readable error message.
        code: Shopify error code (if available).
    """

    model_config = ConfigDict(frozen=True)

    field: list[str] = Field(default_factory=list[str])
    message: str = "Unknown error"
    code: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_field_to_strings(  # type: ignore[reportUnknownVariableType]
        cls, data: Any
    ) -> Any:  # noqa: ANN401
        """Convert integer indices in field path to strings.

        Shopify may return field paths like ["variants", 0, "price"] with integer
        array indices. This validator normalizes them to strings.
        """
        if not isinstance(data, dict) or "field" not in data:
            return data  # type: ignore[reportUnknownVariableType]
        field_value: list[Any] = data["field"]  # type: ignore[reportUnknownVariableType]
        if not isinstance(field_value, list):
            return data  # type: ignore[reportUnknownVariableType]
        # Don't mutate input, create a new dict with normalized field
        result: dict[str, Any] = dict(data)  # type: ignore[reportUnknownArgumentType]
        # Convert all items to strings (handles both str and int indices)
        str_field: list[str] = [str(item) for item in cast(list[Any], field_value)]
        result["field"] = str_field
        return result


class GraphQLErrorLocation(BaseModel):
    """Location in a GraphQL query where an error occurred.

    Attributes:
        line: Line number in the query (1-based).
        column: Column number in the query (1-based).
    """

    model_config = ConfigDict(frozen=True)

    line: int = 0
    column: int = 0


class GraphQLErrorExtensions(BaseModel):
    """Additional metadata from GraphQL errors.

    Shopify includes extension data with errors for debugging.
    This model captures common fields while allowing extra fields.

    Attributes:
        code: Error code from Shopify.
        documentation: Link to documentation.
        request_id: Shopify request ID for support.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    code: str | None = None
    documentation: str | None = None
    request_id: str | None = Field(default=None, alias="requestId")


class GraphQLErrorData(BaseModel):
    """Parsed GraphQL error from API response.

    Represents a single error entry from the GraphQL errors array,
    providing typed access to error details.

    Attributes:
        message: Human-readable error message.
        locations: Where the error occurred in the query.
        path: Path to the field that caused the error.
        extensions: Additional error metadata from Shopify.
    """

    model_config = ConfigDict(frozen=True)

    message: str = "Unknown error"
    locations: list[GraphQLErrorLocation] | None = None
    path: list[str | int] | None = None
    extensions: GraphQLErrorExtensions | None = None


class ProductUpdateMutationProduct(BaseModel):
    """Product data returned from productUpdate mutation.

    This is a minimal model for the mutation response - it only
    contains the `id` field since we re-fetch the full product
    after mutation to get complete data.

    Attributes:
        id: Product GID.
    """

    model_config = ConfigDict(frozen=True)

    id: str


class ProductUpdateMutationData(BaseModel):
    """Parsed productUpdate mutation result.

    Attributes:
        product: Updated product data (or None if mutation failed).
        user_errors: List of user errors from the mutation.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    product: ProductUpdateMutationProduct | None = None
    user_errors: list[UserErrorData] = Field(default_factory=list[UserErrorData], alias="userErrors")


class ProductUpdateResponseData(BaseModel):
    """Data wrapper for productUpdate mutation response.

    Attributes:
        product_update: The productUpdate mutation result.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    product_update: ProductUpdateMutationData | None = Field(default=None, alias="productUpdate")


class ProductUpdateResponse(BaseModel):
    """Full response from productUpdate mutation.

    Provides typed access to both GraphQL errors and mutation result.

    Attributes:
        errors: GraphQL-level errors (query/authentication issues).
        data: Mutation result data (may be None on error).
    """

    model_config = ConfigDict(frozen=True)

    errors: list[GraphQLErrorData] | None = None
    data: ProductUpdateResponseData | None = None

    @property
    def has_graphql_errors(self) -> bool:
        """Check if response contains GraphQL-level errors."""
        return self.errors is not None and len(self.errors) > 0

    @property
    def mutation_data(self) -> ProductUpdateMutationData | None:
        """Get productUpdate mutation data."""
        if self.data is None:
            return None
        return self.data.product_update

    @property
    def has_user_errors(self) -> bool:
        """Check if mutation returned user errors."""
        mutation = self.mutation_data
        return mutation is not None and len(mutation.user_errors) > 0


class SelectedOptionData(BaseModel):
    """Selected option name/value pair from mutation response.

    Attributes:
        name: Option name (e.g., "Size", "Color").
        value: Option value (e.g., "Large", "Blue").
    """

    model_config = ConfigDict(frozen=True)

    name: str
    value: str


class VariantMutationResult(BaseModel):
    """Variant data returned from bulk update mutation.

    Contains the fields returned by the mutation for each updated variant.
    Structure matches the productVariantsBulkUpdate response.

    Attributes:
        id: Variant GID.
        title: Variant title.
        sku: SKU (stock keeping unit).
        barcode: Barcode value (optional).
        price: Current price as string.
        compare_at_price: Compare-at price as string (optional).
        inventory_policy: Inventory policy (DENY or CONTINUE).
        taxable: Whether variant is taxable.
        selected_options: List of selected option name/value pairs.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str
    title: str = ""
    sku: str | None = None
    barcode: str | None = None
    price: str = "0"
    compare_at_price: str | None = Field(default=None, alias="compareAtPrice")
    inventory_policy: str | None = Field(default=None, alias="inventoryPolicy")
    taxable: bool = True
    selected_options: list[SelectedOptionData] = Field(default_factory=list[SelectedOptionData], alias="selectedOptions")


class VariantsBulkUpdateMutationData(BaseModel):
    """Parsed productVariantsBulkUpdate mutation result.

    Attributes:
        product_variants: List of updated variant data.
        user_errors: List of user errors from the mutation.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    product_variants: list[VariantMutationResult] = Field(default_factory=list[VariantMutationResult], alias="productVariants")
    user_errors: list[UserErrorData] = Field(default_factory=list[UserErrorData], alias="userErrors")


class VariantsBulkUpdateResponseData(BaseModel):
    """Data wrapper for productVariantsBulkUpdate mutation response.

    Attributes:
        product_variants_bulk_update: The mutation result.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    product_variants_bulk_update: VariantsBulkUpdateMutationData | None = Field(default=None, alias="productVariantsBulkUpdate")


class VariantsBulkUpdateResponse(BaseModel):
    """Full response from productVariantsBulkUpdate mutation.

    Provides typed access to both GraphQL errors and mutation result.

    Attributes:
        errors: GraphQL-level errors (query/authentication issues).
        data: Mutation result data (may be None on error).
    """

    model_config = ConfigDict(frozen=True)

    errors: list[GraphQLErrorData] | None = None
    data: VariantsBulkUpdateResponseData | None = None

    @property
    def has_graphql_errors(self) -> bool:
        """Check if response contains GraphQL-level errors."""
        return self.errors is not None and len(self.errors) > 0

    @property
    def mutation_data(self) -> VariantsBulkUpdateMutationData | None:
        """Get productVariantsBulkUpdate mutation data."""
        if self.data is None:
            return None
        return self.data.product_variants_bulk_update

    @property
    def has_user_errors(self) -> bool:
        """Check if mutation returned user errors."""
        mutation = self.mutation_data
        return mutation is not None and len(mutation.user_errors) > 0


# =============================================================================
# Truncation Analysis Models
# =============================================================================


class FieldTruncationInfo(BaseModel):
    """Truncation status for a single product field.

    Attributes:
        count: Number of items returned.
        limit: Configured limit for this field.
        truncated: Whether this field was truncated.
        config_key: Config key name to increase limit.
        env_var: Environment variable to increase limit.
        cost_warning: Optional cost impact warning.
    """

    model_config = ConfigDict(frozen=True)

    count: int
    limit: int
    truncated: bool
    config_key: str
    env_var: str
    cost_warning: str | None = None


class TruncationFields(BaseModel):
    """Truncation status for all product fields.

    Attributes:
        images: Image field truncation info.
        media: Media field truncation info.
        metafields: Metafield truncation info.
        variants: Variant truncation info.
        variant_metafields: Variant metafield truncation info.
    """

    model_config = ConfigDict(frozen=True)

    images: FieldTruncationInfo
    media: FieldTruncationInfo
    metafields: FieldTruncationInfo
    variants: FieldTruncationInfo
    variant_metafields: FieldTruncationInfo


class TruncationInfo(BaseModel):
    """Complete truncation analysis result for a product.

    Returned by get_truncation_info() to provide structured
    information about which fields were truncated.

    Attributes:
        product_id: Product GID.
        product_title: Product title.
        truncated: True if any field was truncated.
        fields: Per-field truncation details.
    """

    model_config = ConfigDict(frozen=True)

    product_id: str
    product_title: str
    truncated: bool
    fields: TruncationFields


__all__ = [
    # Update request/result
    "BulkUpdateResult",
    "ProductUpdateRequest",
    "UpdateFailure",
    "UpdateSuccess",
    "VariantUpdateRequest",
    # Inventory
    "InventoryLevel",
    # Pagination
    "PageInfo",
    "ProductConnection",
    # Metafield deletion
    "MetafieldDeleteFailure",
    "MetafieldDeleteResult",
    "MetafieldIdentifier",
    # Product lifecycle
    "DeleteProductResult",
    "DuplicateProductResult",
    # Truncation analysis
    "FieldTruncationInfo",
    "TruncationFields",
    "TruncationInfo",
]
