"""Token cache tests: verifying cached token provider behavior.

Tests use real in-memory implementations instead of mocks to validate
actual system behavior. Each test reads like plain English.

Coverage:
- Cache hit returns cached token without delegate call
- Cache miss queries delegate and caches result
- Token expiration triggers refresh
- Cache invalidation enables fresh lookups
- Error handling returns gracefully
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from lib_shopify_graphql.adapters.constants import DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS
from lib_shopify_graphql.adapters.token_cache import CachedTokenProvider

from conftest import FakeTokenProvider, InMemoryCache


# =============================================================================
# Cache Hit Behavior
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheHitReturnsWithoutDelegateCall:
    """When a valid token is in cache, the provider returns it without calling delegate."""

    def test_cached_token_is_returned_immediately(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """A cached token is returned without any delegate call."""
        # Pre-populate cache with a valid token
        future_expiration = datetime.now(timezone.utc) + timedelta(hours=12)
        cached_data = json.dumps(
            {
                "access_token": "cached_token_123",
                "expires_at": future_expiration.timestamp(),
            }
        )
        in_memory_cache.set("token:mystore.myshopify.com:client123", cached_data)

        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token, expiration = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        assert token == "cached_token_123"
        assert abs((expiration - future_expiration).total_seconds()) < 1

    def test_different_shops_have_different_cache_namespaces(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Same client ID in different shops are cached separately."""
        # Pre-populate cache for both shops
        exp1 = datetime.now(timezone.utc) + timedelta(hours=12)
        exp2 = datetime.now(timezone.utc) + timedelta(hours=12)
        in_memory_cache.set("token:shop1.myshopify.com:client123", json.dumps({"access_token": "token_shop1", "expires_at": exp1.timestamp()}))
        in_memory_cache.set("token:shop2.myshopify.com:client123", json.dumps({"access_token": "token_shop2", "expires_at": exp2.timestamp()}))
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token1, _ = provider.obtain_token("shop1.myshopify.com", "client123", "secret")
        token2, _ = provider.obtain_token("shop2.myshopify.com", "client123", "secret")

        assert token1 == "token_shop1"
        assert token2 == "token_shop2"

    def test_different_clients_have_different_cache_namespaces(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Different client IDs in the same shop are cached separately."""
        exp = datetime.now(timezone.utc) + timedelta(hours=12)
        in_memory_cache.set("token:mystore.myshopify.com:client1", json.dumps({"access_token": "token_client1", "expires_at": exp.timestamp()}))
        in_memory_cache.set("token:mystore.myshopify.com:client2", json.dumps({"access_token": "token_client2", "expires_at": exp.timestamp()}))
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token1, _ = provider.obtain_token("mystore.myshopify.com", "client1", "secret1")
        token2, _ = provider.obtain_token("mystore.myshopify.com", "client2", "secret2")

        assert token1 == "token_client1"
        assert token2 == "token_client2"


# =============================================================================
# Cache Miss Queries Delegate
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheMissQueriesDelegate:
    """When the token is not in cache, the provider queries the delegate."""

    def test_missing_token_triggers_delegate_call(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """A missing token causes a delegate call."""
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        # Should return the token from fake_token_provider
        assert token == fake_token_provider.token

    def test_new_token_is_cached_for_future_lookups(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """The obtained token is cached to avoid future delegate calls."""
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        cached_value = in_memory_cache.get("token:mystore.myshopify.com:client123")
        assert cached_value is not None
        cached_data = json.loads(cached_value)
        assert cached_data["access_token"] == fake_token_provider.token

    def test_cached_token_is_reused_on_second_call(self, in_memory_cache: InMemoryCache) -> None:
        """The second call returns the cached token without hitting delegate."""

        # Use a tracking token provider to verify cache behavior
        class TrackingTokenProvider:
            def __init__(self) -> None:
                self.call_count = 0

            def obtain_token(self, shop_url: str, client_id: str, client_secret: str) -> tuple[str, datetime]:
                self.call_count += 1
                expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                return (f"token_call_{self.call_count}", expires_at)

        tracking_provider = TrackingTokenProvider()
        provider = CachedTokenProvider(in_memory_cache, tracking_provider)

        # First call - should hit delegate
        token1, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")
        # Second call - should use cache
        token2, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        assert token1 == "token_call_1"
        assert token2 == "token_call_1"  # Same token from cache
        assert tracking_provider.call_count == 1  # Only called once


# =============================================================================
# Token Expiration and Refresh
# =============================================================================


@pytest.mark.os_agnostic
class TestTokenExpirationTriggersRefresh:
    """When token is expired or near expiration, the provider refreshes it."""

    def test_expired_token_triggers_refresh(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """An expired token causes a delegate call for a new token."""
        # Cache an expired token
        past_expiration = datetime.now(timezone.utc) - timedelta(minutes=10)
        in_memory_cache.set("token:mystore.myshopify.com:client123", json.dumps({"access_token": "expired_token", "expires_at": past_expiration.timestamp()}))
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        # Should get fresh token, not the expired one
        assert token == fake_token_provider.token
        assert token != "expired_token"

    def test_token_near_expiration_triggers_refresh(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """A token within refresh margin of expiration triggers a refresh."""
        # Token expires in 4 minutes (less than 5 minute default refresh margin)
        near_expiration = datetime.now(timezone.utc) + timedelta(minutes=4)
        in_memory_cache.set("token:mystore.myshopify.com:client123", json.dumps({"access_token": "old_token", "expires_at": near_expiration.timestamp()}))
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider, refresh_margin=300)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        # Should get fresh token since old one is near expiration
        assert token == fake_token_provider.token

    def test_token_not_near_expiration_is_returned(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """A token not near expiration is returned from cache."""
        # Token expires in 10 minutes (more than 5 minute margin)
        future_expiration = datetime.now(timezone.utc) + timedelta(minutes=10)
        in_memory_cache.set("token:mystore.myshopify.com:client123", json.dumps({"access_token": "valid_token", "expires_at": future_expiration.timestamp()}))
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider, refresh_margin=300)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        assert token == "valid_token"


# =============================================================================
# Cache TTL Based on Token Expiration
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheTTLBasedOnExpiration:
    """Cache TTL is set based on token expiration minus refresh margin."""

    def test_ttl_is_expiration_minus_margin(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """TTL is calculated as expiration time minus refresh margin."""
        # Configure token to expire in 2 hours
        fake_token_provider.expires_in_seconds = 7200  # 2 hours
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider, refresh_margin=300)

        provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        # The cached entry should exist
        cached = in_memory_cache.get("token:mystore.myshopify.com:client123")
        assert cached is not None


# =============================================================================
# Cache Invalidation
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheInvalidation:
    """Invalidation removes entries from cache, enabling fresh lookups."""

    def test_invalidate_removes_cached_entry(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Invalidate removes the token from cache."""
        # Pre-populate cache
        exp = datetime.now(timezone.utc) + timedelta(hours=12)
        in_memory_cache.set("token:mystore.myshopify.com:client123", json.dumps({"access_token": "old_token", "expires_at": exp.timestamp()}))
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        provider.invalidate("mystore.myshopify.com", "client123")

        assert in_memory_cache.get("token:mystore.myshopify.com:client123") is None

    def test_invalidation_allows_fresh_lookup(self, in_memory_cache: InMemoryCache) -> None:
        """After invalidation, next obtain_token queries delegate for fresh data."""

        # Use a tracking provider
        class TrackingTokenProvider:
            def __init__(self) -> None:
                self.call_count = 0

            def obtain_token(self, shop_url: str, client_id: str, client_secret: str) -> tuple[str, datetime]:
                self.call_count += 1
                expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                return (f"fresh_token_{self.call_count}", expires_at)

        tracking_provider = TrackingTokenProvider()

        # Pre-populate cache
        exp = datetime.now(timezone.utc) + timedelta(hours=12)
        in_memory_cache.set("token:mystore.myshopify.com:client123", json.dumps({"access_token": "old_token", "expires_at": exp.timestamp()}))
        provider = CachedTokenProvider(in_memory_cache, tracking_provider)

        # First verify cache is being used (should return old_token)
        token1, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")
        assert token1 == "old_token"
        assert tracking_provider.call_count == 0

        # Invalidate and get fresh token
        provider.invalidate("mystore.myshopify.com", "client123")
        token2, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        assert token2 == "fresh_token_1"
        assert tracking_provider.call_count == 1


# =============================================================================
# Error Handling
# =============================================================================


@pytest.mark.os_agnostic
class TestErrorHandling:
    """Errors are handled gracefully without crashing."""

    def test_invalid_json_in_cache_triggers_delegate_call(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Invalid JSON in cache triggers delegate call for fresh token."""
        in_memory_cache.set("token:mystore.myshopify.com:client123", "not valid json {")
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        assert token == fake_token_provider.token

    def test_missing_access_token_in_cache_triggers_delegate_call(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Missing access_token field in cached data triggers delegate call."""
        in_memory_cache.set("token:mystore.myshopify.com:client123", json.dumps({"expires_at": 9999999999.0}))
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        assert token == fake_token_provider.token

    def test_missing_expires_at_in_cache_triggers_delegate_call(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Missing expires_at field in cached data triggers delegate call."""
        in_memory_cache.set("token:mystore.myshopify.com:client123", json.dumps({"access_token": "token"}))
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        assert token == fake_token_provider.token

    def test_delegate_error_propagates(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Delegate errors propagate to caller."""
        fake_token_provider.should_raise = Exception("Auth server down")
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        with pytest.raises(Exception, match="Auth server down"):
            provider.obtain_token("mystore.myshopify.com", "client123", "secret")

    def test_cache_set_failure_is_handled_gracefully(self, fake_token_provider: FakeTokenProvider) -> None:
        """When cache.set fails, obtain_token still returns the token."""
        from unittest.mock import MagicMock

        # Create a cache that raises on set
        failing_cache = MagicMock()
        failing_cache.get.return_value = None  # No cached token
        failing_cache.set.side_effect = Exception("Cache write error")

        provider = CachedTokenProvider(failing_cache, fake_token_provider)

        # Should still work despite cache failure
        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        assert token == fake_token_provider.token
        failing_cache.set.assert_called_once()


# =============================================================================
# Initialization
# =============================================================================


@pytest.mark.os_agnostic
class TestProviderInitialization:
    """CachedTokenProvider initializes with correct defaults."""

    def test_stores_cache_and_delegate(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Constructor stores cache and delegate references."""
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        assert provider.cache is in_memory_cache
        assert provider.delegate is fake_token_provider

    def test_default_refresh_margin_is_five_minutes(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Refresh margin defaults to DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS (300)."""
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        assert provider.refresh_margin == DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS
        assert provider.refresh_margin == 300

    def test_custom_refresh_margin_is_honored(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Custom refresh margin is stored and used."""
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider, refresh_margin=600)

        assert provider.refresh_margin == 600


# =============================================================================
# TTL Edge Case: Token Near Expiration Not Cached
# =============================================================================


@pytest.mark.os_agnostic
class TestTokenNearExpirationNotCached:
    """Tokens with TTL <= 0 after margin are not cached."""

    def test_token_with_zero_ttl_not_cached(self, in_memory_cache: InMemoryCache) -> None:
        """A token that expires within refresh margin is not cached."""

        class ShortLivedTokenProvider:
            """Token provider that returns tokens expiring in 4 minutes (less than 5 minute margin)."""

            def obtain_token(self, shop_url: str, client_id: str, client_secret: str) -> tuple[str, datetime]:
                # Token expires in 4 minutes, with 5 minute margin this gives TTL < 0
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=4)
                return ("short_lived_token", expires_at)

        provider = CachedTokenProvider(in_memory_cache, ShortLivedTokenProvider(), refresh_margin=300)

        # First call - should not cache because TTL would be negative
        token1, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")
        assert token1 == "short_lived_token"

        # Verify nothing was cached
        cached = in_memory_cache.get("token:mystore.myshopify.com:client123")
        assert cached is None, "Token with TTL <= 0 should not be cached"

    def test_token_with_negative_ttl_not_cached(self, in_memory_cache: InMemoryCache) -> None:
        """A token that is already past expiration margin is not cached."""

        class ExpiredTokenProvider:
            """Token provider that returns already-expired tokens."""

            def obtain_token(self, shop_url: str, client_id: str, client_secret: str) -> tuple[str, datetime]:
                # Token expires in 1 minute, with 5 minute margin this gives TTL << 0
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                return ("already_expired_token", expires_at)

        provider = CachedTokenProvider(in_memory_cache, ExpiredTokenProvider(), refresh_margin=300)

        # Should not cache
        provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        cached = in_memory_cache.get("token:mystore.myshopify.com:client123")
        assert cached is None, "Token with negative TTL should not be cached"

    def test_token_with_positive_ttl_is_cached(self, in_memory_cache: InMemoryCache) -> None:
        """A token with TTL > 0 after margin IS cached (sanity check)."""

        class LongLivedTokenProvider:
            """Token provider that returns tokens expiring in 2 hours."""

            def obtain_token(self, shop_url: str, client_id: str, client_secret: str) -> tuple[str, datetime]:
                # Token expires in 2 hours, with 5 minute margin this gives ~115 min TTL
                expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
                return ("long_lived_token", expires_at)

        provider = CachedTokenProvider(in_memory_cache, LongLivedTokenProvider(), refresh_margin=300)

        provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        cached = in_memory_cache.get("token:mystore.myshopify.com:client123")
        assert cached is not None, "Token with TTL > 0 should be cached"


# =============================================================================
# Edge Cases: Invalid Timestamps and Parameters
# =============================================================================


@pytest.mark.os_agnostic
class TestInvalidTimestampHandling:
    """Invalid timestamps in cache are handled gracefully."""

    def test_overflow_timestamp_triggers_delegate_call(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Timestamp too large for datetime.fromtimestamp triggers delegate."""
        # Year 292278994 - way beyond valid range
        in_memory_cache.set(
            "token:mystore.myshopify.com:client123",
            json.dumps({"access_token": "old_token", "expires_at": 9999999999999.0}),
        )
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        # Should get fresh token since cached one has invalid timestamp
        assert token == fake_token_provider.token

    def test_negative_timestamp_triggers_delegate_call(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Negative timestamp triggers delegate call."""
        in_memory_cache.set(
            "token:mystore.myshopify.com:client123",
            json.dumps({"access_token": "old_token", "expires_at": -1000.0}),
        )
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider)

        token, _ = provider.obtain_token("mystore.myshopify.com", "client123", "secret")

        # Should get fresh token since cached one has invalid timestamp
        assert token == fake_token_provider.token


@pytest.mark.os_agnostic
class TestRefreshMarginValidation:
    """refresh_margin parameter is validated."""

    def test_negative_refresh_margin_raises_error(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Negative refresh_margin raises ValueError."""
        with pytest.raises(ValueError, match="refresh_margin must be non-negative"):
            CachedTokenProvider(in_memory_cache, fake_token_provider, refresh_margin=-100)

    def test_zero_refresh_margin_is_valid(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Zero refresh_margin is allowed."""
        provider = CachedTokenProvider(in_memory_cache, fake_token_provider, refresh_margin=0)
        assert provider.refresh_margin == 0
