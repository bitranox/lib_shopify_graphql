"""Product operation CLI commands.

This module provides CLI commands for product CRUD operations:
- get-product: Retrieve a product by ID
- create-product: Create a new product
- duplicate-product: Duplicate an existing product
- delete-product: Delete a product permanently
- update-product: Update product fields
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import lib_log_rich.runtime
import orjson
import rich_click as click

from .. import safe_console
from ..adapters import CachedSKUResolver
from ..enums import OutputFormat
from ..exceptions import AuthenticationError, GraphQLError, ProductNotFoundError
from ..models import (
    UNSET,
    DeleteProductResult,
    Product,
    ProductCreate,
    ProductStatus,
    ProductUpdate,
)
from ..shopify_client import (
    create_product,
    delete_product,
    duplicate_product,
    get_product_by_id,
    update_product,
)
from ._common import CLICK_CONTEXT_SETTINGS, EnumChoice, get_effective_config_and_profile, shopify_session
from .typed_click import argument, option

if TYPE_CHECKING:
    from lib_layered_config import Config

    from ..models import ShopifyCredentials

logger = logging.getLogger(__name__)


# =============================================================================
# Output Helpers
# =============================================================================


def _output_product(product: Product, output_format: OutputFormat) -> None:
    """Output a product in the requested format.

    Args:
        product: Product model to output.
        output_format: Format for the output (JSON or human-readable).
    """
    if output_format == OutputFormat.JSON:
        data = product.model_dump(mode="json")
        safe_console.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
    else:
        safe_console.echo(f"\nProduct: {product.title}")
        safe_console.echo("─" * 50)
        safe_console.echo(f"  ID:           {product.id}")
        safe_console.echo(f"  Handle:       {product.handle}")
        safe_console.echo(f"  Status:       {product.status.value}")
        safe_console.echo(f"  Vendor:       {product.vendor or '-'}")
        safe_console.echo(f"  Type:         {product.product_type or '-'}")
        safe_console.echo(f"  Tags:         {', '.join(product.tags) if product.tags else '-'}")
        safe_console.echo(f"  Variants:     {len(product.variants)}")
        safe_console.echo(f"  Images:       {len(product.images)}")
        safe_console.echo(f"  Created:      {product.created_at.isoformat()}")
        safe_console.echo(f"  Updated:      {product.updated_at.isoformat()}")


def _output_delete_result(result: DeleteProductResult, output_format: OutputFormat) -> None:
    """Output delete result in requested format."""
    if output_format == OutputFormat.JSON:
        data = {"deleted_product_id": result.deleted_product_id, "success": result.success}
        safe_console.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
    else:
        safe_console.echo(f"\n✓ Product deleted: {result.deleted_product_id}")


# =============================================================================
# JSON Input Helpers
# =============================================================================


def _read_json_input(json_input: str) -> dict[str, object]:
    """Read and parse JSON from stdin, file path, or raw string."""
    try:
        if json_input == "-":
            return orjson.loads(sys.stdin.read())
        if json_input.startswith("{"):
            return orjson.loads(json_input)
        with Path(json_input).open("rb") as f:
            return orjson.loads(f.read())
    except orjson.JSONDecodeError as exc:
        safe_console.echo(f"Invalid JSON: {exc}", err=True)
        raise SystemExit(1) from exc
    except FileNotFoundError:
        safe_console.echo(f"File not found: {json_input}", err=True)
        raise SystemExit(1) from None


def _flatten_seo_fields(data: dict[str, object]) -> None:
    """Flatten nested seo object into seo_title/seo_description fields."""
    if "seo" not in data or not isinstance(data["seo"], dict):
        return

    seo: dict[str, object] = data["seo"]  # type: ignore[assignment]
    if seo.get("title"):
        data["seo_title"] = seo["title"]
    if seo.get("description"):
        data["seo_description"] = seo["description"]
    del data["seo"]


# =============================================================================
# Create Product Helpers
# =============================================================================

_READONLY_CREATE_FIELDS = frozenset(
    [
        "id",
        "legacy_resource_id",
        "created_at",
        "updated_at",
        "published_at",
        "variants",
        "images",
        "featured_image",
        "options",
        "price_range",
        "total_inventory",
        "tracks_inventory",
        "has_only_default_variant",
        "has_out_of_stock_variants",
        "is_gift_card",
        "online_store_url",
        "online_store_preview_url",
        "template_suffix",
        "metafields",
        "description",  # Use description_html instead
        "media",
    ]
)


def _strip_readonly_create_fields(data: dict[str, object]) -> None:
    """Remove read-only fields that cannot be set on create."""
    for field_name in _READONLY_CREATE_FIELDS:
        data.pop(field_name, None)  # type: ignore[union-attr]


def _parse_product_create_json(json_input: str) -> ProductCreate:
    """Parse JSON input into ProductCreate model.

    Accepts:
    - '-' for stdin
    - A file path
    - Raw JSON string starting with '{'
    """
    data = _read_json_input(json_input)
    _flatten_seo_fields(data)
    _strip_readonly_create_fields(data)

    try:
        return ProductCreate.model_validate(data)
    except Exception as exc:
        safe_console.echo(f"Invalid product data: {exc}", err=True)
        raise SystemExit(1) from exc


def _build_product_create_from_options(
    *,
    title: str | None,
    vendor: str | None,
    product_type: str | None,
    status: ProductStatus | None,
    tags: str | None,
    description: str | None,
    handle: str | None,
    seo_title: str | None,
    seo_description: str | None,
) -> ProductCreate:
    """Build ProductCreate from CLI options."""
    if not title:
        safe_console.echo("Error: --title is required when not using --json", err=True)
        raise SystemExit(1)

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    return ProductCreate(
        title=title,
        vendor=vendor,
        product_type=product_type,
        status=status,
        tags=tag_list,
        description_html=description,
        handle=handle,
        seo_title=seo_title,
        seo_description=seo_description,
    )


# =============================================================================
# Update Product Helpers
# =============================================================================

_READONLY_UPDATE_FIELDS = frozenset(
    [
        "id",
        "legacy_resource_id",
        "created_at",
        "updated_at",
        "published_at",
        "variants",
        "images",
        "featured_image",
        "options",
        "price_range",
        "total_inventory",
        "tracks_inventory",
        "has_only_default_variant",
        "has_out_of_stock_variants",
        "is_gift_card",
        "online_store_url",
        "online_store_preview_url",
        "template_suffix",
        "metafields",
        "description",
    ]
)


def _option_or_unset(value: Any) -> Any:
    """Return value if set, otherwise UNSET sentinel."""
    return value if value is not None else UNSET


def _parse_tags_option(tags: str | None) -> Any:
    """Parse comma-separated tags or return UNSET."""
    return [t.strip() for t in tags.split(",")] if tags else UNSET


def _strip_readonly_fields(data: dict[str, object]) -> None:
    """Remove read-only fields that cannot be updated."""
    for field_name in _READONLY_UPDATE_FIELDS:
        data.pop(field_name, None)  # type: ignore[union-attr]


def _parse_product_update_json(json_input: str) -> ProductUpdate:
    """Parse JSON input into ProductUpdate model."""
    data = _read_json_input(json_input)
    _flatten_seo_fields(data)
    _strip_readonly_fields(data)

    # Convert remaining fields to ProductUpdate (None explicitly clears field)
    update_data = dict(data.items())

    try:
        return ProductUpdate.model_validate(update_data)
    except Exception as exc:
        safe_console.echo(f"Invalid update data: {exc}", err=True)
        raise SystemExit(1) from exc


def _build_product_update_from_options(
    *,
    title: str | None,
    vendor: str | None,
    product_type: str | None,
    status: ProductStatus | None,
    tags: str | None,
    description: str | None,
    handle: str | None,
    seo_title: str | None,
    seo_description: str | None,
) -> ProductUpdate:
    """Build ProductUpdate from CLI options (only set fields that were provided)."""
    return ProductUpdate(
        title=_option_or_unset(title),
        vendor=_option_or_unset(vendor),
        product_type=_option_or_unset(product_type),
        status=_option_or_unset(status),
        tags=_parse_tags_option(tags),
        description_html=_option_or_unset(description),
        handle=_option_or_unset(handle),
        seo_title=_option_or_unset(seo_title),
        seo_description=_option_or_unset(seo_description),
    )


# =============================================================================
# Delete Helpers
# =============================================================================


def _confirm_delete(product_id: str) -> bool:
    """Prompt user to confirm product deletion."""
    safe_console.echo(f"WARNING: This will permanently delete product {product_id}")
    safe_console.echo("All variants, inventory, and associated data will be lost.")
    return click.confirm("Are you sure you want to continue?", default=False)


def _create_sku_resolver_for_delete(
    config: Config,
    credentials: ShopifyCredentials,
    create_sku_cache_from_config: Any,
) -> CachedSKUResolver | None:
    """Create SKU resolver for cache clearing (best-effort)."""
    sku_cache = create_sku_cache_from_config(config)
    if sku_cache is None:
        return None

    try:
        with shopify_session(credentials) as session_temp:
            return CachedSKUResolver(sku_cache, session_temp._graphql_client)
    except Exception:  # nosec B110 - SKU cache clearing is best-effort
        return None


# =============================================================================
# Command Runners
# =============================================================================


@dataclass(frozen=True, slots=True)
class _ProductFieldOptions:
    """The product field options shared by ``create-product`` and ``update-product``."""

    title: str | None
    vendor: str | None
    product_type: str | None
    status: ProductStatus | None
    tags: str | None
    description: str | None
    handle: str | None
    seo_title: str | None
    seo_description: str | None

    def to_create(self) -> ProductCreate:
        """Build a ProductCreate from these options (exits 1 when the title is missing)."""
        return _build_product_create_from_options(
            title=self.title,
            vendor=self.vendor,
            product_type=self.product_type,
            status=self.status,
            tags=self.tags,
            description=self.description,
            handle=self.handle,
            seo_title=self.seo_title,
            seo_description=self.seo_description,
        )

    def to_update(self) -> ProductUpdate:
        """Build a ProductUpdate setting only the options that were given."""
        return _build_product_update_from_options(
            title=self.title,
            vendor=self.vendor,
            product_type=self.product_type,
            status=self.status,
            tags=self.tags,
            description=self.description,
            handle=self.handle,
            seo_title=self.seo_title,
            seo_description=self.seo_description,
        )


def _resolve_product_create(json_input: str | None, fields: _ProductFieldOptions) -> ProductCreate:
    """Build the ProductCreate from --json when given, otherwise from the field options."""
    if json_input:
        product_create = _parse_product_create_json(json_input)
        logger.info("Creating product from JSON: title='%s'", product_create.title)
        return product_create
    product_create = fields.to_create()
    logger.info("Creating product: title='%s'", product_create.title)
    return product_create


def _resolve_product_update(product_id: str, json_input: str | None, fields: _ProductFieldOptions) -> ProductUpdate:
    """Build the ProductUpdate from --json when given, otherwise from the field options."""
    if json_input:
        product_update = _parse_product_update_json(json_input)
        logger.info("Updating product '%s' from JSON", product_id)
        return product_update
    product_update = fields.to_update()
    logger.info("Updating product '%s'", product_id)
    return product_update


def _exit_on_shopify_error(exc: Exception, credentials: Any, get_fix_suggestion: Any) -> NoReturn:
    """Report an authentication or GraphQL error with its fix suggestion and exit 1."""
    safe_console.echo(f"Error: {exc}", err=True)
    safe_console.echo(get_fix_suggestion(exc, credentials), err=True)
    raise SystemExit(1) from exc


def _exit_not_found(message: str) -> NoReturn:
    """Report a missing product and exit 1 without chaining the lookup error."""
    safe_console.echo(message, err=True)
    raise SystemExit(1) from None


def _run_get_product(
    ctx: click.Context,
    *,
    product_id: str,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Fetch and print a product (body of ``get-product``)."""
    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {"command": "get-product", "profile": effective_profile, "product_id": product_id}

    with lib_log_rich.runtime.bind(job_id="cli-get-product", extra=extra):
        logger.info("Fetching product '%s'", product_id)

        credentials = get_credentials_or_exit(config)

        try:
            with shopify_session(credentials) as session:
                product = get_product_by_id(session, product_id)
                _output_product(product, output_format)
        except ProductNotFoundError:
            _exit_not_found(f"Product not found: {product_id}")
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


