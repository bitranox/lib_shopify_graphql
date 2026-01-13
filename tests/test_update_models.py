"""Update model tests: verifying partial update behavior.

Tests for the partial update models covering:
- UNSET sentinel behavior
- VariantUpdate model
- ProductUpdate model
- Request and result models
- Sentinel field detection
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from lib_shopify_graphql.models import (
    UNSET,
    BulkUpdateResult,
    InventoryLevel,
    InventoryPolicy,
    MetafieldInput,
    MetafieldType,
    ProductStatus,
    ProductUpdate,
    UnsetType,
    UpdateFailure,
    UpdateSuccess,
    VariantUpdate,
    VariantUpdateRequest,
    WeightUnit,
)


# =============================================================================
# UnsetType Sentinel Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestUnsetTypeSingleton:
    """UnsetType is a singleton sentinel value."""

    def test_always_returns_same_instance(self) -> None:
        """All UnsetType instances are the same object."""
        instance1 = UnsetType()
        instance2 = UnsetType()

        assert instance1 is instance2

    def test_is_same_as_unset_constant(self) -> None:
        """New UnsetType() is the same as UNSET constant."""
        instance = UnsetType()

        assert instance is UNSET

    def test_repr_returns_unset(self) -> None:
        """repr(UNSET) returns 'UNSET'."""
        assert repr(UNSET) == "UNSET"

    def test_bool_is_false(self) -> None:
        """UNSET is falsy."""
        assert not UNSET
        assert bool(UNSET) is False


@pytest.mark.os_agnostic
class TestUnsetTypeImmutability:
    """UnsetType supports copy operations for Pydantic."""

    def test_copy_returns_same_instance(self) -> None:
        """copy(UNSET) returns UNSET."""
        import copy

        copied = copy.copy(UNSET)

        assert copied is UNSET

    def test_deepcopy_returns_same_instance(self) -> None:
        """deepcopy(UNSET) returns UNSET."""
        import copy

        deep_copied = copy.deepcopy(UNSET)

        assert deep_copied is UNSET


@pytest.mark.os_agnostic
class TestUnsetTypeComparison:
    """UNSET can be used in comparisons."""

    def test_is_comparison_works(self) -> None:
        """'is UNSET' works for checking if field is unset."""
        value = UNSET

        assert value is UNSET

    def test_is_not_none(self) -> None:
        """UNSET is not None."""
        assert UNSET is not None
        assert UNSET != None  # noqa: E711

    def test_distinguishes_from_none(self) -> None:
        """UNSET and None are different values."""
        value_unset: UnsetType | None = UNSET
        value_none: UnsetType | None = None

        assert value_unset is not value_none
        assert (value_unset is UNSET) and (value_none is None)


# =============================================================================
# VariantUpdate Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestVariantUpdateDefaults:
    """VariantUpdate fields default to UNSET."""

    def test_all_fields_default_to_unset(self) -> None:
        """All fields are UNSET when not specified."""
        update = VariantUpdate()

        assert update.price is UNSET
        assert update.compare_at_price is UNSET
        assert update.sku is UNSET
        assert update.barcode is UNSET
        assert update.inventory_policy is UNSET
        assert update.weight is UNSET
        assert update.taxable is UNSET

    def test_get_set_fields_returns_empty(self) -> None:
        """get_set_fields returns empty dict for default update."""
        update = VariantUpdate()

        result = update.get_set_fields()

        assert result == {}


@pytest.mark.os_agnostic
class TestVariantUpdateWithValues:
    """VariantUpdate stores provided values."""

    def test_stores_price(self) -> None:
        """Price value is stored."""
        update = VariantUpdate(price=Decimal("29.99"))

        assert update.price == Decimal("29.99")

    def test_stores_sku(self) -> None:
        """SKU value is stored."""
        update = VariantUpdate(sku="NEW-SKU-123")

        assert update.sku == "NEW-SKU-123"

    def test_stores_multiple_values(self) -> None:
        """Multiple values can be set."""
        update = VariantUpdate(
            price=Decimal("29.99"),
            barcode="1234567890123",
            taxable=True,
        )

        assert update.price == Decimal("29.99")
        assert update.barcode == "1234567890123"
        assert update.taxable is True

    def test_get_set_fields_returns_set_fields(self) -> None:
        """get_set_fields returns only fields that were set."""
        update = VariantUpdate(
            price=Decimal("29.99"),
            sku="NEW-SKU",
        )

        result = update.get_set_fields()

        assert "price" in result
        assert "sku" in result
        assert result["price"] == Decimal("29.99")
        assert result["sku"] == "NEW-SKU"
        assert "barcode" not in result


@pytest.mark.os_agnostic
class TestVariantUpdateWithNone:
    """VariantUpdate handles None for clearing fields."""

    def test_stores_none_for_clearing(self) -> None:
        """None is stored (different from UNSET)."""
        update = VariantUpdate(compare_at_price=None)

        assert update.compare_at_price is None
        assert update.compare_at_price is not UNSET

    def test_get_set_fields_includes_none(self) -> None:
        """get_set_fields includes fields set to None."""
        update = VariantUpdate(compare_at_price=None)

        result = update.get_set_fields()

        assert "compare_at_price" in result
        assert result["compare_at_price"] is None


@pytest.mark.os_agnostic
class TestVariantUpdateEnumFields:
    """VariantUpdate handles enum field values."""

    def test_stores_inventory_policy(self) -> None:
        """InventoryPolicy enum is stored."""
        update = VariantUpdate(inventory_policy=InventoryPolicy.CONTINUE)

        assert update.inventory_policy == InventoryPolicy.CONTINUE

    def test_stores_weight_unit(self) -> None:
        """WeightUnit enum is stored."""
        update = VariantUpdate(weight_unit=WeightUnit.POUNDS)

        assert update.weight_unit == WeightUnit.POUNDS


@pytest.mark.os_agnostic
class TestVariantUpdateImmutability:
    """VariantUpdate is frozen and cannot be modified."""

    def test_cannot_modify_price(self) -> None:
        """Attempting to modify price raises an error."""
        update = VariantUpdate(price=Decimal("29.99"))

        with pytest.raises(Exception):
            update.price = Decimal("39.99")  # type: ignore[misc]


# =============================================================================
# ProductUpdate Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestProductUpdateDefaults:
    """ProductUpdate fields default to UNSET."""

    def test_all_fields_default_to_unset(self) -> None:
        """All fields are UNSET when not specified."""
        update = ProductUpdate()

        assert update.title is UNSET
        assert update.description_html is UNSET
        assert update.vendor is UNSET
        assert update.status is UNSET
        assert update.tags is UNSET

    def test_get_set_fields_returns_empty(self) -> None:
        """get_set_fields returns empty dict for default update."""
        update = ProductUpdate()

        result = update.get_set_fields()

        assert result == {}


@pytest.mark.os_agnostic
class TestProductUpdateWithValues:
    """ProductUpdate stores provided values."""

    def test_stores_title(self) -> None:
        """Title value is stored."""
        update = ProductUpdate(title="New Product Title")

        assert update.title == "New Product Title"

    def test_stores_status_enum(self) -> None:
        """ProductStatus enum is stored."""
        update = ProductUpdate(status=ProductStatus.ACTIVE)

        assert update.status == ProductStatus.ACTIVE

    def test_stores_tags_list(self) -> None:
        """Tags list is stored."""
        update = ProductUpdate(tags=["sale", "featured", "new"])

        assert update.tags == ["sale", "featured", "new"]

    def test_get_set_fields_returns_set_fields(self) -> None:
        """get_set_fields returns only fields that were set."""
        update = ProductUpdate(
            title="New Title",
            status=ProductStatus.DRAFT,
        )

        result = update.get_set_fields()

        assert "title" in result
        assert "status" in result
        assert "description_html" not in result


@pytest.mark.os_agnostic
class TestProductUpdateWithNone:
    """ProductUpdate handles None for clearing fields."""

    def test_stores_none_for_clearing(self) -> None:
        """None is stored for clearing fields."""
        update = ProductUpdate(template_suffix=None)

        assert update.template_suffix is None
        assert update.template_suffix is not UNSET

    def test_get_set_fields_includes_none(self) -> None:
        """get_set_fields includes fields set to None."""
        update = ProductUpdate(seo_title=None)

        result = update.get_set_fields()

        assert "seo_title" in result
        assert result["seo_title"] is None


# =============================================================================
# MetafieldInput Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestMetafieldInputCreation:
    """MetafieldInput captures metafield input data."""

    def test_creates_with_all_fields(self) -> None:
        """MetafieldInput is created with all required fields."""
        metafield = MetafieldInput(
            namespace="custom",
            key="color",
            value="blue",
            type=MetafieldType.SINGLE_LINE_TEXT_FIELD,
        )

        assert metafield.namespace == "custom"
        assert metafield.key == "color"
        assert metafield.value == "blue"
        assert metafield.type == MetafieldType.SINGLE_LINE_TEXT_FIELD


@pytest.mark.os_agnostic
class TestMetafieldInputInVariantUpdate:
    """MetafieldInput integrates with VariantUpdate."""

    def test_stores_metafield_list(self) -> None:
        """VariantUpdate stores list of MetafieldInput."""
        metafields = [
            MetafieldInput(
                namespace="custom",
                key="color",
                value="blue",
                type=MetafieldType.SINGLE_LINE_TEXT_FIELD,
            ),
            MetafieldInput(
                namespace="custom",
                key="size",
                value="large",
                type=MetafieldType.SINGLE_LINE_TEXT_FIELD,
            ),
        ]
        update = VariantUpdate(metafields=metafields)

        assert update.metafields is not UNSET
        assert len(update.metafields) == 2  # type: ignore[arg-type]


# =============================================================================
# VariantUpdateRequest Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestVariantUpdateRequestValidation:
    """VariantUpdateRequest validates identifiers."""

    def test_accepts_variant_id(self) -> None:
        """Request with variant_id is valid."""
        request = VariantUpdateRequest(
            variant_id="gid://shopify/ProductVariant/123",
            update=VariantUpdate(price=Decimal("29.99")),
        )

        assert request.variant_id == "gid://shopify/ProductVariant/123"

    def test_accepts_sku(self) -> None:
        """Request with SKU is valid."""
        request = VariantUpdateRequest(
            sku="ABC-123",
            update=VariantUpdate(price=Decimal("29.99")),
        )

        assert request.sku == "ABC-123"

    def test_rejects_missing_identifier(self) -> None:
        """Request without identifier is rejected."""
        with pytest.raises(ValueError, match="Either variant_id or sku must be provided"):
            VariantUpdateRequest(update=VariantUpdate(price=Decimal("29.99")))

    def test_accepts_both_identifiers(self) -> None:
        """Request with both identifiers is valid."""
        request = VariantUpdateRequest(
            variant_id="gid://shopify/ProductVariant/123",
            sku="ABC-123",
            update=VariantUpdate(price=Decimal("29.99")),
        )

        assert request.variant_id is not None
        assert request.sku is not None


@pytest.mark.os_agnostic
class TestVariantUpdateRequestLocationOverride:
    """VariantUpdateRequest supports location override."""

    def test_accepts_location_id(self) -> None:
        """Request can include location_id for inventory."""
        request = VariantUpdateRequest(
            sku="ABC-123",
            update=VariantUpdate(),
            location_id="gid://shopify/Location/456",
        )

        assert request.location_id == "gid://shopify/Location/456"


# =============================================================================
# BulkUpdateResult Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestBulkUpdateResultProperties:
    """BulkUpdateResult provides helpful properties."""

    def test_success_count(self) -> None:
        """success_count returns number of successes."""
        result = BulkUpdateResult(
            succeeded=[
                UpdateSuccess(identifier="SKU-1"),
                UpdateSuccess(identifier="SKU-2"),
            ],
            failed=[UpdateFailure(identifier="SKU-3", error="Not found")],
        )

        assert result.success_count == 2

    def test_failure_count(self) -> None:
        """failure_count returns number of failures."""
        result = BulkUpdateResult(
            succeeded=[UpdateSuccess(identifier="SKU-1")],
            failed=[
                UpdateFailure(identifier="SKU-2", error="Error 1"),
                UpdateFailure(identifier="SKU-3", error="Error 2"),
            ],
        )

        assert result.failure_count == 2

    def test_all_succeeded_true(self) -> None:
        """all_succeeded is True when no failures."""
        result = BulkUpdateResult(
            succeeded=[
                UpdateSuccess(identifier="SKU-1"),
                UpdateSuccess(identifier="SKU-2"),
            ],
            failed=[],
        )

        assert result.all_succeeded is True

    def test_all_succeeded_false(self) -> None:
        """all_succeeded is False when any failure."""
        result = BulkUpdateResult(
            succeeded=[UpdateSuccess(identifier="SKU-1")],
            failed=[UpdateFailure(identifier="SKU-2", error="Error")],
        )

        assert result.all_succeeded is False


@pytest.mark.os_agnostic
class TestBulkUpdateResultEmpty:
    """BulkUpdateResult handles empty results."""

    def test_empty_result(self) -> None:
        """Empty result has zero counts."""
        result = BulkUpdateResult()

        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.all_succeeded is True


# =============================================================================
# UpdateSuccess Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestUpdateSuccessCreation:
    """UpdateSuccess captures successful update details."""

    def test_creates_with_identifier(self) -> None:
        """UpdateSuccess stores identifier."""
        success = UpdateSuccess(identifier="gid://shopify/ProductVariant/123")

        assert success.identifier == "gid://shopify/ProductVariant/123"

    def test_variant_defaults_to_none(self) -> None:
        """variant defaults to None."""
        success = UpdateSuccess(identifier="SKU-123")

        assert success.variant is None

    def test_product_defaults_to_none(self) -> None:
        """product defaults to None."""
        success = UpdateSuccess(identifier="SKU-123")

        assert success.product is None


# =============================================================================
# UpdateFailure Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestUpdateFailureCreation:
    """UpdateFailure captures failure details."""

    def test_creates_with_identifier_and_error(self) -> None:
        """UpdateFailure stores identifier and error."""
        failure = UpdateFailure(identifier="SKU-123", error="Variant not found")

        assert failure.identifier == "SKU-123"
        assert failure.error == "Variant not found"

    def test_error_code_defaults_to_none(self) -> None:
        """error_code defaults to None."""
        failure = UpdateFailure(identifier="SKU-123", error="Error")

        assert failure.error_code is None

    def test_field_defaults_to_none(self) -> None:
        """field defaults to None."""
        failure = UpdateFailure(identifier="SKU-123", error="Error")

        assert failure.field is None

    def test_stores_all_fields(self) -> None:
        """UpdateFailure stores all optional fields."""
        failure = UpdateFailure(
            identifier="SKU-123",
            error="Invalid price format",
            error_code="INVALID_VALUE",
            field="price",
        )

        assert failure.error_code == "INVALID_VALUE"
        assert failure.field == "price"


# =============================================================================
# InventoryLevel Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestInventoryLevelCreation:
    """InventoryLevel captures inventory state."""

    def test_creates_with_required_fields(self) -> None:
        """InventoryLevel is created with required fields."""
        level = InventoryLevel(
            inventory_item_id="gid://shopify/InventoryItem/123",
            location_id="gid://shopify/Location/456",
            available=100,
        )

        assert level.inventory_item_id == "gid://shopify/InventoryItem/123"
        assert level.location_id == "gid://shopify/Location/456"
        assert level.available == 100

    def test_updated_at_defaults_to_none(self) -> None:
        """updated_at defaults to None."""
        level = InventoryLevel(
            inventory_item_id="gid://shopify/InventoryItem/123",
            location_id="gid://shopify/Location/456",
            available=100,
        )

        assert level.updated_at is None


# =============================================================================
# WeightUnit Enum Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestWeightUnitEnum:
    """WeightUnit enum provides expected values."""

    def test_grams_value(self) -> None:
        """GRAMS has correct string value."""
        assert WeightUnit.GRAMS == "GRAMS"

    def test_kilograms_value(self) -> None:
        """KILOGRAMS has correct string value."""
        assert WeightUnit.KILOGRAMS == "KILOGRAMS"

    def test_ounces_value(self) -> None:
        """OUNCES has correct string value."""
        assert WeightUnit.OUNCES == "OUNCES"

    def test_pounds_value(self) -> None:
        """POUNDS has correct string value."""
        assert WeightUnit.POUNDS == "POUNDS"
