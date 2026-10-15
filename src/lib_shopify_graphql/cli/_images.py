"""Image operation CLI commands.

This module provides CLI commands for product image operations:
- add-image: Add image(s) to a product from URL or local file
- delete-image: Delete an image from a product
- update-image: Update image metadata (alt text)
- reorder-images: Reorder product images
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import lib_log_rich.runtime
import orjson
import rich_click as click

from .. import safe_console
from ..enums import OutputFormat
from ..exceptions import AuthenticationError, GraphQLError, ProductNotFoundError
from ..models import ImageCreateSuccess, ImageDeleteResult, ImageReorderResult, ImageSource, ImageUpdate
from ..shopify_client import (
    create_image,
    delete_image,
    reorder_images,
    update_image,
)
from ._common import CLICK_CONTEXT_SETTINGS, EnumChoice, get_effective_config_and_profile, shopify_session
from .typed_click import argument, option

if TYPE_CHECKING:
    from ..shopify_client import ShopifySession

logger = logging.getLogger(__name__)

#: Reordering requires at least two images - a single image has nothing to reorder against.
_MIN_IMAGES_FOR_REORDER = 2


# =============================================================================
# Helper Functions
# =============================================================================


def _create_images_from_sources(
    session: ShopifySession,
    product_id: str,
    urls: tuple[str, ...],
    files: tuple[str, ...],
    alt: str | None,
) -> list[dict[str, str]]:
    """Create images from URL and file sources."""
    results: list[dict[str, str]] = []

    for url in urls:
        source = ImageSource(url=url, alt_text=alt)
        result = create_image(session, product_id, source)
        results.append({"source": url, "image_id": result.image_id, "status": result.status})

    for file_path in files:
        source = ImageSource(file_path=Path(file_path), alt_text=alt)
        result = create_image(session, product_id, source)
        results.append({"source": str(file_path), "image_id": result.image_id, "status": result.status})

    return results


def _output_add_image_results(results: list[dict[str, str]], output_format: OutputFormat) -> None:
    """Output image creation results."""
    if output_format == OutputFormat.JSON:
        safe_console.echo(orjson.dumps({"images": results}, option=orjson.OPT_INDENT_2).decode())
    else:
        safe_console.echo(f"\n✓ Added {len(results)} image(s)")
        for img_result in results:
            safe_console.echo(f"  - {img_result['source']}: {img_result['image_id']} ({img_result['status']})")


def _parse_image_ids(order: str) -> list[str]:
    """Parse comma-separated image IDs."""
    return [img_id.strip() for img_id in order.split(",") if img_id.strip()]


def _output_reorder_result(result: ImageReorderResult, output_format: OutputFormat) -> None:
    """Output reorder result in requested format."""
    if output_format == OutputFormat.JSON:
        data = {"product_id": result.product_id, "job_id": result.job_id}
        safe_console.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
    else:
        safe_console.echo(f"✓ Images reordered for product {result.product_id}")
        if result.job_id:
            safe_console.echo(f"  Job ID: {result.job_id} (async operation)")


# =============================================================================
# Command Runners
# =============================================================================


def _exit_product_not_found(product_id: str) -> NoReturn:
    """Report a missing product and exit 1 without chaining the lookup error."""
    safe_console.echo(f"Product not found: {product_id}", err=True)
    raise SystemExit(1) from None


def _exit_on_shopify_error(exc: Exception, credentials: Any, get_fix_suggestion: Any) -> NoReturn:
    """Report an authentication or GraphQL error with its fix suggestion and exit 1."""
    safe_console.echo(f"Error: {exc}", err=True)
    safe_console.echo(get_fix_suggestion(exc, credentials), err=True)
    raise SystemExit(1) from exc


def _output_delete_image_result(result: ImageDeleteResult, output_format: OutputFormat) -> None:
    """Output image deletion result in requested format."""
    if output_format == OutputFormat.JSON:
        data = {
            "product_id": result.product_id,
            "deleted_image_ids": result.deleted_image_ids,
            "deleted_media_ids": result.deleted_media_ids,
        }
        safe_console.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
    else:
        safe_console.echo(f"✓ Image deleted from product {result.product_id}")


def _output_update_image_result(result: ImageCreateSuccess, output_format: OutputFormat) -> None:
    """Output image update result in requested format."""
    if output_format == OutputFormat.JSON:
        data = {
            "image_id": result.image_id,
            "url": result.url,
            "alt_text": result.alt_text,
            "status": result.status,
        }
        safe_console.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
    else:
        safe_console.echo(f"✓ Image updated: {result.image_id}")
        safe_console.echo(f"  Alt text: {result.alt_text}")


def _run_add_image(
    ctx: click.Context,
    *,
    product_id: str,
    urls: tuple[str, ...],
    files: tuple[str, ...],
    alt: str | None,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Add images to a product (body of ``add-image``)."""
    if not urls and not files:
        safe_console.echo("Error: At least one --url or --file is required", err=True)
        raise SystemExit(1)

    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {"command": "add-image", "profile": effective_profile, "product_id": product_id}

    with lib_log_rich.runtime.bind(job_id="cli-add-image", extra=extra):
        logger.info("Adding image(s) to product '%s': %s URL(s), %s file(s)", product_id, len(urls), len(files))

        credentials = get_credentials_or_exit(config)

        try:
            with shopify_session(credentials) as session:
                results = _create_images_from_sources(session, product_id, urls, files, alt)
                logger.info("Images added: %s image(s)", len(results))
                _output_add_image_results(results, output_format)
        except ProductNotFoundError:
            _exit_product_not_found(product_id)
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


