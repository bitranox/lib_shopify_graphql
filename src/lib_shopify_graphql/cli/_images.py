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
from typing import TYPE_CHECKING, Any

import lib_log_rich.runtime
import orjson
import rich_click as click

from ..enums import OutputFormat
from ..exceptions import AuthenticationError, GraphQLError, ProductNotFoundError
from ..models import ImageReorderResult, ImageSource, ImageUpdate
from ..shopify_client import (
    create_image,
    delete_image,
    login,
    logout,
    reorder_images,
    update_image,
)
from ._common import CLICK_CONTEXT_SETTINGS, EnumChoice, get_effective_config_and_profile

if TYPE_CHECKING:
    from ..shopify_client import ShopifySession

logger = logging.getLogger(__name__)


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
        click.echo(orjson.dumps({"images": results}, option=orjson.OPT_INDENT_2).decode())
    else:
        click.echo(f"\n✓ Added {len(results)} image(s)")
        for img_result in results:
            click.echo(f"  - {img_result['source']}: {img_result['image_id']} ({img_result['status']})")


def _parse_image_ids(order: str) -> list[str]:
    """Parse comma-separated image IDs."""
    return [img_id.strip() for img_id in order.split(",") if img_id.strip()]


def _output_reorder_result(result: ImageReorderResult, output_format: OutputFormat) -> None:
    """Output reorder result in requested format."""
    if output_format == OutputFormat.JSON:
        data = {"product_id": result.product_id, "job_id": result.job_id}
        click.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
    else:
        click.echo(f"✓ Images reordered for product {result.product_id}")
        if result.job_id:
            click.echo(f"  Job ID: {result.job_id} (async operation)")


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
    @click.argument("product_id", type=str)
    @click.option("--url", "urls", multiple=True, help="Image URL (repeatable)")
    @click.option("--file", "files", multiple=True, type=click.Path(exists=True), help="Local file path (repeatable)")
    @click.option("--alt", type=str, default=None, help="Alt text (applies to all images)")
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @click.option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_add_image(
        ctx: click.Context,
        product_id: str,
        urls: tuple[str, ...],
        files: tuple[str, ...],
        alt: str | None,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Add image(s) to a product from URL or local file."""
        if not urls and not files:
            click.echo("Error: At least one --url or --file is required", err=True)
            raise SystemExit(1)

        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "add-image", "profile": effective_profile, "product_id": product_id}

        with lib_log_rich.runtime.bind(job_id="cli-add-image", extra=extra):
            logger.info(f"Adding image(s) to product '{product_id}': {len(urls)} URL(s), {len(files)} file(s)")

            credentials = get_credentials_or_exit(config)

            session = None
            try:
                session = login(credentials)
                results = _create_images_from_sources(session, product_id, urls, files, alt)
                logger.info(f"Images added: {len(results)} image(s)")
                _output_add_image_results(results, output_format)
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

    @cli_group.command("delete-image", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.argument("product_id", type=str)
    @click.argument("image_id", type=str)
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.HUMAN,
        help="Output format (default: human)",
    )
    @click.option("--profile", type=str, default=None, help="Override profile from root command")
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
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {
            "command": "delete-image",
            "profile": effective_profile,
            "product_id": product_id,
            "image_id": image_id,
        }

        with lib_log_rich.runtime.bind(job_id="cli-delete-image", extra=extra):
            logger.info(f"Deleting image '{image_id}' from product '{product_id}'")

            credentials = get_credentials_or_exit(config)

            session = None
            try:
                session = login(credentials)
                result = delete_image(session, product_id, image_id)
                deleted_ids = result.deleted_image_ids + result.deleted_media_ids
                logger.info(f"Image deleted: {deleted_ids}")

                if output_format == OutputFormat.JSON:
                    data = {
                        "product_id": result.product_id,
                        "deleted_image_ids": result.deleted_image_ids,
                        "deleted_media_ids": result.deleted_media_ids,
                    }
                    click.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
                else:
                    click.echo(f"✓ Image deleted from product {result.product_id}")

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

    @cli_group.command("update-image", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.argument("product_id", type=str)
    @click.argument("image_id", type=str)
    @click.option("--alt", type=str, required=True, help="New alt text for the image")
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.JSON,
        help="Output format (default: json)",
    )
    @click.option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_update_image(
        ctx: click.Context,
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
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {
            "command": "update-image",
            "profile": effective_profile,
            "product_id": product_id,
            "image_id": image_id,
        }

        with lib_log_rich.runtime.bind(job_id="cli-update-image", extra=extra):
            logger.info(f"Updating image '{image_id}' on product '{product_id}'")

            credentials = get_credentials_or_exit(config)

            session = None
            try:
                session = login(credentials)
                image_update = ImageUpdate(alt_text=alt)
                result = update_image(session, product_id, image_id, image_update)
                logger.info(f"Image updated: id='{result.image_id}'")

                if output_format == OutputFormat.JSON:
                    data = {
                        "image_id": result.image_id,
                        "url": result.url,
                        "alt_text": result.alt_text,
                        "status": result.status,
                    }
                    click.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())
                else:
                    click.echo(f"✓ Image updated: {result.image_id}")
                    click.echo(f"  Alt text: {result.alt_text}")

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

    @cli_group.command("reorder-images", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.argument("product_id", type=str)
    @click.option("--order", type=str, required=True, help="Comma-separated image IDs in desired order")
    @click.option(
        "--format",
        "output_format",
        type=EnumChoice(OutputFormat),
        default=OutputFormat.HUMAN,
        help="Output format (default: human)",
    )
    @click.option("--profile", type=str, default=None, help="Override profile from root command")
    @click.pass_context
    def cli_reorder_images(
        ctx: click.Context,
        product_id: str,
        order: str,
        output_format: OutputFormat,
        profile: str | None,
    ) -> None:
        """Reorder product images."""
        image_ids = _parse_image_ids(order)
        if len(image_ids) < 2:
            click.echo("Error: At least 2 image IDs required for reordering", err=True)
            raise SystemExit(1)

        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "reorder-images", "profile": effective_profile, "product_id": product_id}

        with lib_log_rich.runtime.bind(job_id="cli-reorder-images", extra=extra):
            logger.info(f"Reordering {len(image_ids)} image(s) for product '{product_id}'")

            credentials = get_credentials_or_exit(config)

            session = None
            try:
                session = login(credentials)
                result = reorder_images(session, product_id, image_ids)
                logger.info(f"Images reordered for product '{result.product_id}' (job_id='{result.job_id}')")
                _output_reorder_result(result, output_format)
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
    "register_image_commands",
    # Internal functions exported for tests
    "_output_reorder_result",
    "_parse_image_ids",
]
