"""Image management models for Shopify product media operations.

This module provides models for creating, updating, and deleting product images:
    - ImageSource: Source specification (URL or file path)
    - ImageUpdate: Partial update for image metadata
    - ImageCreateResult: Result of batch image creation
    - ImageDeleteResult: Result of image deletion
    - ImageReorderResult: Result of image reordering
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from ._enums import MediaStatus
from ._internal import UNSET, Updatable


class ImageSource(BaseModel):
    """Source for creating a new product image.

    Either ``url`` or ``file_path`` must be provided, but not both.

    Attributes:
        url: External URL of an already-hosted image.
        file_path: Local file path for upload to Shopify.
        alt_text: Alternative text for accessibility.

    Example:
        >>> # From external URL
        >>> source = ImageSource(url="https://example.com/image.jpg", alt_text="Front view")
        >>> # From local file
        >>> source = ImageSource(file_path=Path("/path/to/image.jpg"))
    """

    model_config = ConfigDict(frozen=True)

    url: str | None = None
    file_path: Path | None = None
    alt_text: str | None = None

    @model_validator(mode="after")
    def require_source(self) -> Self:
        """Validate that exactly one source is provided."""
        if self.url and self.file_path:
            msg = "Provide either url or file_path, not both"
            raise ValueError(msg)
        if not self.url and not self.file_path:
            msg = "Either url or file_path must be provided"
            raise ValueError(msg)
        return self


class ImageUpdate(BaseModel):
    """Partial update for image metadata.

    All fields default to UNSET (won't be updated).
    Set to a value to update, or None to clear.

    Field states:
        - ``UNSET`` (default): Don't update this field
        - ``None``: Clear this field (set to null on Shopify)
        - ``value``: Update to this value

    Attributes:
        alt_text: Alternative text for accessibility.

    Example:
        >>> update = ImageUpdate(alt_text="New description")
        >>> update.alt_text
        'New description'
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    alt_text: Updatable[str] = UNSET

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


# =============================================================================
# Result Models
# =============================================================================


class StagedUploadParameter(BaseModel):
    """A single authentication parameter for staged upload.

    Attributes:
        name: Parameter name (header key).
        value: Parameter value.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    value: str


class StagedUploadTarget(BaseModel):
    """Staged upload target returned by Shopify.

    Used internally for the 2-step file upload process.

    Attributes:
        url: URL to upload the file to.
        resource_url: URL to use as originalSource in subsequent mutations.
        parameters: Authentication parameters for the upload.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    resource_url: str
    parameters: list[StagedUploadParameter] = Field(default_factory=list[StagedUploadParameter])

    def get_parameters_dict(self) -> dict[str, str]:
        """Get parameters as a dictionary for HTTP requests.

        Returns:
            Dictionary of parameter names to values.
        """
        return {p.name: p.value for p in self.parameters}


class ImageCreateSuccess(BaseModel):
    """Result of a successful image creation.

    Attributes:
        image_id: The created image/media GID.
        url: URL of the created image (may be None while processing).
        alt_text: Alt text if set.
        status: Processing status (PROCESSING, READY, FAILED).
    """

    model_config = ConfigDict(frozen=True)

    image_id: str
    url: str | None = None
    alt_text: str | None = None
    status: MediaStatus = MediaStatus.PROCESSING


class ImageCreateFailure(BaseModel):
    """Result of a failed image creation.

    Attributes:
        source: The image source that failed.
        error: Human-readable error message.
        error_code: Shopify error code if available.
    """

    model_config = ConfigDict(frozen=True)

    source: ImageSource
    error: str
    error_code: str | None = None


class ImageCreateResult(BaseModel):
    """Result of image creation operation.

    Attributes:
        succeeded: Successfully created images.
        failed: Failed image creations.
        product_id: The product that was updated.

    Example:
        >>> result = create_images(session, product_id, sources)  # doctest: +SKIP
        >>> print(f"Created {result.success_count}, failed {result.failure_count}")  # doctest: +SKIP
        >>> if result.all_succeeded:  # doctest: +SKIP
        ...     print("All images created successfully")
    """

    model_config = ConfigDict(frozen=True)

    succeeded: list[ImageCreateSuccess] = Field(default_factory=list[ImageCreateSuccess])
    failed: list[ImageCreateFailure] = Field(default_factory=list[ImageCreateFailure])
    product_id: str

    @property
    def success_count(self) -> int:
        """Number of successfully created images."""
        return len(self.succeeded)

    @property
    def failure_count(self) -> int:
        """Number of failed image creations."""
        return len(self.failed)

    @property
    def all_succeeded(self) -> bool:
        """Whether all images were created successfully."""
        return len(self.failed) == 0


class ImageDeleteResult(BaseModel):
    """Result of image deletion operation.

    Attributes:
        deleted_image_ids: Successfully deleted ProductImage GIDs.
        deleted_media_ids: Successfully deleted Media GIDs.
        product_id: The product that was updated.
    """

    model_config = ConfigDict(frozen=True)

    deleted_image_ids: list[str] = Field(default_factory=list[str])
    deleted_media_ids: list[str] = Field(default_factory=list[str])
    product_id: str


class ImageReorderResult(BaseModel):
    """Result of image reorder operation.

    Note: Reordering is an async operation in Shopify.

    Attributes:
        job_id: Async job ID for tracking progress.
        product_id: The product being updated.
    """

    model_config = ConfigDict(frozen=True)

    job_id: str | None = None
    product_id: str


__all__ = [
    "ImageCreateFailure",
    "ImageCreateResult",
    "ImageCreateSuccess",
    "ImageDeleteResult",
    "ImageReorderResult",
    "ImageSource",
    "ImageUpdate",
    "StagedUploadParameter",
    "StagedUploadTarget",
]