def _run_delete_image(
    ctx: click.Context,
    *,
    product_id: str,
    image_id: str,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Delete an image from a product (body of ``delete-image``)."""
    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {
        "command": "delete-image",
        "profile": effective_profile,
        "product_id": product_id,
        "image_id": image_id,
    }

    with lib_log_rich.runtime.bind(job_id="cli-delete-image", extra=extra):
        logger.info("Deleting image '%s' from product '%s'", image_id, product_id)

        credentials = get_credentials_or_exit(config)

        try:
            with shopify_session(credentials) as session:
                result = delete_image(session, product_id, image_id)
                deleted_ids = result.deleted_image_ids + result.deleted_media_ids
                logger.info("Image deleted: %s", deleted_ids)
                _output_delete_image_result(result, output_format)
        except ProductNotFoundError:
            _exit_product_not_found(product_id)
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


def _run_update_image(
    ctx: click.Context,
    *,
    product_id: str,
    image_id: str,
    alt: str,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Update an image's alt text (body of ``update-image``)."""
    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {
        "command": "update-image",
        "profile": effective_profile,
        "product_id": product_id,
        "image_id": image_id,
    }

    with lib_log_rich.runtime.bind(job_id="cli-update-image", extra=extra):
        logger.info("Updating image '%s' on product '%s'", image_id, product_id)

        credentials = get_credentials_or_exit(config)

        try:
            with shopify_session(credentials) as session:
                image_update = ImageUpdate(alt_text=alt)
                result = update_image(session, product_id, image_id, image_update)
                logger.info("Image updated: id='%s'", result.image_id)
                _output_update_image_result(result, output_format)
        except ProductNotFoundError:
            _exit_product_not_found(product_id)
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


def _run_reorder_images(
    ctx: click.Context,
    *,
    product_id: str,
    order: str,
    output_format: OutputFormat,
    profile: str | None,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Reorder a product's images (body of ``reorder-images``)."""
    image_ids = _parse_image_ids(order)
    if len(image_ids) < _MIN_IMAGES_FOR_REORDER:
        safe_console.echo("Error: At least 2 image IDs required for reordering", err=True)
        raise SystemExit(1)

    config, effective_profile = get_effective_config_and_profile(ctx, profile)
    extra = {"command": "reorder-images", "profile": effective_profile, "product_id": product_id}

    with lib_log_rich.runtime.bind(job_id="cli-reorder-images", extra=extra):
        logger.info("Reordering %s image(s) for product '%s'", len(image_ids), product_id)

        credentials = get_credentials_or_exit(config)

        try:
            with shopify_session(credentials) as session:
                result = reorder_images(session, product_id, image_ids)
                logger.info("Images reordered for product '%s' (job_id='%s')", result.product_id, result.job_id)
                _output_reorder_result(result, output_format)
        except ProductNotFoundError:
            _exit_product_not_found(product_id)
        except (AuthenticationError, GraphQLError) as exc:
            _exit_on_shopify_error(exc, credentials, get_fix_suggestion)


# =============================================================================
# CLI Commands
# =============================================================================


def register_image_commands(
    cli_group: click.Group,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Register image operation commands on the CLI group.

    Args:
        cli_group: The Click group to register commands on.
        get_credentials_or_exit: Function to get credentials from config.
        get_fix_suggestion: Function to get fix suggestions for errors.
    """

    @cli_group.command("add-image", context_settings=CLICK_CONTEXT_SETTINGS)
    @argument("product_id", type=str)
    @option("--url", "urls", multiple=True, help="Image URL (repeatable)")
    @option("--file", "files", multiple=True, type=click.Path(exists=True), help="Local file path (repeatable)")
    @option("--alt", type=str, default=None, help="Alt text (applies to all images)")
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_add_image(
        ctx: click.Context,
        *,
        product_id: str,
        urls: tuple[str, ...],
        files: tuple[str, ...],
        alt: str | None,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Add image(s) to a product from URL or local file."""
        _run_add_image(
            ctx,
            product_id=product_id,
            urls=urls,
            files=files,
            alt=alt,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
        )

    @cli_group.command("delete-image", context_settings=CLICK_CONTEXT_SETTINGS)
    @argument("product_id", type=str)
    @argument("image_id", type=str)
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.HUMAN,
        help="Output format (default: human)",
    )
    @option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_delete_image(
        ctx: click.Context,
        product_id: str,
        image_id: str,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Delete an image from a product.

        PRODUCT_ID and IMAGE_ID can be Shopify GIDs or numeric IDs.

        Examples:

            lib-shopify-graphql delete-image 123456789 111222333

            lib-shopify-graphql delete-image 123456789 gid://shopify/ProductImage/111222333
        """
        _run_delete_image(
            ctx,
            product_id=product_id,
            image_id=image_id,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
        )

    @cli_group.command("update-image", context_settings=CLICK_CONTEXT_SETTINGS)
    @argument("product_id", type=str)
    @argument("image_id", type=str)
    @option("--alt", type=str, required=True, help="New alt text for the image")
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_update_image(
        ctx: click.Context,
        *,
        product_id: str,
        image_id: str,
        alt: str,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Update image metadata (alt text).

        PRODUCT_ID and IMAGE_ID can be Shopify GIDs or numeric IDs.

        Examples:

            lib-shopify-graphql update-image 123456789 111222333 --alt "Front view of product"
        """
        _run_update_image(
            ctx,
            product_id=product_id,
            image_id=image_id,
            alt=alt,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
        )

    @cli_group.command("reorder-images", context_settings=CLICK_CONTEXT_SETTINGS)
    @argument("product_id", type=str)
    @option("--order", type=str, required=True, help="Comma-separated image IDs in desired order")
    @option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.HUMAN,
        help="Output format (default: human)",
    )
    @option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_reorder_images(
        ctx: click.Context,
        product_id: str,
        order: str,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Reorder product images."""
        _run_reorder_images(
            ctx,
            product_id=product_id,
            order=order,
            output_format=output_format,
            profile=profile,
            get_credentials_or_exit=get_credentials_or_exit,
            get_fix_suggestion=get_fix_suggestion,
        )


__all__ = [
    # Internal functions exported for tests
    "_output_reorder_result",
    "_parse_image_ids",
    "register_image_commands",
]