def _run_create_product(
    ctx: click.Context,
    *,
    fields: _ProductFieldOptions,
    json_input: str | None,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Create a product and print it (body of ``create-product``)."""
    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {"command": "create-product", "profile": effective_profile}

    with lib_log_rich.runtime.bind(job_id="cli-create-product", extra=extra):
        product_create = _resolve_product_create(json_input, fields)

        credentials = get_credentials_or_exit(config)

        try:
            with shopify_session(credentials) as session:
                product = create_product(session, product_create)
                logger.info("Product created: id='%s'", product.id)
                _output_product(product, output_format)
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


def _run_duplicate_product(
    ctx: click.Context,
    *,
    product_id: str,
    new_title: str,
    no_images: bool,
    status: ProductStatus | None,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Duplicate a product and print the copy (body of ``duplicate-product``)."""
    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {
        "command": "duplicate-product",
        "profile": effective_profile,
        "product_id": product_id,
        "new_title": new_title,
    }

    with lib_log_rich.runtime.bind(job_id="cli-duplicate-product", extra=extra):
        logger.info("Duplicating product '%s' with new title '%s'", product_id, new_title)

        credentials = get_credentials_or_exit(config)

        try:
            with shopify_session(credentials) as session:
                result = duplicate_product(
                    session,
                    product_id,
                    new_title,
                    include_images=not no_images,
                    new_status=status,
                )
                logger.info("Product duplicated: original='%s', new='%s'", result.original_product_id, result.new_product.id)
                _output_product(result.new_product, output_format)
        except ProductNotFoundError:
            _exit_not_found(f"Source product not found: {product_id}")
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


def _run_delete_product(
    ctx: click.Context,
    *,
    product_id: str,
    force: bool,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
    create_sku_cache_from_config: Any,
) -> None:
    """Delete a product after confirmation (body of ``delete-product``)."""
    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {"command": "delete-product", "profile": effective_profile, "product_id": product_id}

    with lib_log_rich.runtime.bind(job_id="cli-delete-product", extra=extra):
        if not force and not _confirm_delete(product_id):
            safe_console.echo("Aborted.")
            raise SystemExit(0)

        logger.info("Deleting product '%s'", product_id)

        credentials = get_credentials_or_exit(config)

        sku_resolver = _create_sku_resolver_for_delete(config, credentials, create_sku_cache_from_config)

        try:
            with shopify_session(credentials) as session:
                result = delete_product(session, product_id, sku_resolver=sku_resolver)
                logger.info("Product deleted: id='%s'", result.deleted_product_id)
                _output_delete_result(result, output_format)
        except ProductNotFoundError:
            _exit_not_found(f"Product not found: {product_id}")
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


def _run_update_product(
    ctx: click.Context,
    *,
    product_id: str,
    fields: _ProductFieldOptions,
    json_input: str | None,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Apply a partial product update and print the result (body of ``update-product``)."""
    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {"command": "update-product", "profile": effective_profile, "product_id": product_id}

    with lib_log_rich.runtime.bind(job_id="cli-update-product", extra=extra):
        product_update = _resolve_product_update(product_id, json_input, fields)

        credentials = get_credentials_or_exit(config)

        try:
            with shopify_session(credentials) as session:
                product = update_product(session, product_id, product_update)
                logger.info("Product updated: id='%s'", product.id)
                _output_product(product, output_format)
        except ProductNotFoundError:
            _exit_not_found(f"Product not found: {product_id}")
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


# =============================================================================
# CLI Commands
# =============================================================================


def register_product_commands(
    cli_group: click.Group,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
    create_sku_cache_from_config: Any,
) -> None:
    """Register product operation commands on the CLI group.

    Args:
        cli_group: The Click group to register commands on.
        get_credentials_or_exit: Function to get credentials from config.
        get_fix_suggestion: Function to get fix suggestions for errors.
        create_sku_cache_from_config: Function to create SKU cache from config.
    """

    @cli_group.command("get-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @argument("product_id", type=str)
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command",
    )
    @click.pass_context
    def cli_get_product(
        ctx: click.Context,
        product_id: str,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Retrieve a product by ID.

        PRODUCT_ID can be a Shopify GID (gid://shopify/Product/123456789)
        or a numeric ID (123456789).

        Examples:

            lib-shopify-graphql get-product 123456789

            lib-shopify-graphql get-product gid://shopify/Product/123456789 --format human
        """
        _run_get_product(
            ctx,
            product_id=product_id,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
        )

    @cli_group.command("create-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @option("--title", type=str, default=None, help="Product title (required if no --json)")
    @option("--vendor", type=str, default=None, help="Product vendor")
    @option("--product-type", type=str, default=None, help="Product type/category")
    @option(
        "--status",
        type=EnumChoice(ProductStatus),
        default=None,
        help="Product status (default: DRAFT)",
    )
    @option("--tags", type=str, default=None, help="Comma-separated tags")
    @option("--description", type=str, default=None, help="HTML description")
    @option("--handle", type=str, default=None, help="URL handle")
    @option("--seo-title", type=str, default=None, help="SEO title")
    @option("--seo-description", type=str, default=None, help="SEO meta description")
    @option(
        "--json",
        "json_input",
        type=str,
        default=None,
        help="JSON input (file path or '-' for stdin)",
    )
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_create_product(
        ctx: click.Context,
        *,
        title: str | None,
        vendor: str | None,
        product_type: str | None,
        status: ProductStatus | None,
        tags: str | None,
        description: str | None,
        handle: str | None,
        seo_title: str | None,
        seo_description: str | None,
        json_input: str | None,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Create a new product.

        Create via individual options or --json input. The --json option accepts
        the output from get-product (read-only fields are automatically stripped).

        Examples:

            lib-shopify-graphql create-product --title "My Product" --status DRAFT

            echo '{"title": "JSON Product"}' | lib-shopify-graphql create-product --json -

            lib-shopify-graphql create-product --json product.json
        """
        fields = _ProductFieldOptions(
            title=title,
            vendor=vendor,
            product_type=product_type,
            status=status,
            tags=tags,
            description=description,
            handle=handle,
            seo_title=seo_title,
            seo_description=seo_description,
        )
        _run_create_product(
            ctx,
            fields=fields,
            json_input=json_input,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
        )

    @cli_group.command("duplicate-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @argument("product_id", type=str)
    @argument("new_title", type=str)
    @option("--no-images", is_flag=True, default=False, help="Don't copy images")
    @option(
        "--status",
        type=EnumChoice(ProductStatus),
        default=None,
        help="Status for new product (default: same as original)",
    )
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_duplicate_product(
        ctx: click.Context,
        *,
        product_id: str,
        new_title: str,
        no_images: bool,
        status: ProductStatus | None,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Duplicate an existing product.

        PRODUCT_ID is the source product to duplicate.
        NEW_TITLE is the title for the duplicated product.

        Examples:

            lib-shopify-graphql duplicate-product 123456789 "Copy of Product"

            lib-shopify-graphql duplicate-product 123456789 "Draft Copy" --status DRAFT --no-images
        """
        _run_duplicate_product(
            ctx,
            product_id=product_id,
            new_title=new_title,
            no_images=no_images,
            status=status,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
        )

    @cli_group.command("delete-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @argument("product_id", type=str)
    @option("--force", is_flag=True, default=False, help="Skip confirmation prompt")
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.HUMAN,
        help="Output format (default: human)",
    )
    @option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_delete_product(
        ctx: click.Context,
        *,
        product_id: str,
        force: bool,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Delete a product permanently.

        WARNING: This operation is irreversible. All variants, inventory,
        and associated data will be permanently deleted.
        """
        _run_delete_product(
            ctx,
            product_id=product_id,
            force=force,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
            create_sku_cache_from_config=create_sku_cache_from_config,
        )

    @cli_group.command("update-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @argument("product_id", type=str)
    @option("--title", type=str, default=None, help="Product title")
    @option("--vendor", type=str, default=None, help="Product vendor")
    @option("--product-type", type=str, default=None, help="Product type/category")
    @option(
        "--status",
        type=EnumChoice(ProductStatus),
        default=None,
        help="Product status (ACTIVE, DRAFT, ARCHIVED)",
    )
    @option("--tags", type=str, default=None, help="Comma-separated tags")
    @option("--description", type=str, default=None, help="HTML description")
    @option("--handle", type=str, default=None, help="URL handle")
    @option("--seo-title", type=str, default=None, help="SEO title")
    @option("--seo-description", type=str, default=None, help="SEO meta description")
    @option(
        "--json",
        "json_input",
        type=str,
        default=None,
        help="JSON input (file path or '-' for stdin)",
    )
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_update_product(
        ctx: click.Context,
        *,
        product_id: str,
        title: str | None,
        vendor: str | None,
        product_type: str | None,
        status: ProductStatus | None,
        tags: str | None,
        description: str | None,
        handle: str | None,
        seo_title: str | None,
        seo_description: str | None,
        json_input: str | None,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Update a product (partial update - only specified fields change).

        PRODUCT_ID can be a Shopify GID or numeric ID.

        Only fields you specify will be updated; others remain unchanged.

        Examples:

            lib-shopify-graphql update-product 123456789 --title "New Title"

            lib-shopify-graphql update-product 123456789 --status ACTIVE --tags "sale,featured"

            lib-shopify-graphql update-product 123456789 --json updates.json
        """
        fields = _ProductFieldOptions(
            title=title,
            vendor=vendor,
            product_type=product_type,
            status=status,
            tags=tags,
            description=description,
            handle=handle,
            seo_title=seo_title,
            seo_description=seo_description,
        )
        _run_update_product(
            ctx,
            product_id=product_id,
            fields=fields,
            json_input=json_input,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
        )


__all__ = [
    # Internal functions exported for tests
    "_build_product_create_from_options",
    "_flatten_seo_fields",
    "_output_product",
    "_parse_product_create_json",
    "_read_json_input",
    "_strip_readonly_create_fields",
    "register_product_commands",
]
