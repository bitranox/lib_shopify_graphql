"""Partial update models for Shopify mutations.

This module contains models for partial updates with UNSET sentinel support:
    - MetafieldInput: Input for creating/updating metafields
    - VariantUpdate: Partial update for variant fields
    - ProductUpdate: Partial update for product fields
    - ProductCreate: Input for creating new products
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from ._enums import InventoryPolicy, MetafieldType, ProductStatus, WeightUnit
from ._internal import UNSET, Updatable


class MetafieldInput(BaseModel):
    """Input for creating or updating a metafield.

    Used in product and variant update operations.

    Attributes:
        namespace: Container grouping metafields (e.g., 'custom', 'inventory').
        key: Unique identifier within the namespace.
        value: Data stored as string.
        type: Data type as MetafieldType enum.
    """

    model_config = ConfigDict(frozen=True)

    namespace: str
    key: str
    value: str
    type: MetafieldType


class VariantUpdate(BaseModel):
    """Partial update for product variant fields.

    All fields default to UNSET, meaning they won't be sent to Shopify.
    Set a field to a value to update it, or to None to clear it.

    Field states:
        - ``UNSET`` (default): Don't update this field
        - ``None``: Clear this field (set to null on Shopify)
        - ``value``: Update to this value

    Example:
        >>> from decimal import Decimal
        >>> from lib_shopify_graphql import UNSET, VariantUpdate
        >>> # Update price only, leave other fields unchanged
        >>> update = VariantUpdate(price=Decimal("29.99"))
        >>> update.price
        Decimal('29.99')
        >>> update.barcode is UNSET
        True
        >>> # Clear compare_at_price (remove sale price)
        >>> update = VariantUpdate(compare_at_price=None)
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # Pricing
    price: Updatable[Decimal] = UNSET
    compare_at_price: Updatable[Decimal] = UNSET
    cost: Updatable[Decimal] = UNSET

    # Identification
    sku: Updatable[str] = UNSET
    barcode: Updatable[str] = UNSET

    # Inventory
    inventory_policy: Updatable[InventoryPolicy] = UNSET

    # Physical properties
    weight: Updatable[Decimal] = UNSET
    weight_unit: Updatable[WeightUnit] = UNSET
    requires_shipping: Updatable[bool] = UNSET

    # Tax
    taxable: Updatable[bool] = UNSET
    tax_code: Updatable[str] = UNSET

    # Fulfillment
    fulfillment_service: Updatable[str] = UNSET

    # Variant options (for changing variant option values)
    option1: Updatable[str] = UNSET
    option2: Updatable[str] = UNSET
    option3: Updatable[str] = UNSET

    # Media
    image_id: Updatable[str] = UNSET

    # Metafields
    metafields: Updatable[list[MetafieldInput]] = UNSET

    # Customs
    harmonized_system_code: Updatable[str] = UNSET
    country_code_of_origin: Updatable[str] = UNSET

    def is_field_set(self, field_name: str) -> bool:
        """Check if a field has been set (is not UNSET).

        Args:
            field_name: Name of the field to check.

        Returns:
            True if the field has a value (not UNSET).
        """
        return getattr(self, field_name, UNSET) is not UNSET

    def get_field_value(self, field_name: str) -> object:
        """Get the value of a field.

        Args:
            field_name: Name of the field to get.

        Returns:
            The field value, or UNSET if not set.
        """
        return getattr(self, field_name, UNSET)

    def get_set_fields(self) -> dict[str, object]:
        """Return only fields that are not UNSET.

        Note: This method is for adapter boundary conversion to GraphQL input.

        Returns:
            Dictionary of field names to values for fields that should be updated.
        """
        result: dict[str, object] = {}
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if value is not UNSET:
                result[field_name] = value
        return result


class ProductUpdate(BaseModel):
    """Partial update for product fields.

    All fields default to UNSET, meaning they won't be sent to Shopify.
    Set a field to a value to update it, or to None to clear it.

    Field states:
        - ``UNSET`` (default): Don't update this field
        - ``None``: Clear this field (set to null on Shopify)
        - ``value``: Update to this value

    Example:
        >>> from lib_shopify_graphql import UNSET, ProductUpdate, ProductStatus
        >>> # Update title and status only
        >>> update = ProductUpdate(
        ...     title="New Product Title",
        ...     status=ProductStatus.ACTIVE,
        ... )
        >>> update.title
        'New Product Title'
        >>> update.description_html is UNSET
        True
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # Basic info
    title: Updatable[str] = UNSET
    description_html: Updatable[str] = UNSET
    handle: Updatable[str] = UNSET

    # Categorization
    vendor: Updatable[str] = UNSET
    product_type: Updatable[str] = UNSET
    tags: Updatable[list[str]] = UNSET

    # Status
    status: Updatable[ProductStatus] = UNSET

    # SEO
    seo_title: Updatable[str] = UNSET
    seo_description: Updatable[str] = UNSET

    # Template
    template_suffix: Updatable[str] = UNSET

    # Gift card
    gift_card: Updatable[bool] = UNSET

    # Collections
    collections_to_join: Updatable[list[str]] = UNSET
    collections_to_leave: Updatable[list[str]] = UNSET

    # Category
    category: Updatable[str] = UNSET

    # Metafields
    metafields: Updatable[list[MetafieldInput]] = UNSET

    # Subscription
    requires_selling_plan: Updatable[bool] = UNSET

    def is_field_set(self, field_name: str) -> bool:
        """Check if a field has been set (is not UNSET).

        Args:
            field_name: Name of the field to check.

        Returns:
            True if the field has a value (not UNSET).
        """
        return getattr(self, field_name, UNSET) is not UNSET

    def get_field_value(self, field_name: str) -> object:
        """Get the value of a field.

        Args:
            field_name: Name of the field to get.

        Returns:
            The field value, or UNSET if not set.
        """
        return getattr(self, field_name, UNSET)

    def get_set_fields(self) -> dict[str, object]:
        """Return only fields that are not UNSET.

        Note: This method is for adapter boundary conversion to GraphQL input.

        Returns:
            Dictionary of field names to values for fields that should be updated.
        """
        result: dict[str, object] = {}
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if value is not UNSET:
                result[field_name] = value
        return result


class ProductCreate(BaseModel):
    """Input model for creating a new product.

    Only ``title`` is required. All other fields are optional and will use
    Shopify defaults if not provided.

    Unlike ``ProductUpdate``, this model uses ``None`` for optional fields
    rather than ``UNSET``, since all provided values should be sent on creation.

    Example:
        >>> from lib_shopify_graphql import ProductCreate, ProductStatus
        >>> # Create a minimal product
        >>> product = ProductCreate(title="My New Product")
        >>> # Create a product with more fields
        >>> product = ProductCreate(
        ...     title="Premium Widget",
        ...     description_html="<p>A high-quality widget.</p>",
        ...     vendor="WidgetCo",
        ...     product_type="Widgets",
        ...     status=ProductStatus.DRAFT,
        ...     tags=["premium", "widget"],
        ... )
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # Required
    title: str

    # Optional - basic info
    description_html: str | None = None
    handle: str | None = None

    # Optional - categorization
    vendor: str | None = None
    product_type: str | None = None
    tags: list[str] | None = None

    # Optional - status (defaults to DRAFT on Shopify if not specified)
    status: ProductStatus | None = None

    # Optional - SEO
    seo_title: str | None = None
    seo_description: str | None = None


__all__ = [
    "MetafieldInput",
    "ProductCreate",
    "ProductUpdate",
    "VariantUpdate",
]
