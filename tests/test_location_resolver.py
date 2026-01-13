"""Location resolver tests: verifying location resolution fallback chain.

Tests use real fake implementations to validate actual behavior.
Each test reads like plain English.

Coverage:
- Explicit location is returned as-is
- Default location from config is used
- Primary location is fetched from Shopify
- Location GID normalization
- Caching of primary location
- Error handling when no location available
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lib_shopify_graphql.adapters.location_resolver import (
    PRIMARY_LOCATION_QUERY,
    LocationResolver,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class FakeLocationGraphQLClient:
    """Fake GraphQL client for location resolution testing."""

    locations: list[dict[str, Any]] = field(default_factory=lambda: [])
    call_count: int = field(default=0, init=False)
    should_raise: Exception | None = field(default=None, init=False)

    def configure(self, shop_url: str, api_version: str, access_token: str) -> None:
        """Configure the GraphQL client (no-op for fake)."""

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute fake query, returning configured locations."""
        self.call_count += 1

        if self.should_raise:
            raise self.should_raise

        return {"data": {"locations": {"edges": [{"node": loc} for loc in self.locations]}}}

    def add_location(self, location_id: str, name: str, is_active: bool = True, is_primary: bool = False) -> None:
        """Add a location to the fake response."""
        self.locations.append(
            {
                "id": location_id,
                "name": name,
                "isActive": is_active,
                "isPrimary": is_primary,
            }
        )


@pytest.fixture
def fake_location_client() -> FakeLocationGraphQLClient:
    """Provide a fake GraphQL client for location testing."""
    return FakeLocationGraphQLClient()


# =============================================================================
# Explicit Location Priority
# =============================================================================


@pytest.mark.os_agnostic
class TestExplicitLocationPriority:
    """Explicit location parameter takes highest priority."""

    def test_explicit_gid_returned_as_is(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Explicit GID is returned without modification."""
        resolver = LocationResolver(fake_location_client)

        result = resolver.resolve(explicit_location="gid://shopify/Location/12345")

        assert result == "gid://shopify/Location/12345"
        assert fake_location_client.call_count == 0  # No API call needed

    def test_explicit_numeric_id_is_normalized(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Numeric location ID is converted to GID format."""
        resolver = LocationResolver(fake_location_client)

        result = resolver.resolve(explicit_location="12345")

        assert result == "gid://shopify/Location/12345"

    def test_explicit_overrides_default(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Explicit location overrides configured default."""
        resolver = LocationResolver(fake_location_client, default_location_id="gid://shopify/Location/default")

        result = resolver.resolve(explicit_location="gid://shopify/Location/explicit")

        assert result == "gid://shopify/Location/explicit"


# =============================================================================
# Default Location Fallback
# =============================================================================


@pytest.mark.os_agnostic
class TestDefaultLocationFallback:
    """Default location from config is used when no explicit provided."""

    def test_default_used_when_no_explicit(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Default location is used when no explicit location provided."""
        resolver = LocationResolver(fake_location_client, default_location_id="gid://shopify/Location/99999")

        result = resolver.resolve()

        assert result == "gid://shopify/Location/99999"
        assert fake_location_client.call_count == 0  # No API call needed

    def test_default_numeric_is_normalized(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Numeric default ID is converted to GID format."""
        resolver = LocationResolver(fake_location_client, default_location_id="99999")

        result = resolver.resolve()

        assert result == "gid://shopify/Location/99999"


# =============================================================================
# Primary Location Fetch
# =============================================================================


@pytest.mark.os_agnostic
class TestPrimaryLocationFetch:
    """Primary location is fetched from Shopify when needed."""

    def test_fetches_primary_location(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Primary location is fetched from Shopify API."""
        fake_location_client.add_location(
            "gid://shopify/Location/11111",
            "Warehouse 1",
            is_active=True,
            is_primary=True,
        )
        resolver = LocationResolver(fake_location_client)

        result = resolver.resolve()

        assert result == "gid://shopify/Location/11111"
        assert fake_location_client.call_count == 1

    def test_primary_location_is_cached(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Primary location is cached after first fetch."""
        fake_location_client.add_location(
            "gid://shopify/Location/11111",
            "Warehouse 1",
            is_active=True,
            is_primary=True,
        )
        resolver = LocationResolver(fake_location_client)

        resolver.resolve()
        resolver.resolve()
        resolver.resolve()

        assert fake_location_client.call_count == 1  # Only one API call

    def test_falls_back_to_first_active_location(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """First active location used when no primary found."""
        fake_location_client.add_location(
            "gid://shopify/Location/22222",
            "Store Front",
            is_active=True,
            is_primary=False,
        )
        resolver = LocationResolver(fake_location_client)

        result = resolver.resolve()

        assert result == "gid://shopify/Location/22222"


# =============================================================================
# Error Handling
# =============================================================================


@pytest.mark.os_agnostic
class TestErrorHandling:
    """Errors are handled gracefully."""

    def test_raises_when_no_location_available(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """ValueError raised when no location can be resolved."""
        resolver = LocationResolver(fake_location_client)  # No default, no locations

        with pytest.raises(ValueError, match="Could not resolve location"):
            resolver.resolve()

    def test_api_error_returns_none(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """API error results in no primary location (triggers ValueError)."""
        fake_location_client.should_raise = Exception("Network error")
        resolver = LocationResolver(fake_location_client)

        with pytest.raises(ValueError, match="Could not resolve location"):
            resolver.resolve()

    def test_inactive_location_not_used(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Inactive locations are not used."""
        fake_location_client.add_location(
            "gid://shopify/Location/33333",
            "Closed Warehouse",
            is_active=False,
            is_primary=False,
        )
        resolver = LocationResolver(fake_location_client)

        with pytest.raises(ValueError, match="Could not resolve location"):
            resolver.resolve()


# =============================================================================
# Cache Management
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheManagement:
    """Cache can be cleared to force refresh."""

    def test_clear_cache_forces_refetch(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Clearing cache forces new API call on next resolve."""
        fake_location_client.add_location(
            "gid://shopify/Location/11111",
            "Original",
            is_active=True,
            is_primary=True,
        )
        resolver = LocationResolver(fake_location_client)

        resolver.resolve()
        resolver.clear_cache()
        resolver.resolve()

        assert fake_location_client.call_count == 2  # Two API calls


# =============================================================================
# Query Definition
# =============================================================================


@pytest.mark.os_agnostic
class TestPrimaryLocationQuery:
    """PRIMARY_LOCATION_QUERY is correctly defined."""

    def test_query_includes_required_fields(self) -> None:
        """Query contains essential fields for location resolution."""
        assert "locations" in PRIMARY_LOCATION_QUERY
        assert "id" in PRIMARY_LOCATION_QUERY
        assert "isActive" in PRIMARY_LOCATION_QUERY
        assert "isPrimary" in PRIMARY_LOCATION_QUERY


# =============================================================================
# Initialization
# =============================================================================


@pytest.mark.os_agnostic
class TestResolverInitialization:
    """LocationResolver initializes correctly."""

    def test_stores_graphql_client(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Constructor stores GraphQL client reference."""
        resolver = LocationResolver(fake_location_client)

        assert resolver.graphql is fake_location_client

    def test_stores_default_location(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Constructor stores default location ID."""
        resolver = LocationResolver(fake_location_client, default_location_id="gid://loc/1")

        assert resolver.default_location_id == "gid://loc/1"

    def test_default_location_is_none_by_default(self, fake_location_client: FakeLocationGraphQLClient) -> None:
        """Default location is None when not provided."""
        resolver = LocationResolver(fake_location_client)

        assert resolver.default_location_id is None
