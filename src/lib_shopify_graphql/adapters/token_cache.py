"""Cached token provider with file or database backing.

This module provides a caching wrapper for token providers to reduce
OAuth token requests. Tokens are cached until near expiration.

Classes:
    - :class:`CachedTokenProvider`: Token provider with cache backing.
    - :class:`CachedTokenData`: Pydantic model for cached token data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from .constants import DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS

if TYPE_CHECKING:
    from ..application.ports import CachePort, TokenProviderPort

logger = logging.getLogger(__name__)


class CachedTokenData(BaseModel):
    """Cached OAuth token data.

    Attributes:
        access_token: The OAuth access token.
        expires_at: Unix timestamp when token expires.
    """

    model_config = ConfigDict(frozen=True)

    access_token: str
    expires_at: float


class CachedTokenProvider:
    """Token provider with cache-first strategy.

    Implements :class:`~lib_shopify_graphql.application.ports.TokenProviderPort`.

    Caches access tokens to reduce OAuth requests. Tokens are refreshed
    before expiration with a safety margin.

    The cache stores tokens as JSON with the structure:
    {
        "access_token": "...",
        "expires_at": 1234567890.0  # Unix timestamp
    }

    Attributes:
        cache: Cache adapter for storing tokens.
        delegate: Underlying token provider for obtaining new tokens.
        refresh_margin: Seconds before expiration to refresh token.

    Example:
        >>> from lib_shopify_graphql.adapters import (
        ...     JsonFileCacheAdapter,
        ...     ShopifyTokenProvider,
        ...     CachedTokenProvider,
        ... )
        >>> cache = JsonFileCacheAdapter(Path("/tmp/token_cache.json"))
        >>> delegate = ShopifyTokenProvider()
        >>> provider = CachedTokenProvider(cache, delegate)
        >>> token, expiration = provider.obtain_token(
        ...     "mystore.myshopify.com",
        ...     "client_id",
        ...     "client_secret",
        ... )
    """

    def __init__(
        self,
        cache: CachePort,
        delegate: TokenProviderPort,
        refresh_margin: int = DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS,
    ) -> None:
        """Initialize the cached token provider.

        Args:
            cache: Cache adapter for storing tokens.
            delegate: Underlying token provider for obtaining new tokens.
            refresh_margin: Seconds before expiration to refresh token.
                Defaults to 300 (5 minutes). Must be non-negative.

        Raises:
            ValueError: If refresh_margin is negative.
        """
        if refresh_margin < 0:
            msg = f"refresh_margin must be non-negative, got: {refresh_margin}"
            raise ValueError(msg)
        self.cache = cache
        self.delegate = delegate
        self.refresh_margin = refresh_margin

    def _make_cache_key(self, shop_url: str, client_id: str) -> str:
        """Generate a cache key for the token.

        Args:
            shop_url: Shopify store URL.
            client_id: OAuth client ID.

        Returns:
            Cache key in format "token:{shop_url}:{client_id}".
        """
        return f"token:{shop_url}:{client_id}"

    def obtain_token(
        self,
        shop_url: str,
        client_id: str,
        client_secret: str,
    ) -> tuple[str, datetime]:
        """Obtain an access token, using cache when possible.

        Checks cache first. Returns cached token if valid and not near
        expiration. Otherwise, obtains new token from delegate and caches it.

        Args:
            shop_url: Shopify store URL (e.g., 'mystore.myshopify.com').
            client_id: OAuth client ID from Dev Dashboard.
            client_secret: OAuth client secret from Dev Dashboard.

        Returns:
            Tuple of (access_token, expiration_datetime).

        Raises:
            AuthenticationError: If token request fails.
        """
        cache_key = self._make_cache_key(shop_url, client_id)

        # Try cache first
        cached = self._get_cached_token(cache_key)
        if cached:
            access_token, expires_at = cached
            logger.debug(
                "Token cache hit",
                extra={"shop_url": shop_url, "expires_at": expires_at.isoformat()},
            )
            return access_token, expires_at

        # Cache miss or expired - get new token
        logger.debug("Token cache miss, obtaining new token", extra={"shop_url": shop_url})
        access_token, expires_at = self.delegate.obtain_token(shop_url, client_id, client_secret)

        # Cache the new token
        self._cache_token(cache_key, access_token, expires_at)
        logger.debug(
            "Token cached",
            extra={"shop_url": shop_url, "expires_at": expires_at.isoformat()},
        )

        return access_token, expires_at

    def _get_cached_token(self, cache_key: str) -> tuple[str, datetime] | None:
        """Get token from cache if valid and not near expiration.

        Args:
            cache_key: Cache key for the token.

        Returns:
            Tuple of (access_token, expiration) if valid, None otherwise.
        """
        # Max valid timestamp: year 9999 (prevents OverflowError on 32-bit systems)
        max_valid_timestamp = 253402300799.0

        try:
            cached_value = self.cache.get(cache_key)
            if not cached_value:
                return None

            token_data = CachedTokenData.model_validate_json(cached_value)

            # Validate timestamp bounds before conversion
            if not (0 <= token_data.expires_at <= max_valid_timestamp):
                logger.warning(f"Invalid expires_at timestamp in cached token: expires_at={token_data.expires_at}")
                return None

            expires_at = datetime.fromtimestamp(token_data.expires_at, tz=timezone.utc)
            now = datetime.now(timezone.utc)

            # Check if token is still valid with safety margin
            if (expires_at - now).total_seconds() < self.refresh_margin:
                logger.debug("Cached token near expiration, will refresh")
                return None

            return token_data.access_token, expires_at

        except (TypeError, ValueError, OverflowError, OSError) as exc:
            logger.warning(f"Failed to parse cached token: {exc}")
            return None

    def _cache_token(
        self,
        cache_key: str,
        access_token: str,
        expires_at: datetime,
    ) -> None:
        """Store token in cache.

        Tokens are only cached if they have meaningful remaining lifetime
        (more than the refresh margin). Tokens near expiration are not
        cached to avoid serving stale tokens.

        Args:
            cache_key: Cache key for the token.
            access_token: The access token to cache.
            expires_at: Token expiration time.
        """
        try:
            # Calculate TTL: time until expiration minus refresh margin
            now = datetime.now(timezone.utc)
            ttl = int((expires_at - now).total_seconds()) - self.refresh_margin

            # Don't cache tokens that are already near or past expiration
            if ttl <= 0:
                logger.debug(
                    "Skipping cache for token near expiration",
                    extra={"ttl_seconds": ttl, "refresh_margin": self.refresh_margin},
                )
                return

            token_data = CachedTokenData(
                access_token=access_token,
                expires_at=expires_at.timestamp(),
            )
            self.cache.set(cache_key, token_data.model_dump_json(), ttl=ttl)

        except Exception as exc:
            logger.warning(f"Failed to cache token: {exc}")

    def invalidate(self, shop_url: str, client_id: str) -> None:
        """Remove a token from cache.

        Call this if authentication fails to force token refresh.

        Args:
            shop_url: Shopify store URL.
            client_id: OAuth client ID.
        """
        cache_key = self._make_cache_key(shop_url, client_id)
        self.cache.delete(cache_key)
        logger.debug("Token cache invalidated", extra={"shop_url": shop_url})


__all__ = ["CachedTokenData", "CachedTokenProvider"]
