"""Image management operations for Shopify products.

This module provides CRUD operations for product images/media:
    - :func:`create_image`: Create a single image from URL or file.
    - :func:`create_images`: Batch create multiple images.
    - :func:`update_image`: Update image metadata (alt text).
    - :func:`delete_image`: Delete a single image.
    - :func:`delete_images`: Batch delete multiple images.
    - :func:`reorder_images`: Reorder product images.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any, TypedDict, cast

import httpx
from pydantic import BaseModel, ConfigDict

from ..adapters.mutations import (
    PRODUCT_CREATE_MEDIA_MUTATION,
    PRODUCT_DELETE_MEDIA_MUTATION,
    PRODUCT_REORDER_MEDIA_MUTATION,
    PRODUCT_UPDATE_MEDIA_MUTATION,
    STAGED_UPLOADS_CREATE_MUTATION,
)
from ..adapters.parsers import (
    format_graphql_errors,
    parse_graphql_errors,
    parse_media_from_mutation,
    parse_media_user_errors,
    parse_staged_upload_target,
)
from ..exceptions import (
    GraphQLError,
    ImageNotFoundError,
    ImageUploadError,
    SessionNotActiveError,
)
from ..models import (
    ImageCreateFailure,
    ImageCreateResult,
    ImageCreateSuccess,
    ImageDeleteResult,
    ImageReorderResult,
    ImageSource,
    ImageUpdate,
    MediaStatus,
    StagedUploadTarget,
)
from ._common import _normalize_media_gid, _normalize_product_gid
from ._session import ShopifySession

# =============================================================================
# Internal TypedDicts for Raw GraphQL Response Parsing
# =============================================================================


class _RawMediaUserError(TypedDict, total=False):
    """Raw media user error from GraphQL mutation response."""

    code: str
    field: list[str]
    message: str


class _RawMediaData(TypedDict, total=False):
    """Raw media data from GraphQL mutation response."""

    id: str
    alt: str | None
    status: str | None
    image: dict[str, Any] | None


# =============================================================================
# Internal Pydantic Models for Parsed GraphQL Responses
# =============================================================================


class _ParsedMediaUserError(BaseModel):
    """Internal model for parsed media user errors from GraphQL mutations."""

    model_config = ConfigDict(frozen=True)

    code: str = "UNKNOWN"
    field: str = ""
    message: str = "Unknown error"


def _parse_media_user_errors_typed(
    errors: list[_RawMediaUserError],
) -> list[_ParsedMediaUserError]:
    """Parse media user errors from mutation response into typed models.

    Args:
        errors: Raw error list from GraphQL response.

    Returns:
        List of typed _ParsedMediaUserError models.
    """
    # Cast TypedDict list to dict list for parser compatibility
    parsed = parse_media_user_errors(cast(list[dict[str, Any]], errors))
    return [
        _ParsedMediaUserError(
            code=e.get("code", "UNKNOWN"),
            field=e.get("field", ""),
            message=e.get("message", "Unknown error"),
        )
        for e in parsed
    ]


logger = logging.getLogger(__name__)


# =============================================================================
# Internal Helpers
# =============================================================================


def _get_mime_type(file_path: Path) -> str:
    """Get MIME type for a file.

    Args:
        file_path: Path to the file.

    Returns:
        MIME type string (defaults to 'image/jpeg' if unknown).
    """
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "image/jpeg"


def _create_staged_upload(
    session: ShopifySession,
    file_path: Path,
) -> StagedUploadTarget:
    """Create a staged upload target for a file.

    Args:
        session: Active Shopify session.
        file_path: Path to the file to upload.

    Returns:
        StagedUploadTarget with upload URL and resource URL.

    Raises:
        ImageUploadError: If staged upload creation fails.
    """
    file_size = file_path.stat().st_size
    mime_type = _get_mime_type(file_path)

    input_data = [
        {
            "filename": file_path.name,
            "mimeType": mime_type,
            "fileSize": str(file_size),
            "resource": "IMAGE",
        }
    ]

    data = session.execute_graphql(STAGED_UPLOADS_CREATE_MUTATION, variables={"input": input_data})

    if "errors" in data:
        parsed_errors = parse_graphql_errors(data["errors"])
        raise ImageUploadError(
            str(file_path),
            f"Failed to create staged upload: {format_graphql_errors(parsed_errors)}",
        )

    mutation_data = data.get("data", {}).get("stagedUploadsCreate", {})
    user_errors = mutation_data.get("userErrors", [])
    if user_errors:
        raise ImageUploadError(str(file_path), f"Staged upload failed: {user_errors[0]['message']}")

    targets = mutation_data.get("stagedTargets", [])
    if not targets:
        raise ImageUploadError(str(file_path), "No staged upload target returned")

    return parse_staged_upload_target(targets[0])


def _upload_file_to_staged_target(
    staged_target: StagedUploadTarget,
    file_path: Path,
) -> None:
    """Upload a file to a staged upload target.

    Handles both Google Cloud Storage (PUT) and S3-style (POST multipart) uploads.
    GCS signed URLs have X-Goog-* query parameters and require PUT requests.
    S3-style URLs require POST with multipart form data.

    Args:
        staged_target: The staged upload target from Shopify.
        file_path: Path to the file to upload.

    Raises:
        ImageUploadError: If the upload fails.
    """
    mime_type = _get_mime_type(file_path)
    with file_path.open("rb") as f:
        file_content = f.read()

    try:
        # Check if this is a Google Cloud Storage signed URL
        if "X-Goog-" in staged_target.url or "storage.googleapis.com" in staged_target.url:
            # GCS uses PUT with file as body
            response = httpx.put(
                staged_target.url,
                content=file_content,
                headers={"Content-Type": mime_type},
                timeout=60.0,
            )
        else:
            # S3-style uses POST with multipart form data
            files: dict[str, Any] = {}
            for param in staged_target.parameters:
                files[param.name] = (None, param.value)
            files["file"] = (file_path.name, file_content, mime_type)

            response = httpx.post(
                staged_target.url,
                files=files,
                timeout=60.0,
            )

        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ImageUploadError(str(file_path), f"File upload failed: {exc}") from exc


def _build_media_input(alt_text: str | None, source_url: str) -> dict[str, Any]:
    """Build a media input dict for the GraphQL mutation."""
    return {
        "alt": alt_text or "",
        "mediaContentType": "IMAGE",
        "originalSource": source_url,
    }


def _prepare_file_source(
    session: ShopifySession,
    source: ImageSource,
    failed: list[ImageCreateFailure],
) -> str | None:
    """Prepare a file source by uploading to staged target.

    Returns:
        Resource URL if successful, None if failed.
    """
    file_path = source.file_path
    if file_path is None:
        return None

    try:
        if not file_path.exists():
            raise ImageUploadError(str(file_path), "File does not exist")

        staged_target = _create_staged_upload(session, file_path)
        _upload_file_to_staged_target(staged_target, file_path)
        return staged_target.resource_url
    except ImageUploadError as exc:
        failed.append(ImageCreateFailure(source=source, error=exc.message))
        return None


def _prepare_media_inputs(
    session: ShopifySession,
    sources: list[ImageSource],
    failed: list[ImageCreateFailure],
) -> tuple[list[dict[str, Any]], list[tuple[ImageSource, str | None]]]:
    """Prepare media inputs from sources.

    Returns:
        Tuple of (media_inputs, source_map).
    """
    media_inputs: list[dict[str, Any]] = []
    source_map: list[tuple[ImageSource, str | None]] = []

    for source in sources:
        if source.url:
            media_inputs.append(_build_media_input(source.alt_text, source.url))
            source_map.append((source, source.url))
        elif source.file_path:
            resource_url = _prepare_file_source(session, source, failed)
            if resource_url:
                media_inputs.append(_build_media_input(source.alt_text, resource_url))
            source_map.append((source, resource_url))

    return media_inputs, source_map


def _handle_mutation_graphql_errors(
    data: dict[str, Any],
    source_map: list[tuple[ImageSource, str | None]],
    failed: list[ImageCreateFailure],
) -> bool:
    """Handle GraphQL-level errors from mutation.

    Returns:
        True if errors were found (processing should stop).
    """
    if "errors" not in data:
        return False

    parsed_errors = parse_graphql_errors(data["errors"])
    error_message = format_graphql_errors(parsed_errors)

    for source, resource_url in source_map:
        if resource_url is not None:
            failed.append(ImageCreateFailure(source=source, error=error_message))

    return True


def _handle_media_user_errors(
    media_errors: list[_RawMediaUserError],
    sources: list[ImageSource],
    failed: list[ImageCreateFailure],
) -> bool:
    """Handle media user errors from mutation.

    Returns:
        True if errors were found.
    """
    if not media_errors:
        return False

    parsed_media_errors = _parse_media_user_errors_typed(media_errors)
    for error in parsed_media_errors:
        failed.append(
            ImageCreateFailure(
                source=sources[0],  # Best effort mapping
                error=error.message,
                error_code=error.code if error.code != "UNKNOWN" else None,
            )
        )
    return True


def _map_created_media(
    created_media: list[_RawMediaData],
    source_map: list[tuple[ImageSource, str | None]],
    succeeded: list[ImageCreateSuccess],
) -> None:
    """Map created media to success results."""
    media_index = 0
    for _source, resource_url in source_map:
        if resource_url is not None and media_index < len(created_media):
            # Cast TypedDict to dict for parser compatibility
            parsed = parse_media_from_mutation(cast(dict[str, Any], created_media[media_index]))
            succeeded.append(
                ImageCreateSuccess(
                    image_id=parsed["image_id"],
                    url=parsed.get("url"),
                    alt_text=parsed.get("alt_text"),
                    status=parsed.get("status", MediaStatus.PROCESSING),
                )
            )
            media_index += 1


def _create_media_from_sources(
    session: ShopifySession,
    product_id: str,
    sources: list[ImageSource],
) -> ImageCreateResult:
    """Create media for a product from multiple sources.

    Args:
        session: Active Shopify session.
        product_id: Product GID.
        sources: List of image sources.

    Returns:
        ImageCreateResult with succeeded and failed lists.
    """
    succeeded: list[ImageCreateSuccess] = []
    failed: list[ImageCreateFailure] = []

    media_inputs, source_map = _prepare_media_inputs(session, sources, failed)

    if media_inputs:
        data = session.execute_graphql(
            PRODUCT_CREATE_MEDIA_MUTATION,
            variables={"productId": product_id, "media": media_inputs},
        )

        if not _handle_mutation_graphql_errors(data, source_map, failed):
            mutation_data = data.get("data", {}).get("productCreateMedia", {})
            media_errors = mutation_data.get("mediaUserErrors", [])
            created_media = mutation_data.get("media", [])

            if not _handle_media_user_errors(media_errors, sources, failed):
                _map_created_media(created_media, source_map, succeeded)

    return ImageCreateResult(succeeded=succeeded, failed=failed, product_id=product_id)


# =============================================================================
# Public API
# =============================================================================


def create_image(
    session: ShopifySession,
    product_id: str,
    source: ImageSource,
) -> ImageCreateSuccess:
    """Create a single product image.

    Args:
        session: Active Shopify session.
        product_id: Product GID or numeric ID.
        source: Image source (URL or file path).

    Returns:
        ImageCreateSuccess with the created image details.

    Raises:
        SessionNotActiveError: If the session is not active.
        ImageUploadError: If file upload fails.
        GraphQLError: If the mutation fails.

    Example:
        >>> from lib_shopify_graphql import login, create_image, ImageSource
        >>> session = login(credentials)  # doctest: +SKIP
        >>> success = create_image(session, product_id, ImageSource(url="https://example.com/img.jpg"))  # doctest: +SKIP
        >>> print(success.image_id)  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    product_gid = _normalize_product_gid(product_id)

    logger.info(f"Creating image for product '{product_gid}' from {source}")

    result = _create_media_from_sources(session, product_gid, [source])

    if result.failed:
        failure = result.failed[0]
        if source.file_path:
            raise ImageUploadError(str(source.file_path), failure.error)
        raise GraphQLError(failure.error, query=PRODUCT_CREATE_MEDIA_MUTATION)

    if not result.succeeded:
        raise GraphQLError("No image was created", query=PRODUCT_CREATE_MEDIA_MUTATION)

    return result.succeeded[0]


