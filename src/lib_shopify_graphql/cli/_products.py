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
from typing import TYPE_CHECKING, Any

import lib_log_rich.runtime
import orjson
import rich_click as click
from lib_layered_config import Config

from ..adapters import CachedSKUResolver
from ..enums import OutputFormat
from ..exceptions import AuthenticationError, GraphQLError, ProductNotFoundError
from ..models import (
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
    login,
    logout,
    update_product,
)
from ._common import CLICK_CONTEXT_SETTINGS, EnumChoice, get_effective_config_and_profile

if TYPE_CHECKING:
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
        click.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
    else:
        click.echo(f"\nProduct: {product.title}")
        click.echo("─" * 50)
        click.echo(f"  ID:           {product.id}")
        click.echo(f"  Handle:       {product.handle}")
        click.echo(f"  Status:       {product.status.value}")
        click.echo(f"  Vendor:       {product.vendor or '-'}")
        click.echo(f"  Type:         {product.product_type or '-'}")
        click.echo(f"  Tags:         {', '.join(product.tags) if product.tags else '-'}")
        click.echo(f"  Variants:     {len(product.variants)}")
        click.echo(f"  Images:       {len(product.images)}")
        click.echo(f"  Created:      {product.created_at.isoformat()}")
        click.echo(f"  Updated:      {product.updated_at.isoformat()}")


def _output_delete_result(result: DeleteProductResult, output_format: OutputFormat) -> None:
    """Output delete result in requested format."""
    if output_format == OutputFormat.JSON:
        data = {"deleted_product_id": result.deleted_product_id, "success": result.success}
        click.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
    else:
        click.echo(f"\n✓ Product deleted: {result.deleted_product_id}")


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
        with open(json_input, "rb") as f:
            return orjson.loads(f.read())
    except orjson.JSONDecodeError as exc:
        click.echo(f"Invalid JSON: {exc}", err=True)
        raise SystemExit(1) from exc
    except FileNotFoundError:
        click.echo(f"File not found: {json_input}", err=True)
        raise SystemExit(1)


def _flatten_seo_fields(data: dict[str, object]) -> None:
    """Flatten nested seo object into seo_title/seo_description fields."""
    if "seo" not in data or not isinstance(data["seo"], dict):
        return

    seo: dict[str, object] = data["seo"]  # type: ignore[assignment]
    if "title" in seo and seo["title"]:
        data["seo_title"] = seo["title"]
    if "description" in seo and seo["description"]:
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
        click.echo(f"Invalid product data: {exc}", err=True)
        raise SystemExit(1) from exc


