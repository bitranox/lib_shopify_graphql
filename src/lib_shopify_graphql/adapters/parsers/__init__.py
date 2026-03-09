"""Parsing functions for Shopify GraphQL API responses.

This package contains all functions for parsing raw GraphQL response data
into typed Pydantic models. Centralizing parsers improves testability
and reduces shopify_client complexity.

Submodules:
    _errors: GraphQL error parsing and formatting
    _truncation: Truncation detection and warning system
    _products: Product, variant, and entity parsing
    _input_builders: Mutation input construction
    _mutations: Mutation response parsing
"""

from ._errors import format_graphql_error, format_graphql_errors, parse_graphql_errors
from ._input_builders import build_product_create_input, build_product_input, build_variant_input
from ._mutations import (
    parse_inventory_level,
    parse_media_from_mutation,
    parse_media_user_errors,
    parse_staged_upload_target,
    parse_user_errors,
    parse_variant_from_mutation,
)

# Re-export VariantMutationResult (used by tests via this module)
from ...models._operations import VariantMutationResult
from ._products import (
    parse_datetime,
    parse_image,
    parse_inventory_policy,
    parse_metafield_type,
    parse_metafields,
    parse_money,
    parse_options,
    parse_page_info,
    parse_price_range,
    parse_product,
    parse_product_connection,
    parse_selected_options,
    parse_seo,
    parse_variant,
)
from ._truncation import _check_truncation, _has_more_pages, get_truncation_info

__all__ = [
    # Error parsing
    "format_graphql_error",
    "format_graphql_errors",
    "parse_graphql_errors",
    # Input builders
    "build_product_create_input",
    "build_product_input",
    "build_variant_input",
    # Response parsers
    "parse_datetime",
    "parse_image",
    "parse_inventory_level",
    "parse_inventory_policy",
    "parse_media_from_mutation",
    "parse_media_user_errors",
    "parse_metafield_type",
    "parse_metafields",
    "parse_money",
    "parse_options",
    "parse_page_info",
    "parse_price_range",
    "parse_product",
    "parse_product_connection",
    "parse_selected_options",
    "parse_seo",
    "parse_staged_upload_target",
    "parse_user_errors",
    "parse_variant",
    "parse_variant_from_mutation",
    # Truncation
    "_check_truncation",
    "_has_more_pages",
    "get_truncation_info",
    # Re-exported models
    "VariantMutationResult",
]