def create_images(
    session: ShopifySession,
    product_id: str,
    sources: list[ImageSource],
) -> ImageCreateResult:
    """Create multiple product images in batch.

    Args:
        session: Active Shopify session.
        product_id: Product GID or numeric ID.
        sources: List of image sources.

    Returns:
        ImageCreateResult with succeeded and failed lists.

    Raises:
        SessionNotActiveError: If the session is not active.

    Example:
        >>> from lib_shopify_graphql import login, create_images, ImageSource
        >>> session = login(credentials)  # doctest: +SKIP
        >>> result = create_images(session, product_id, [
        ...     ImageSource(url="https://example.com/1.jpg"),
        ...     ImageSource(url="https://example.com/2.jpg"),
        ... ])  # doctest: +SKIP
        >>> print(f"Created {result.success_count}, failed {result.failure_count}")  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    product_gid = _normalize_product_gid(product_id)

    logger.info(f"Creating {len(sources)} image(s) for product '{product_gid}'")

    return _create_media_from_sources(session, product_gid, sources)


def _check_update_graphql_errors(data: dict[str, Any]) -> None:
    """Check for GraphQL errors in update response."""
    if "errors" not in data:
        return
    parsed_errors = parse_graphql_errors(data["errors"])
    raise GraphQLError(
        f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
        errors=parsed_errors,
        query=PRODUCT_UPDATE_MEDIA_MUTATION,
    )


def _check_update_media_errors(media_errors: list[_RawMediaUserError], image_gid: str) -> None:
    """Check for media errors in update response."""
    if not media_errors:
        return
    # Cast TypedDict list to dict list for parser compatibility
    parsed_errors = parse_media_user_errors(cast(list[dict[str, Any]], media_errors))
    if any(e.get("code") == "MEDIA_DOES_NOT_EXIST" for e in parsed_errors):
        raise ImageNotFoundError(image_gid)
    raise GraphQLError(f"Media update failed: {parsed_errors[0]['message']}", query=PRODUCT_UPDATE_MEDIA_MUTATION)


def update_image(
    session: ShopifySession,
    product_id: str,
    image_id: str,
    update: ImageUpdate,
) -> ImageCreateSuccess:
    """Update image metadata (alt text)."""
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    product_gid = _normalize_product_gid(product_id)
    image_gid = _normalize_media_gid(image_id)

    logger.info(f"Updating image '{image_gid}' on product '{product_gid}'")

    set_fields = update.get_set_fields()
    if not set_fields:
        raise ValueError("No fields to update")

    media_input: dict[str, str] = {"id": image_gid}
    if "alt_text" in set_fields:
        media_input["alt"] = set_fields["alt_text"]  # type: ignore[assignment]

    data = session.execute_graphql(
        PRODUCT_UPDATE_MEDIA_MUTATION,
        variables={"productId": product_gid, "media": [media_input]},
    )

    _check_update_graphql_errors(data)

    mutation_data = data.get("data", {}).get("productUpdateMedia", {})
    _check_update_media_errors(mutation_data.get("mediaUserErrors", []), image_gid)

    media_list = mutation_data.get("media", [])
    if not media_list:
        raise ImageNotFoundError(image_gid)

    parsed = parse_media_from_mutation(media_list[0])
    return ImageCreateSuccess(
        image_id=parsed["image_id"],
        url=parsed.get("url"),
        alt_text=parsed.get("alt_text"),
        status=parsed.get("status", MediaStatus.READY),
    )


def delete_image(
    session: ShopifySession,
    product_id: str,
    image_id: str,
) -> ImageDeleteResult:
    """Delete a single product image.

    Args:
        session: Active Shopify session.
        product_id: Product GID or numeric ID.
        image_id: Image/media GID or numeric ID.

    Returns:
        ImageDeleteResult with deleted IDs.

    Raises:
        SessionNotActiveError: If the session is not active.
        ImageNotFoundError: If the image does not exist.
        GraphQLError: If the mutation fails.

    Example:
        >>> from lib_shopify_graphql import login, delete_image
        >>> session = login(credentials)  # doctest: +SKIP
        >>> result = delete_image(session, product_id, image_id)  # doctest: +SKIP
    """
    return delete_images(session, product_id, [image_id])


def delete_images(
    session: ShopifySession,
    product_id: str,
    image_ids: list[str],
) -> ImageDeleteResult:
    """Delete multiple product images.

    Args:
        session: Active Shopify session.
        product_id: Product GID or numeric ID.
        image_ids: List of image/media GIDs or numeric IDs.

    Returns:
        ImageDeleteResult with deleted IDs.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the mutation fails.

    Example:
        >>> from lib_shopify_graphql import login, delete_images
        >>> session = login(credentials)  # doctest: +SKIP
        >>> result = delete_images(session, product_id, [image_id_1, image_id_2])  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    product_gid = _normalize_product_gid(product_id)
    media_gids = [_normalize_media_gid(img_id) for img_id in image_ids]

    logger.info(f"Deleting {len(media_gids)} image(s) from product '{product_gid}': {media_gids}")

    data = session.execute_graphql(
        PRODUCT_DELETE_MEDIA_MUTATION,
        variables={"productId": product_gid, "mediaIds": media_gids},
    )

    if "errors" in data:
        parsed_errors = parse_graphql_errors(data["errors"])
        raise GraphQLError(
            f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
            errors=parsed_errors,
            query=PRODUCT_DELETE_MEDIA_MUTATION,
        )

    mutation_data = data.get("data", {}).get("productDeleteMedia", {})
    media_errors = mutation_data.get("mediaUserErrors", [])

    if media_errors:
        parsed_errors = parse_media_user_errors(media_errors)
        raise GraphQLError(
            f"Media delete failed: {parsed_errors[0]['message']}",
            query=PRODUCT_DELETE_MEDIA_MUTATION,
        )

    return ImageDeleteResult(
        deleted_media_ids=mutation_data.get("deletedMediaIds", []),
        deleted_image_ids=mutation_data.get("deletedProductImageIds", []),
        product_id=product_gid,
    )


