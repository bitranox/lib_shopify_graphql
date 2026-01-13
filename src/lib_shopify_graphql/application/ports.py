"""Port definitions for Shopify API operations.

Ports define the contracts (interfaces) that adapters must implement.
The application layer depends only on these protocols, never on
concrete implementations like the Shopify SDK.

Protocols:
    - :class:`TokenProviderPort`: Obtain access tokens via OAuth.
    - :class:`GraphQLClientPort`: Execute GraphQL queries.
    - :class:`SessionManagerPort`: Manage API session state.
    - :class:`CachePort`: Key-value cache for SKU lookups.
    - :class:`SKUResolverPort`: Resolve SKU to variant GID.
    - :class:`LocationResolverPort`: Resolve location for inventory ops.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..models import Product


class TokenProviderPort(Protocol):
    """Port for obtaining OAuth access tokens.

    Implementations handle the OAuth 2.0 client credentials grant flow
    to obtain access tokens from Shopify.
    """

    def obtain_token(
        self,
        shop_url: str,
        client_id: str,
        client_secret: str,
    ) -> tuple[str, datetime]:
        """Obtain an access token using client credentials grant.

        Args:
            shop_url: Shopify store URL (e.g., 'mystore.myshopify.com').
            client_id: OAuth client ID from Dev Dashboard.
            client_secret: OAuth client secret from Dev Dashboard.

        Returns:
            Tuple of (access_token, expiration_datetime).

        Raises:
            AuthenticationError: If token request fails.
        """
        ...


class GraphQLClientPort(Protocol):
    """Port for executing GraphQL queries against Shopify API.

    Implementations handle the actual HTTP communication with
    Shopify's GraphQL Admin API.
    """

    def configure(
        self,
        shop_url: str,
        api_version: str,
        access_token: str,
    ) -> None:
        """Configure the GraphQL client with endpoint and credentials.

        Must be called before execute().

        Args:
            shop_url: Shopify store URL.
            api_version: Shopify API version.
            access_token: Access token for authentication.
        """
        ...

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query and return the parsed response.

        Args:
            query: GraphQL query string.
            variables: Optional query variables.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            GraphQLError: If the query execution fails.
        """
        ...


class SessionManagerPort(Protocol):
    """Port for managing Shopify API session state.

    Implementations handle activation, deactivation, and lifecycle
    of the underlying API session.
    """

    def create_session(
        self,
        shop_url: str,
        api_version: str,
        access_token: str,
    ) -> Any:
        """Create a new API session.

        Args:
            shop_url: Shopify store URL.
            api_version: Shopify API version (format: YYYY-MM).
            access_token: OAuth access token.

        Returns:
            Session object (implementation-specific).
        """
        ...

    def activate_session(self, session: Any) -> None:
        """Activate a session for API calls.

        Args:
            session: Session object to activate.
        """
        ...

    def clear_session(self) -> None:
        """Clear/deactivate the current session."""
        ...


class CachePort(Protocol):
    """Port for key-value cache operations.

    Used for caching SKU-to-GID mappings to reduce API calls.
    Implementations may use file storage, databases, or other backends.
    """

    def get(self, key: str) -> str | None:
        """Get a value from the cache.

        Args:
            key: Cache key to look up.

        Returns:
            The cached value, or None if not found or expired.
        """
        ...

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Store a value in the cache.

        Args:
            key: Cache key.
            value: Value to store.
            ttl: Time-to-live in seconds. None for no expiration.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove a key from the cache.

        Args:
            key: Cache key to remove.
        """
        ...

    def clear(self) -> None:
        """Clear all cached entries."""
        ...

    def keys(self, prefix: str | None = None) -> list[str]:
        """List all cache keys, optionally filtered by prefix.

        Args:
            prefix: If provided, only return keys starting with this prefix.

        Returns:
            List of cache keys.
        """
        ...


class SKUResolverPort(Protocol):
    """Port for resolving SKU to variant GID with bidirectional cache.

    Maintains bidirectional cache mappings:
    - Forward: SKU → (variant_gid, product_gid)
    - Reverse: variant_gid → (sku, product_gid)

    Cache is updated on:
    - Read operations: ``resolve()``, ``update_from_product()``
    - Write operations: ``update_from_variant()``

    Important:
        SKUs in Shopify are NOT guaranteed to be unique. Multiple variants
        (potentially across different products) can share the same SKU.
        Implementations must detect this and raise ``AmbiguousSKUError``
        when a SKU matches multiple variants.
    """

    def resolve(self, sku: str, shop_url: str) -> str | None:
        """Resolve a SKU to its variant GID.

        Always queries Shopify to verify uniqueness, then updates cache.

        Args:
            sku: Stock keeping unit identifier.
            shop_url: Shopify store URL for cache key namespacing.

        Returns:
            Variant GID if found and unique, None if not found.

        Raises:
            AmbiguousSKUError: If the SKU matches multiple variants.
                Use explicit variant GID or ``resolve_all()`` instead.
        """
        ...

    def resolve_all(self, sku: str) -> list[str]:
        """Resolve a SKU to ALL matching variant GIDs.

        Does not use cache. Always queries Shopify to find all variants.

        Args:
            sku: Stock keeping unit identifier.

        Returns:
            List of variant GIDs. Empty list if no matches found.
        """
        ...

    def invalidate(self, sku: str, shop_url: str) -> None:
        """Remove a SKU mapping from cache.

        Deletes both forward and reverse cache entries.

        Args:
            sku: SKU to invalidate.
            shop_url: Shopify store URL.
        """
        ...

    def update_from_variant(
        self,
        variant_gid: str,
        product_gid: str,
        sku: str | None,
        shop_url: str,
    ) -> None:
        """Update cache after variant upsert.

        Handles SKU changes by:
        1. Looking up old SKU via reverse cache
        2. If SKU changed, deleting old forward entry
        3. Setting new forward + reverse entries

        Args:
            variant_gid: Variant GID.
            product_gid: Product GID.
            sku: New SKU value (None if variant has no SKU).
            shop_url: Shop URL for namespacing.
        """
        ...

    def update_from_product(self, product: Product, shop_url: str) -> None:
        """Update cache for all variants in a product.

        Call this after fetching a product to keep the cache warm.

        Args:
            product: Product with variants.
            shop_url: Shop URL for namespacing.
        """
        ...


class LocationResolverPort(Protocol):
    """Port for resolving inventory location.

    Implements fallback chain:
    1. Explicit location from parameter
    2. Default location from configuration
    3. Shop's primary location (auto-fetched)
    """

    def resolve(self, explicit_location: str | None = None) -> str:
        """Resolve the location to use for inventory operations.

        Args:
            explicit_location: Explicitly provided location GID.
                If provided, returned as-is.

        Returns:
            Location GID to use.

        Raises:
            ValueError: If no location can be resolved.
        """
        ...

    def clear_cache(self) -> None:
        """Clear the cached primary location.

        Call this if the shop's locations change and you need
        to re-fetch the primary location.
        """
        ...


__all__ = [
    "CachePort",
    "GraphQLClientPort",
    "LocationResolverPort",
    "SessionManagerPort",
    "SKUResolverPort",
    "TokenProviderPort",
]
