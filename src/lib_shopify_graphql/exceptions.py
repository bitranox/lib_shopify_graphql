"""Domain exceptions for Shopify API operations.

This module contains all custom exceptions raised by the Shopify client:
    - :class:`ShopifyError`: Base exception for all Shopify operations.
    - :class:`AuthenticationError`: Authentication with Shopify failed.
    - :class:`ProductNotFoundError`: Product with given ID does not exist.
    - :class:`VariantNotFoundError`: Variant with given ID/SKU does not exist.
    - :class:`ImageNotFoundError`: Image with given ID does not exist.
    - :class:`ImageUploadError`: Image upload operation failed.
    - :class:`SessionNotActiveError`: Session is not active.
    - :class:`GraphQLError`: GraphQL query returned errors.
    - :class:`GraphQLErrorEntry`: Structured GraphQL error entry.

Note:
    All exceptions inherit from :class:`ShopifyError` for easy catching
    of any Shopify-related error.
"""

from __future__ import annotations

from dataclasses import dataclass


class ShopifyError(Exception):
    """Base exception for all Shopify API operations.

    All Shopify-specific exceptions inherit from this class, allowing
    callers to catch any Shopify error with a single except clause.

    Example::

        try:
            result = some_shopify_operation()
        except ShopifyError as e:
            print(f"Shopify operation failed: {e}")
    """


class AuthenticationError(ShopifyError):
    """Authentication with Shopify failed.

    Raised when:
        - Invalid access token provided.
        - Shop URL is incorrect or inaccessible.
        - API credentials have been revoked.

    Attributes:
        shop_url: The shop URL that failed authentication.
        message: Human-readable error description.
    """

    def __init__(self, message: str, *, shop_url: str | None = None) -> None:
        """Initialize authentication error.

        Args:
            message: Human-readable error description.
            shop_url: The shop URL that failed authentication.
        """
        super().__init__(message)
        self.shop_url = shop_url
        self.message = message


class ProductNotFoundError(ShopifyError):
    """Product with given ID does not exist.

    Raised when a product lookup by ID returns no results.

    Attributes:
        product_id: The product ID that was not found.
        message: Human-readable error description.
    """

    def __init__(self, product_id: str, message: str | None = None) -> None:
        """Initialize product not found error.

        Args:
            product_id: The Shopify product ID that was not found.
            message: Optional custom message.
        """
        self.product_id = product_id
        self.message = message or f"Product not found: {product_id}"
        super().__init__(self.message)


class VariantNotFoundError(ShopifyError):
    """Variant with given ID or SKU does not exist.

    Raised when a variant lookup by ID or SKU returns no results.

    Attributes:
        identifier: The variant ID or SKU that was not found.
        message: Human-readable error description.
    """

    def __init__(self, identifier: str, message: str | None = None) -> None:
        """Initialize variant not found error.

        Args:
            identifier: The variant ID or SKU that was not found.
            message: Optional custom message.
        """
        self.identifier = identifier
        self.message = message or f"Variant not found: {identifier}"
        super().__init__(self.message)


class ImageNotFoundError(ShopifyError):
    """Image with given ID does not exist.

    Raised when an image lookup by ID returns no results or when
    attempting to update/delete a non-existent image.

    Attributes:
        image_id: The image/media ID that was not found.
        message: Human-readable error description.
    """

    def __init__(self, image_id: str, message: str | None = None) -> None:
        """Initialize image not found error.

        Args:
            image_id: The Shopify image/media GID that was not found.
            message: Optional custom message.
        """
        self.image_id = image_id
        self.message = message or f"Image not found: {image_id}"
        super().__init__(self.message)


class ImageUploadError(ShopifyError):
    """Image upload operation failed.

    Raised when uploading a local file to Shopify fails. This can occur
    during the staged upload process or when attaching the uploaded
    file to a product.

    Attributes:
        file_path: Path to the local file that failed to upload.
        message: Human-readable error description.
    """

    def __init__(self, file_path: str, message: str | None = None) -> None:
        """Initialize image upload error.

        Args:
            file_path: Path to the file that failed to upload.
            message: Optional custom message.
        """
        self.file_path = file_path
        self.message = message or f"Image upload failed: {file_path}"
        super().__init__(self.message)


