"""Location resolver with fallback chain.

This module provides location resolution for inventory operations.

Classes:
    - :class:`LocationResolver`: Location resolver with config fallback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..application.ports import GraphQLClientPort

logger = logging.getLogger(__name__)


# GraphQL query to get shop's primary location
PRIMARY_LOCATION_QUERY = """
query PrimaryLocation {
    locations(first: 1, query: "active:true") {
        edges {
            node {
                id
                name
                isActive
                isPrimary
            }
        }
    }
}
"""


class LocationResolver:
    """Location resolver with fallback chain for inventory operations.

    Implements :class:`~lib_shopify_graphql.application.ports.LocationResolverPort`.

    Fallback chain:
    1. Explicit location from parameter
    2. Default location from configuration
    3. Shop's primary location (auto-fetched and cached)

    Attributes:
        graphql: GraphQL client for Shopify API queries.
        default_location_id: Default location from configuration.

    Example:
        >>> resolver = LocationResolver(graphql_client)
        >>> # Uses explicit location
        >>> loc = resolver.resolve(explicit_location="gid://shopify/Location/123")
        >>> # Uses configured default
        >>> resolver = LocationResolver(graphql_client, default_location_id="gid://...")
        >>> loc = resolver.resolve()
        >>> # Fetches primary location from Shopify
        >>> resolver = LocationResolver(graphql_client)
        >>> loc = resolver.resolve()  # Queries Shopify API
    """

    def __init__(
        self,
        graphql: GraphQLClientPort,
        default_location_id: str | None = None,
    ) -> None:
        """Initialize the location resolver.

        Args:
            graphql: GraphQL client for Shopify API queries.
            default_location_id: Default location GID from configuration.
                If not provided, will fetch shop's primary location.
        """
        self.graphql = graphql
        self.default_location_id = default_location_id
        self._primary_location_cache: str | None = None

    def resolve(self, explicit_location: str | None = None) -> str:
        """Resolve the location to use for inventory operations.

        Args:
            explicit_location: Explicitly provided location GID.
                If provided, returned as-is (normalized if needed).

        Returns:
            Location GID to use.

        Raises:
            ValueError: If no location can be resolved.
        """
        # 1. Explicit location takes priority
        if explicit_location:
            return self._normalize_location_gid(explicit_location)

        # 2. Default from config
        if self.default_location_id:
            return self._normalize_location_gid(self.default_location_id)

        # 3. Fetch primary location (cached for session)
        if self._primary_location_cache is None:
            self._primary_location_cache = self._fetch_primary_location()

        if self._primary_location_cache is None:
            msg = "Could not resolve location: no explicit, default, or primary location available"
            raise ValueError(msg)

        return self._primary_location_cache

    def _normalize_location_gid(self, location_id: str) -> str:
        """Normalize location ID to GID format.

        Args:
            location_id: Location ID (GID or numeric).

        Returns:
            Full GID format.
        """
        if location_id.startswith("gid://"):
            return location_id
        return f"gid://shopify/Location/{location_id}"

    def _fetch_primary_location(self) -> str | None:
        """Fetch the shop's primary location from Shopify.

        Returns:
            Primary location GID, or None if not found.
        """
        try:
            result: dict[str, Any] = self.graphql.execute(PRIMARY_LOCATION_QUERY)
            edges = result.get("data", {}).get("locations", {}).get("edges", [])

            # Look for primary location first
            for edge in edges:
                node = edge.get("node", {})
                if node.get("isPrimary") and node.get("isActive"):
                    location_id = node.get("id")
                    logger.info(f"Fetched primary location '{location_id}' (name='{node.get('name')}')")
                    return location_id

            # Fall back to first active location
            if edges:
                node = edges[0].get("node", {})
                if node.get("isActive"):
                    location_id = node.get("id")
                    logger.info(f"Using first active location '{location_id}' (name='{node.get('name')}') - no primary found")
                    return location_id

            logger.warning("No active locations found")
            return None

        except Exception as exc:
            logger.error("Failed to fetch primary location", extra={"error": str(exc)})
            return None

    def clear_cache(self) -> None:
        """Clear the primary location cache.

        Call this if the shop's locations change and you need
        to re-fetch the primary location.
        """
        self._primary_location_cache = None


__all__ = ["LocationResolver", "PRIMARY_LOCATION_QUERY"]
