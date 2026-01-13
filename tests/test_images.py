"""Tests for image management functionality.

Tests for image models, parsers, and API functions:
- ImageSource validation (URL vs file_path)
- ImageUpdate partial update model
- Image result models
- Media parsers
- Image API functions with mocked GraphQL
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib_shopify_graphql import (
    ImageCreateFailure,
    ImageCreateResult,
    ImageCreateSuccess,
    ImageDeleteResult,
    ImageNotFoundError,
    ImageReorderResult,
    ImageSource,
    ImageUpdate,
    ImageUploadError,
    MediaStatus,
    SessionNotActiveError,
    StagedUploadTarget,
)
from lib_shopify_graphql.models._images import StagedUploadParameter
from lib_shopify_graphql.adapters.parsers import (
    parse_media_from_mutation,
    parse_media_user_errors,
    parse_staged_upload_target,
)
from lib_shopify_graphql.models._internal import UNSET


# =============================================================================
# ImageSource Model Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestImageSourceValidation:
    """ImageSource validates that exactly one source is provided."""

    def test_accepts_url_source(self) -> None:
        """URL source is accepted without file_path."""
        source = ImageSource(url="https://example.com/image.jpg")

        assert source.url == "https://example.com/image.jpg"
        assert source.file_path is None

    def test_accepts_file_path_source(self) -> None:
        """File path source is accepted without URL."""
        source = ImageSource(file_path=Path("/path/to/image.jpg"))

        assert source.file_path == Path("/path/to/image.jpg")
        assert source.url is None

    def test_accepts_alt_text_with_url(self) -> None:
        """Alt text can be provided with URL source."""
        source = ImageSource(url="https://example.com/image.jpg", alt_text="Front view")

        assert source.alt_text == "Front view"

    def test_accepts_alt_text_with_file_path(self) -> None:
        """Alt text can be provided with file path source."""
        source = ImageSource(file_path=Path("/path/to/image.jpg"), alt_text="Side view")

        assert source.alt_text == "Side view"

    def test_rejects_both_url_and_file_path(self) -> None:
        """Providing both URL and file_path raises ValueError."""
        with pytest.raises(ValueError, match="Provide either url or file_path, not both"):
            ImageSource(url="https://example.com/image.jpg", file_path=Path("/path/to/image.jpg"))

    def test_rejects_neither_url_nor_file_path(self) -> None:
        """Providing neither URL nor file_path raises ValueError."""
        with pytest.raises(ValueError, match="Either url or file_path must be provided"):
            ImageSource()

    def test_is_frozen(self) -> None:
        """ImageSource is immutable."""
        source = ImageSource(url="https://example.com/image.jpg")

        with pytest.raises(Exception):  # ValidationError for frozen model
            source.url = "https://other.com/image.jpg"  # type: ignore[misc]


# =============================================================================
# ImageUpdate Model Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestImageUpdateModel:
    """ImageUpdate handles partial updates with UNSET sentinel."""

    def test_defaults_to_unset(self) -> None:
        """All fields default to UNSET."""
        update = ImageUpdate()

        assert update.alt_text is UNSET

    def test_accepts_alt_text_value(self) -> None:
        """Alt text can be set to a value."""
        update = ImageUpdate(alt_text="New description")

        assert update.alt_text == "New description"

    def test_accepts_none_to_clear(self) -> None:
        """Alt text can be set to None to clear it."""
        update = ImageUpdate(alt_text=None)

        assert update.alt_text is None
        assert update.alt_text is not UNSET

    def test_get_set_fields_returns_only_set_fields(self) -> None:
        """get_set_fields returns only fields that are not UNSET."""
        update = ImageUpdate(alt_text="New text")

        set_fields = update.get_set_fields()

        assert set_fields == {"alt_text": "New text"}

    def test_get_set_fields_returns_empty_when_all_unset(self) -> None:
        """get_set_fields returns empty dict when all fields are UNSET."""
        update = ImageUpdate()

        set_fields = update.get_set_fields()

        assert set_fields == {}


# =============================================================================
# Result Model Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestImageResultModels:
    """Image result models are properly structured."""

    def test_staged_upload_target_stores_data(self) -> None:
        """StagedUploadTarget stores upload data."""
        target = StagedUploadTarget(
            url="https://shopify.com/upload",
            resource_url="https://cdn.shopify.com/resource.jpg",
            parameters=[StagedUploadParameter(name="key", value="value")],
        )

        assert target.url == "https://shopify.com/upload"
        assert target.resource_url == "https://cdn.shopify.com/resource.jpg"
        assert len(target.parameters) == 1
        assert target.parameters[0].name == "key"
        assert target.parameters[0].value == "value"
        assert target.get_parameters_dict() == {"key": "value"}

    def test_image_create_success_stores_data(self) -> None:
        """ImageCreateSuccess stores creation result."""
        success = ImageCreateSuccess(
            image_id="gid://shopify/MediaImage/123",
            url="https://cdn.shopify.com/image.jpg",
            alt_text="Front view",
            status=MediaStatus.READY,
        )

        assert success.image_id == "gid://shopify/MediaImage/123"
        assert success.url == "https://cdn.shopify.com/image.jpg"
        assert success.alt_text == "Front view"
        assert success.status == MediaStatus.READY

    def test_image_create_failure_stores_error(self) -> None:
        """ImageCreateFailure stores failure details."""
        source = ImageSource(url="https://example.com/bad.jpg")
        failure = ImageCreateFailure(
            source=source,
            error="Invalid image format",
            error_code="INVALID_FORMAT",
        )

        assert failure.source == source
        assert failure.error == "Invalid image format"
        assert failure.error_code == "INVALID_FORMAT"

    def test_image_create_result_properties(self) -> None:
        """ImageCreateResult has convenience properties."""
        success = ImageCreateSuccess(image_id="gid://shopify/MediaImage/1")
        failure = ImageCreateFailure(
            source=ImageSource(url="https://bad.com/img.jpg"),
            error="Failed",
        )
        result = ImageCreateResult(
            succeeded=[success],
            failed=[failure],
            product_id="gid://shopify/Product/1",
        )

        assert result.success_count == 1
        assert result.failure_count == 1
        assert result.all_succeeded is False

    def test_image_create_result_all_succeeded_true(self) -> None:
        """all_succeeded is True when no failures."""
        result = ImageCreateResult(
            succeeded=[ImageCreateSuccess(image_id="gid://shopify/MediaImage/1")],
            failed=[],
            product_id="gid://shopify/Product/1",
        )

        assert result.all_succeeded is True

    def test_image_delete_result_stores_ids(self) -> None:
        """ImageDeleteResult stores deleted IDs."""
        result = ImageDeleteResult(
            deleted_media_ids=["gid://shopify/MediaImage/1"],
            deleted_image_ids=["gid://shopify/ProductImage/1"],
            product_id="gid://shopify/Product/1",
        )

        assert result.deleted_media_ids == ["gid://shopify/MediaImage/1"]
        assert result.deleted_image_ids == ["gid://shopify/ProductImage/1"]

    def test_image_reorder_result_stores_job_id(self) -> None:
        """ImageReorderResult stores job ID."""
        result = ImageReorderResult(
            job_id="gid://shopify/Job/123",
            product_id="gid://shopify/Product/1",
        )

        assert result.job_id == "gid://shopify/Job/123"


# =============================================================================
# Parser Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestMediaParsers:
    """Media parser functions extract data correctly."""

    def test_parse_staged_upload_target(self) -> None:
        """parse_staged_upload_target extracts target data."""
        data = {
            "url": "https://upload.shopify.com/staged",
            "resourceUrl": "https://cdn.shopify.com/resource.jpg",
            "parameters": [
                {"name": "key", "value": "abc123"},
                {"name": "policy", "value": "xyz"},
            ],
        }

        result = parse_staged_upload_target(data)

        assert result.url == "https://upload.shopify.com/staged"
        assert result.resource_url == "https://cdn.shopify.com/resource.jpg"
        assert result.get_parameters_dict() == {"key": "abc123", "policy": "xyz"}

    def test_parse_staged_upload_target_empty_parameters(self) -> None:
        """parse_staged_upload_target handles empty parameters."""
        data: dict[str, object] = {
            "url": "https://upload.shopify.com/staged",
            "resourceUrl": "https://cdn.shopify.com/resource.jpg",
            "parameters": [],
        }

        result = parse_staged_upload_target(data)  # type: ignore[arg-type]

        assert result.get_parameters_dict() == {}

    def test_parse_media_from_mutation(self) -> None:
        """parse_media_from_mutation extracts media data."""
        data = {
            "id": "gid://shopify/MediaImage/123",
            "alt": "Front view",
            "status": "READY",
            "image": {
                "url": "https://cdn.shopify.com/image.jpg",
                "altText": "Alt from image",
            },
        }

        result = parse_media_from_mutation(data)

        assert result["image_id"] == "gid://shopify/MediaImage/123"
        assert result["url"] == "https://cdn.shopify.com/image.jpg"
        assert result["alt_text"] == "Front view"  # Prefers top-level alt
        assert result["status"] == "READY"

    def test_parse_media_from_mutation_fallback_alt(self) -> None:
        """parse_media_from_mutation falls back to image altText."""
        data = {
            "id": "gid://shopify/MediaImage/123",
            "alt": None,
            "status": "READY",
            "image": {
                "url": "https://cdn.shopify.com/image.jpg",
                "altText": "Alt from image",
            },
        }

        result = parse_media_from_mutation(data)

        assert result["alt_text"] == "Alt from image"

    def test_parse_media_user_errors(self) -> None:
        """parse_media_user_errors extracts error details."""
        errors = [
            {
                "code": "INVALID_IMAGE",
                "field": ["media", "0", "originalSource"],
                "message": "Invalid image URL",
            },
            {
                "code": "MEDIA_DOES_NOT_EXIST",
                "field": None,
                "message": "Media not found",
            },
        ]

        result = parse_media_user_errors(errors)

        assert len(result) == 2
        assert result[0]["code"] == "INVALID_IMAGE"
        assert result[0]["field"] == "media.0.originalSource"
        assert result[0]["message"] == "Invalid image URL"
        assert result[1]["code"] == "MEDIA_DOES_NOT_EXIST"
        assert result[1]["field"] == ""


# =============================================================================
# Exception Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestImageExceptions:
    """Image exceptions provide useful error information."""

    def test_image_not_found_error_message(self) -> None:
        """ImageNotFoundError has descriptive message."""
        error = ImageNotFoundError("gid://shopify/MediaImage/123")

        assert error.image_id == "gid://shopify/MediaImage/123"
        assert "Image not found: gid://shopify/MediaImage/123" in str(error)

    def test_image_not_found_error_custom_message(self) -> None:
        """ImageNotFoundError accepts custom message."""
        error = ImageNotFoundError("123", message="Custom error")

        assert error.message == "Custom error"

    def test_image_upload_error_message(self) -> None:
        """ImageUploadError has descriptive message."""
        error = ImageUploadError("/path/to/file.jpg")

        assert error.file_path == "/path/to/file.jpg"
        assert "Image upload failed: /path/to/file.jpg" in str(error)

    def test_image_upload_error_custom_message(self) -> None:
        """ImageUploadError accepts custom message."""
        error = ImageUploadError("/path/to/file.jpg", message="File too large")

        assert error.message == "File too large"


# =============================================================================
# API Function Tests (with mocking)
# =============================================================================


@pytest.mark.os_agnostic
class TestImageAPIFunctions:
    """Image API functions handle GraphQL operations correctly."""

    def test_create_image_requires_active_session(self) -> None:
        """create_image raises SessionNotActiveError for inactive session."""
        from lib_shopify_graphql.shopify_client._images import create_image

        mock_session = MagicMock()
        mock_session.is_active = False
        source = ImageSource(url="https://example.com/image.jpg")

        with pytest.raises(SessionNotActiveError):
            create_image(mock_session, "gid://shopify/Product/1", source)

    def test_create_images_requires_active_session(self) -> None:
        """create_images raises SessionNotActiveError for inactive session."""
        from lib_shopify_graphql.shopify_client._images import create_images

        mock_session = MagicMock()
        mock_session.is_active = False
        sources = [ImageSource(url="https://example.com/image.jpg")]

        with pytest.raises(SessionNotActiveError):
            create_images(mock_session, "gid://shopify/Product/1", sources)

    def test_update_image_requires_active_session(self) -> None:
        """update_image raises SessionNotActiveError for inactive session."""
        from lib_shopify_graphql.shopify_client._images import update_image

        mock_session = MagicMock()
        mock_session.is_active = False
        update = ImageUpdate(alt_text="New text")

        with pytest.raises(SessionNotActiveError):
            update_image(mock_session, "gid://shopify/Product/1", "gid://shopify/MediaImage/1", update)

    def test_update_image_requires_fields_to_update(self) -> None:
        """update_image raises ValueError when no fields to update."""
        from lib_shopify_graphql.shopify_client._images import update_image

        mock_session = MagicMock()
        mock_session.is_active = True
        update = ImageUpdate()  # All UNSET

        with pytest.raises(ValueError, match="No fields to update"):
            update_image(mock_session, "gid://shopify/Product/1", "gid://shopify/MediaImage/1", update)

    def test_delete_image_requires_active_session(self) -> None:
        """delete_image raises SessionNotActiveError for inactive session."""
        from lib_shopify_graphql.shopify_client._images import delete_image

        mock_session = MagicMock()
        mock_session.is_active = False

        with pytest.raises(SessionNotActiveError):
            delete_image(mock_session, "gid://shopify/Product/1", "gid://shopify/MediaImage/1")

    def test_delete_images_requires_active_session(self) -> None:
        """delete_images raises SessionNotActiveError for inactive session."""
        from lib_shopify_graphql.shopify_client._images import delete_images

        mock_session = MagicMock()
        mock_session.is_active = False

        with pytest.raises(SessionNotActiveError):
            delete_images(mock_session, "gid://shopify/Product/1", ["gid://shopify/MediaImage/1"])

    def test_reorder_images_requires_active_session(self) -> None:
        """reorder_images raises SessionNotActiveError for inactive session."""
        from lib_shopify_graphql.shopify_client._images import reorder_images

        mock_session = MagicMock()
        mock_session.is_active = False

        with pytest.raises(SessionNotActiveError):
            reorder_images(mock_session, "gid://shopify/Product/1", ["gid://shopify/MediaImage/1"])


@pytest.mark.os_agnostic
class TestImageAPIWithMockedGraphQL:
    """Image API functions with mocked GraphQL responses."""

    def test_create_image_from_url_success(self) -> None:
        """create_image successfully creates image from URL."""
        from lib_shopify_graphql.shopify_client._images import create_image

        mock_session = MagicMock()
        mock_session.is_active = True
        mock_session.execute_graphql.return_value = {
            "data": {
                "productCreateMedia": {
                    "media": [
                        {
                            "id": "gid://shopify/MediaImage/123",
                            "alt": "Front view",
                            "status": "PROCESSING",
                            "image": {"url": None, "altText": None},
                        }
                    ],
                    "mediaUserErrors": [],
                }
            }
        }

        source = ImageSource(url="https://example.com/image.jpg", alt_text="Front view")
        result = create_image(mock_session, "gid://shopify/Product/1", source)

        assert isinstance(result, ImageCreateSuccess)
        assert result.image_id == "gid://shopify/MediaImage/123"
        assert result.alt_text == "Front view"

    def test_delete_images_success(self) -> None:
        """delete_images successfully deletes images."""
        from lib_shopify_graphql.shopify_client._images import delete_images

        mock_session = MagicMock()
        mock_session.is_active = True
        mock_session.execute_graphql.return_value = {
            "data": {
                "productDeleteMedia": {
                    "deletedMediaIds": ["gid://shopify/MediaImage/1", "gid://shopify/MediaImage/2"],
                    "deletedProductImageIds": [],
                    "mediaUserErrors": [],
                }
            }
        }

        result = delete_images(
            mock_session,
            "gid://shopify/Product/1",
            ["gid://shopify/MediaImage/1", "gid://shopify/MediaImage/2"],
        )

        assert isinstance(result, ImageDeleteResult)
        assert len(result.deleted_media_ids) == 2

    def test_reorder_images_success(self) -> None:
        """reorder_images successfully reorders images."""
        from lib_shopify_graphql.shopify_client._images import reorder_images

        mock_session = MagicMock()
        mock_session.is_active = True
        mock_session.execute_graphql.return_value = {
            "data": {
                "productReorderMedia": {
                    "job": {"id": "gid://shopify/Job/456"},
                    "mediaUserErrors": [],
                }
            }
        }

        result = reorder_images(
            mock_session,
            "gid://shopify/Product/1",
            ["gid://shopify/MediaImage/3", "gid://shopify/MediaImage/1", "gid://shopify/MediaImage/2"],
        )

        assert isinstance(result, ImageReorderResult)
        assert result.job_id == "gid://shopify/Job/456"

    def test_update_image_success(self) -> None:
        """update_image successfully updates image metadata."""
        from lib_shopify_graphql.shopify_client._images import update_image

        mock_session = MagicMock()
        mock_session.is_active = True
        mock_session.execute_graphql.return_value = {
            "data": {
                "productUpdateMedia": {
                    "media": [
                        {
                            "id": "gid://shopify/MediaImage/123",
                            "alt": "Updated alt",
                            "status": "READY",
                            "image": {"url": "https://cdn.shopify.com/image.jpg", "altText": "Updated alt"},
                        }
                    ],
                    "mediaUserErrors": [],
                }
            }
        }

        update = ImageUpdate(alt_text="Updated alt")
        result = update_image(mock_session, "gid://shopify/Product/1", "gid://shopify/MediaImage/123", update)

        assert isinstance(result, ImageCreateSuccess)
        assert result.alt_text == "Updated alt"


# =============================================================================
# Helper Function Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestNormalizeMediaGid:
    """_normalize_media_gid converts IDs to GID format."""

    def test_returns_gid_unchanged(self) -> None:
        """Full GID is returned unchanged."""
        from lib_shopify_graphql.shopify_client._common import _normalize_media_gid

        result = _normalize_media_gid("gid://shopify/MediaImage/123")

        assert result == "gid://shopify/MediaImage/123"

    def test_converts_numeric_to_gid(self) -> None:
        """Numeric ID is converted to full GID."""
        from lib_shopify_graphql.shopify_client._common import _normalize_media_gid

        result = _normalize_media_gid("123")

        assert result == "gid://shopify/MediaImage/123"
