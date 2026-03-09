"""Input builders for converting update models to GraphQL mutation format.

Transforms typed Pydantic update models into the dictionary format
expected by Shopify's GraphQL mutation inputs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...models import (
    InventoryPolicy,
    MetafieldInput,
    ProductCreate,
    ProductStatus,
    ProductUpdate,
    VariantUpdate,
    WeightUnit,
)


def _build_metafield_inputs(metafields: list[MetafieldInput] | None) -> list[dict[str, str]] | None:
    """Convert MetafieldInput list to GraphQL input format."""
    if metafields is None:
        return None
    return [{"namespace": mf.namespace, "key": mf.key, "value": mf.value, "type": mf.type.value} for mf in metafields]


_PRODUCT_FIELD_MAPPING: dict[str, str] = {
    "title": "title",
    "description_html": "descriptionHtml",
    "handle": "handle",
    "vendor": "vendor",
    "product_type": "productType",
    "tags": "tags",
    "status": "status",
    "template_suffix": "templateSuffix",
    "gift_card": "giftCard",
    "requires_selling_plan": "requiresSellingPlan",
    "collections_to_join": "collectionsToJoin",
    "collections_to_leave": "collectionsToLeave",
    "category": "category",
}


def _add_product_fields(result: dict[str, Any], set_fields: dict[str, Any]) -> None:
    """Add mapped product fields to result."""
    for model_field, graphql_field in _PRODUCT_FIELD_MAPPING.items():
        if model_field in set_fields:
            value = set_fields[model_field]
            result[graphql_field] = value.value if isinstance(value, ProductStatus) else value


def _add_seo_fields(result: dict[str, Any], set_fields: dict[str, Any]) -> None:
    """Add SEO fields as nested object if present."""
    if "seo_title" not in set_fields and "seo_description" not in set_fields:
        return
    seo: dict[str, str | None] = {}
    if "seo_title" in set_fields:
        seo["title"] = set_fields["seo_title"]  # type: ignore[assignment]
    if "seo_description" in set_fields:
        seo["description"] = set_fields["seo_description"]  # type: ignore[assignment]
    result["seo"] = seo


def build_product_input(product_id: str, update: ProductUpdate) -> dict[str, Any]:
    """Build ProductInput for productUpdate mutation."""
    result: dict[str, Any] = {"id": product_id}
    set_fields = update.get_set_fields()

    _add_product_fields(result, set_fields)
    _add_seo_fields(result, set_fields)

    if "metafields" in set_fields:
        result["metafields"] = _build_metafield_inputs(set_fields["metafields"])  # type: ignore[arg-type]

    return result


_PRODUCT_CREATE_FIELD_MAPPING: dict[str, str] = {
    "description_html": "descriptionHtml",
    "handle": "handle",
    "vendor": "vendor",
    "product_type": "productType",
    "tags": "tags",
}


def _add_create_optional_fields(result: dict[str, Any], create: ProductCreate) -> None:
    """Add optional fields from ProductCreate if not None."""
    for model_field, graphql_field in _PRODUCT_CREATE_FIELD_MAPPING.items():
        value = getattr(create, model_field)
        if value is not None:
            result[graphql_field] = value


def _add_create_seo_fields(result: dict[str, Any], create: ProductCreate) -> None:
    """Add SEO fields from ProductCreate if present."""
    if create.seo_title is None and create.seo_description is None:
        return
    seo: dict[str, str] = {}
    if create.seo_title is not None:
        seo["title"] = create.seo_title
    if create.seo_description is not None:
        seo["description"] = create.seo_description
    result["seo"] = seo


def build_product_create_input(create: ProductCreate) -> dict[str, Any]:
    """Build ProductInput for productCreate mutation."""
    result: dict[str, Any] = {"title": create.title}
    _add_create_optional_fields(result, create)

    if create.status is not None:
        result["status"] = create.status.value

    _add_create_seo_fields(result, create)
    return result


def _convert_variant_field_value(value: Any) -> Any:
    """Convert variant field value to GraphQL-compatible format."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, InventoryPolicy):
        return value.value
    return value