def _build_product_create_from_options(
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
        click.echo("Error: --title is required when not using --json", err=True)
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
    from ..models import UNSET

    return value if value is not None else UNSET


def _parse_tags_option(tags: str | None) -> Any:
    """Parse comma-separated tags or return UNSET."""
    from ..models import UNSET

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
    update_data = {key: value for key, value in data.items()}

    try:
        return ProductUpdate.model_validate(update_data)
    except Exception as exc:
        click.echo(f"Invalid update data: {exc}", err=True)
        raise SystemExit(1) from exc


def _build_product_update_from_options(
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
    click.echo(f"WARNING: This will permanently delete product {product_id}")
    click.echo("All variants, inventory, and associated data will be lost.")
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

    session_temp = None
    try:
        session_temp = login(credentials)
        return CachedSKUResolver(sku_cache, session_temp._graphql_client)
    except Exception:  # nosec B110 - SKU cache clearing is best-effort
        return None
    finally:
        if session_temp is not None and session_temp.is_active:
            logout(session_temp)


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
    @click.argument("product_id", type=str)
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @click.option(
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
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "get-product", "profile": effective_profile, "product_id": product_id}

        with lib_log_rich.runtime.bind(job_id="cli-get-product", extra=extra):
            logger.info(f"Fetching product '{product_id}'")

            credentials = get_credentials_or_exit(config)

            session = None
            try:
                session = login(credentials)
                product = get_product_by_id(session, product_id)
                _output_product(product, output_format)
            except ProductNotFoundError:
                click.echo(f"Product not found: {product_id}", err=True)
                raise SystemExit(1)
            except (AuthenticationError, GraphQLError) as exc:
                click.echo(f"Error: {exc}", err=True)
                click.echo(get_fix_suggestion(exc, credentials), err=True)
                raise SystemExit(1)
            finally:
                if session is not None and session.is_active:
                    logout(session)

    @cli_group.command("create-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.option("--title", type=str, default=None, help="Product title (required if no --json)")
    @click.option("--vendor", type=str, default=None, help="Product vendor")
    @click.option("--product-type", type=str, default=None, help="Product type/category")
    @click.option(
        "--status",
        type=EnumChoice(ProductStatus),
        default=None,
        help="Product status (default: DRAFT)",
    )
    @click.option("--tags", type=str, default=None, help="Comma-separated tags")
    @click.option("--description", type=str, default=None, help="HTML description")
    @click.option("--handle", type=str, default=None, help="URL handle")
    @click.option("--seo-title", type=str, default=None, help="SEO title")
    @click.option("--seo-description", type=str, default=None, help="SEO meta description")
    @click.option(
        "--json",
        "json_input",
        type=str,
        default=None,
        help="JSON input (file path or '-' for stdin)",
    )
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @click.option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_create_product(
        ctx: click.Context,
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
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "create-product", "profile": effective_profile}

        with lib_log_rich.runtime.bind(job_id="cli-create-product", extra=extra):
            # Build ProductCreate from options or JSON
            if json_input:
                product_create = _parse_product_create_json(json_input)
                logger.info(f"Creating product from JSON: title='{product_create.title}'")
            else:
                product_create = _build_product_create_from_options(
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
                logger.info(f"Creating product: title='{product_create.title}'")

            credentials = get_credentials_or_exit(config)

            session = None
            try:
                session = login(credentials)
                product = create_product(session, product_create)
                logger.info(f"Product created: id='{product.id}'")
                _output_product(product, output_format)
            except (AuthenticationError, GraphQLError) as exc:
                click.echo(f"Error: {exc}", err=True)
                click.echo(get_fix_suggestion(exc, credentials), err=True)
                raise SystemExit(1)
            finally:
                if session is not None and session.is_active:
                    logout(session)

    @cli_group.command("duplicate-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.argument("product_id", type=str)
    @click.argument("new_title", type=str)
    @click.option("--no-images", is_flag=True, default=False, help="Don't copy images")
    @click.option(
        "--status",
        type=EnumChoice(ProductStatus),
        default=None,
        help="Status for new product (default: same as original)",
    )
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @click.option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_duplicate_product(
        ctx: click.Context,
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
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {
            "command": "duplicate-product",
            "profile": effective_profile,
            "product_id": product_id,
            "new_title": new_title,
        }

        with lib_log_rich.runtime.bind(job_id="cli-duplicate-product", extra=extra):
            logger.info(f"Duplicating product '{product_id}' with new title '{new_title}'")

            credentials = get_credentials_or_exit(config)

            session = None
            try:
                session = login(credentials)
                result = duplicate_product(
                    session,
                    product_id,
                    new_title,
                    include_images=not no_images,
                    new_status=status,
                )
                logger.info(f"Product duplicated: original='{result.original_product_id}', new='{result.new_product.id}'")
                _output_product(result.new_product, output_format)
            except ProductNotFoundError:
                click.echo(f"Source product not found: {product_id}", err=True)
                raise SystemExit(1)
            except (AuthenticationError, GraphQLError) as exc:
                click.echo(f"Error: {exc}", err=True)
                click.echo(get_fix_suggestion(exc, credentials), err=True)
                raise SystemExit(1)
            finally:
                if session is not None and session.is_active:
                    logout(session)

    @cli_group.command("delete-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.argument("product_id", type=str)
    @click.option("--force", is_flag=True, default=False, help="Skip confirmation prompt")
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.HUMAN,
        help="Output format (default: human)",
    )
    @click.option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_delete_product(
        ctx: click.Context,
        product_id: str,
        force: bool,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Delete a product permanently.

        WARNING: This operation is irreversible. All variants, inventory,
        and associated data will be permanently deleted.
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "delete-product", "profile": effective_profile, "product_id": product_id}

        with lib_log_rich.runtime.bind(job_id="cli-delete-product", extra=extra):
            if not force and not _confirm_delete(product_id):
                click.echo("Aborted.")
                raise SystemExit(0)

            logger.info(f"Deleting product '{product_id}'")

            credentials = get_credentials_or_exit(config)

            sku_resolver = _create_sku_resolver_for_delete(config, credentials, create_sku_cache_from_config)

            session = None
            try:
                session = login(credentials)
                result = delete_product(session, product_id, sku_resolver=sku_resolver)
                logger.info(f"Product deleted: id='{result.deleted_product_id}'")
                _output_delete_result(result, output_format)
            except ProductNotFoundError:
                click.echo(f"Product not found: {product_id}", err=True)
                raise SystemExit(1)
            except (AuthenticationError, GraphQLError) as exc:
                click.echo(f"Error: {exc}", err=True)
                click.echo(get_fix_suggestion(exc, credentials), err=True)
                raise SystemExit(1)
            finally:
                if session is not None and session.is_active:
                    logout(session)

    @cli_group.command("update-product", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.argument("product_id", type=str)
    @click.option("--title", type=str, default=None, help="Product title")
    @click.option("--vendor", type=str, default=None, help="Product vendor")
    @click.option("--product-type", type=str, default=None, help="Product type/category")
    @click.option(
        "--status",
        type=EnumChoice(ProductStatus),
        default=None,
        help="Product status (ACTIVE, DRAFT, ARCHIVED)",
    )
    @click.option("--tags", type=str, default=None, help="Comma-separated tags")
    @click.option("--description", type=str, default=None, help="HTML description")
    @click.option("--handle", type=str, default=None, help="URL handle")
    @click.option("--seo-title", type=str, default=None, help="SEO title")
    @click.option("--seo-description", type=str, default=None, help="SEO meta description")
    @click.option(
        "--json",
        "json_input",
        type=str,
        default=None,
        help="JSON input (file path or '-' for stdin)",
    )
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @click.option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_update_product(
        ctx: click.Context,
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
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "update-product", "profile": effective_profile, "product_id": product_id}

        with lib_log_rich.runtime.bind(job_id="cli-update-product", extra=extra):
            # Build ProductUpdate from options or JSON
            if json_input:
                product_update = _parse_product_update_json(json_input)
                logger.info(f"Updating product '{product_id}' from JSON")
            else:
                product_update = _build_product_update_from_options(
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
                logger.info(f"Updating product '{product_id}'")

            credentials = get_credentials_or_exit(config)

            session = None
            try:
                session = login(credentials)
                product = update_product(session, product_id, product_update)
                logger.info(f"Product updated: id='{product.id}'")
                _output_product(product, output_format)
            except ProductNotFoundError:
                click.echo(f"Product not found: {product_id}", err=True)
                raise SystemExit(1)
            except (AuthenticationError, GraphQLError) as exc:
                click.echo(f"Error: {exc}", err=True)
                click.echo(get_fix_suggestion(exc, credentials), err=True)
                raise SystemExit(1)
            finally:
                if session is not None and session.is_active:
                    logout(session)


__all__ = [
    "register_product_commands",
    # Internal functions exported for tests
    "_build_product_create_from_options",
    "_flatten_seo_fields",
    "_output_product",
    "_parse_product_create_json",
    "_read_json_input",
    "_strip_readonly_create_fields",
]