class AmbiguousSKUError(ShopifyError):
    """SKU matches multiple variants.

    Raised when a SKU lookup returns more than one variant. This indicates
    that the SKU is not unique in the Shopify store, and the operation
    cannot proceed without explicit variant identification.

    In Shopify, SKUs are not enforced to be unique - multiple variants
    (potentially across different products) can share the same SKU.
    When this occurs, you must use the explicit variant GID instead.

    Attributes:
        sku: The ambiguous SKU.
        variant_gids: List of variant GIDs that match this SKU.
        message: Human-readable error description.

    Example:
        >>> try:  # doctest: +SKIP
        ...     update_variant(session, "AMBIGUOUS-SKU", update)
        ... except AmbiguousSKUError as e:
        ...     print(f"SKU '{e.sku}' matches {len(e.variant_gids)} variants:")
        ...     for gid in e.variant_gids:
        ...         print(f"  - {gid}")
        ...     print("Please use explicit variant GID instead.")
    """

    def __init__(
        self,
        sku: str,
        variant_gids: list[str],
        message: str | None = None,
    ) -> None:
        """Initialize ambiguous SKU error.

        Args:
            sku: The SKU that matches multiple variants.
            variant_gids: List of variant GIDs that have this SKU.
            message: Optional custom message.
        """
        self.sku = sku
        self.variant_gids = list(variant_gids)  # Defensive copy
        self.message = message or (f"SKU '{sku}' is ambiguous: matches {len(variant_gids)} variants. Use explicit variant GID instead: {variant_gids}")
        super().__init__(self.message)


class SessionNotActiveError(ShopifyError):
    """Session is not active or has been logged out.

    Raised when attempting to use a session that has been terminated
    or was never properly initialized.

    Attributes:
        message: Human-readable error description.
    """

    def __init__(self, message: str = "Session is not active") -> None:
        """Initialize session not active error.

        Args:
            message: Human-readable error description.
        """
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class GraphQLErrorLocation:
    """Location within a GraphQL query where an error occurred.

    Attributes:
        line: Line number in the query (1-indexed).
        column: Column number in the query (1-indexed).
    """

    line: int
    column: int


@dataclass(frozen=True, slots=True)
class GraphQLErrorEntry:
    """Structured GraphQL error entry from Shopify API response.

    Represents a single error from the GraphQL response errors array.

    Attributes:
        message: Human-readable error description.
        locations: Where the error occurred in the query.
        path: Path to the field that caused the error.
        extensions: Additional error metadata from Shopify.
    """

    message: str
    locations: tuple[GraphQLErrorLocation, ...] | None = None
    path: tuple[str | int, ...] | None = None
    extensions: dict[str, object] | None = None


class GraphQLTimeoutError(ShopifyError):
    """GraphQL query timed out.

    Raised when a GraphQL query exceeds the configured timeout.

    Attributes:
        timeout: The timeout value in seconds that was exceeded.
        query: The GraphQL query that timed out.
        message: Human-readable error description.
    """

    def __init__(
        self,
        message: str,
        *,
        timeout: float,
        query: str | None = None,
    ) -> None:
        """Initialize timeout error.

        Args:
            message: Human-readable error description.
            timeout: The timeout value that was exceeded.
            query: The GraphQL query that timed out.
        """
        super().__init__(message)
        self.timeout = timeout
        self.query = query
        self.message = message


class GraphQLError(ShopifyError):
    """GraphQL query returned errors.

    Raised when Shopify's GraphQL API returns errors in the response.

    Attributes:
        errors: List of structured GraphQLErrorEntry objects.
        query: The GraphQL query that caused the error.
        message: Human-readable error description.
    """

    def __init__(
        self,
        message: str,
        *,
        errors: list[GraphQLErrorEntry] | None = None,
        query: str | None = None,
    ) -> None:
        """Initialize GraphQL error.

        Args:
            message: Human-readable error description.
            errors: List of structured GraphQLErrorEntry objects.
            query: The GraphQL query that caused the error.
        """
        super().__init__(message)
        self.errors = errors or []
        self.query = query
        self.message = message


__all__ = [
    "AmbiguousSKUError",
    "AuthenticationError",
    "GraphQLError",
    "GraphQLErrorEntry",
    "GraphQLErrorLocation",
    "GraphQLTimeoutError",
    "ImageNotFoundError",
    "ImageUploadError",
    "ProductNotFoundError",
    "SessionNotActiveError",
    "ShopifyError",
    "VariantNotFoundError",
]