def _build_variant_direct_fields(
    result: dict[str, Any],
    set_fields: dict[str, Any],
) -> None:
    """Add direct variant fields to result dict."""
    field_mapping = {
        "price": "price",
        "compare_at_price": "compareAtPrice",
        "barcode": "barcode",
        "inventory_policy": "inventoryPolicy",
        "taxable": "taxable",
        "tax_code": "taxCode",
        "image_id": "mediaId",
    }

    for model_field, graphql_field in field_mapping.items():
        if model_field in set_fields:
            result[graphql_field] = _convert_variant_field_value(set_fields[model_field])


def _build_measurement_input(set_fields: dict[str, Any]) -> dict[str, Any]:
    """Build measurement input for inventoryItem (weight fields)."""
    measurement: dict[str, Any] = {}

    if "weight" in set_fields:
        weight_value = set_fields["weight"]
        if isinstance(weight_value, Decimal):
            weight_value = float(weight_value)
        measurement["weight"] = {"value": weight_value}

    if "weight_unit" in set_fields:
        weight_unit = set_fields["weight_unit"]
        if isinstance(weight_unit, WeightUnit):
            weight_unit = weight_unit.value
        if "weight" not in measurement:
            measurement["weight"] = {}
        measurement["weight"]["unit"] = weight_unit

    return measurement


def _build_inventory_item_input(set_fields: dict[str, Any]) -> dict[str, Any]:
    """Build inventoryItem input (API 2024-04+)."""
    inventory_item: dict[str, Any] = {}

    field_mapping = {
        "sku": "sku",
        "requires_shipping": "requiresShipping",
        "harmonized_system_code": "harmonizedSystemCode",
        "country_code_of_origin": "countryCodeOfOrigin",
    }

    for model_field, graphql_field in field_mapping.items():
        if model_field in set_fields:
            inventory_item[graphql_field] = set_fields[model_field]

    measurement = _build_measurement_input(set_fields)
    if measurement:
        inventory_item["measurement"] = measurement

    return inventory_item


def _build_option_values_input(set_fields: dict[str, Any]) -> list[dict[str, str]]:
    """Build option values array for variant options."""
    option_values: list[dict[str, str]] = []
    option_fields = ["option1", "option2", "option3"]

    for i, opt_field in enumerate(option_fields, start=1):
        if opt_field in set_fields and set_fields[opt_field] is not None:
            option_values.append({"optionName": f"Option{i}", "name": set_fields[opt_field]})  # type: ignore[dict-item]

    return option_values


def build_variant_input(variant_id: str, update: VariantUpdate) -> dict[str, Any]:
    """Build ProductVariantsBulkInput for productVariantsBulkUpdate mutation.

    Converts a VariantUpdate model to the GraphQL input format,
    only including fields that are not UNSET.

    Note: API 2024-04+ moved sku, requiresShipping, harmonizedSystemCode,
    and countryCodeOfOrigin to the inventoryItem nested input.

    Args:
        variant_id: Variant GID.
        update: VariantUpdate with fields to update.

    Returns:
        Dictionary suitable for ProductVariantsBulkInput GraphQL type.
    """
    result: dict[str, Any] = {"id": variant_id}
    set_fields = update.get_set_fields()

    _build_variant_direct_fields(result, set_fields)

    inventory_item = _build_inventory_item_input(set_fields)
    if inventory_item:
        result["inventoryItem"] = inventory_item

    option_values = _build_option_values_input(set_fields)
    if option_values:
        result["optionValues"] = option_values

    if "metafields" in set_fields:
        result["metafields"] = _build_metafield_inputs(set_fields["metafields"])  # type: ignore[arg-type]

    return result


__all__ = [
    "build_product_create_input",
    "build_product_input",
    "build_variant_input",
]