def reorder_images(
    session: ShopifySession,
    product_id: str,
    image_ids: list[str],
) -> ImageReorderResult:
    """Reorder product images.

    The images will be reordered to match the order of image_ids.
    This is an async operation in Shopify.

    Args:
        session: Active Shopify session.
        product_id: Product GID or numeric ID.
        image_ids: List of image/media GIDs in desired order.

    Returns:
        ImageReorderResult with job_id for tracking.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the mutation fails.

    Example:
        >>> from lib_shopify_graphql import login, reorder_images
        >>> session = login(credentials)  # doctest: +SKIP
        >>> result = reorder_images(session, product_id, [image_3, image_1, image_2])  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    product_gid = _normalize_product_gid(product_id)
    media_gids = [_normalize_media_gid(img_id) for img_id in image_ids]

    logger.info(f"Reordering {len(media_gids)} image(s) for product '{product_gid}'")

    # Build moves array (newPosition must be string for Shopify's UnsignedInt64)
    moves = [{"id": media_id, "newPosition": str(position)} for position, media_id in enumerate(media_gids)]

    data = session.execute_graphql(
        PRODUCT_REORDER_MEDIA_MUTATION,
        variables={"id": product_gid, "moves": moves},
    )

    if "errors" in data:
        parsed_errors = parse_graphql_errors(data["errors"])
        raise GraphQLError(
            f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
            errors=parsed_errors,
            query=PRODUCT_REORDER_MEDIA_MUTATION,
        )

    mutation_data = data.get("data", {}).get("productReorderMedia", {})
    media_errors = mutation_data.get("mediaUserErrors", [])

    if media_errors:
        parsed_errors = parse_media_user_errors(media_errors)
        raise GraphQLError(
            f"Media reorder failed: {parsed_errors[0]['message']}",
            query=PRODUCT_REORDER_MEDIA_MUTATION,
        )

    job = mutation_data.get("job", {})
    return ImageReorderResult(
        job_id=job.get("id") if job else None,
        product_id=product_gid,
    )


__all__ = [
    "create_image",
    "create_images",
    "delete_image",
    "delete_images",
    "reorder_images",
    "update_image",
]
