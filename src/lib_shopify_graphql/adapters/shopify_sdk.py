"""Shopify adapter implementing application ports.

This module provides concrete implementations of the application
layer ports using direct HTTP requests to Shopify's APIs.

Classes:
    - :class:`ShopifyTokenProvider`: OAuth token provider.
    - :class:`ShopifyGraphQLClient`: GraphQL query executor.
    - :class:`ShopifySessionManager`: Session lifecycle manager.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn

import orjson

from ..exceptions import AuthenticationError, GraphQLTimeoutError, SessionNotActiveError
from .constants import DEFAULT_GRAPHQL_TIMEOUT_SECONDS, DEFAULT_TOKEN_EXPIRES_IN_SECONDS

logger = logging.getLogger(__name__)


class ShopifyTokenProvider:
    """OAuth token provider using Shopify's token endpoint.

    Implements :class:`~lib_shopify_graphql.application.ports.TokenProviderPort`.
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
        request = self._build_token_request(shop_url, client_id, client_secret)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = orjson.loads(response.read())
            return self._parse_token_response(result, shop_url)
        except urllib.error.HTTPError as exc:
            self._handle_token_error(exc, shop_url)
        except Exception as exc:
            raise AuthenticationError(f"Failed to obtain access token: {exc}", shop_url=shop_url) from exc

    def _build_token_request(
        self,
        shop_url: str,
        client_id: str,
        client_secret: str,
    ) -> urllib.request.Request:
        """Build HTTP request for token endpoint."""
        url = f"https://{shop_url}/admin/oauth/access_token"
        data = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }
        ).encode("utf-8")
        return urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

    def _parse_token_response(
        self,
        result: dict[str, Any],
        shop_url: str,
    ) -> tuple[str, datetime]:
        """Parse token response and return access token with expiration."""
        access_token = result.get("access_token")
        if not access_token:
            raise AuthenticationError("No access token in response", shop_url=shop_url)
        expires_in = result.get("expires_in", DEFAULT_TOKEN_EXPIRES_IN_SECONDS)
        expiration = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        scopes = result.get("scope", "")
        logger.info(f"Obtained access token for shop '{shop_url}' (expires_in={expires_in}s, scopes='{scopes}')")
        return access_token, expiration

    def _handle_token_error(
        self,
        exc: urllib.error.HTTPError,
        shop_url: str,
    ) -> NoReturn:
        """Handle HTTP errors from token request. Always raises."""
        error_body = exc.read().decode("utf-8") if exc.fp else ""
        logger.error(
            "Failed to obtain access token",
            extra={"shop_url": shop_url, "status": exc.code, "body": error_body},
        )
        raise AuthenticationError(
            f"Failed to obtain access token: HTTP {exc.code} - {error_body}",
            shop_url=shop_url,
        ) from exc


class ShopifyGraphQLClient:
    """GraphQL client using direct HTTP requests.

    Implements :class:`~lib_shopify_graphql.application.ports.GraphQLClientPort`.

    Uses direct HTTP requests to ensure proper header handling
    with client credentials grant.

    Attributes:
        timeout: Request timeout in seconds. Defaults to DEFAULT_GRAPHQL_TIMEOUT_SECONDS.
        _endpoint: GraphQL endpoint URL (set via configure).
        _access_token: Access token for authentication (set via configure).

    Example:
        >>> client = ShopifyGraphQLClient(timeout=60.0)  # doctest: +SKIP
        >>> client.configure("mystore.myshopify.com", "2026-01", "token")  # doctest: +SKIP
        >>> result = client.execute("{ shop { name } }")  # doctest: +SKIP
    """

    def __init__(self, timeout: float = DEFAULT_GRAPHQL_TIMEOUT_SECONDS) -> None:
        """Initialize the GraphQL client.

        Args:
            timeout: Request timeout in seconds. Set to 0 or None to disable.
                Defaults to DEFAULT_GRAPHQL_TIMEOUT_SECONDS (30 seconds).
        """
        # Normalize: 0 or negative values mean "no timeout"
        self.timeout: float | None = timeout if timeout and timeout > 0 else None
        self._endpoint: str | None = None
        self._access_token: str | None = None

    def _get_effective_timeout(self) -> float | None:
        """Get the effective timeout value (None if disabled)."""
        return self.timeout

    def configure(self, shop_url: str, api_version: str, access_token: str) -> None:
        """Configure the GraphQL client with endpoint and credentials.

        Args:
            shop_url: Shopify store URL.
            api_version: Shopify API version.
            access_token: Access token for authentication.
        """
        self._endpoint = f"https://{shop_url}/admin/api/{api_version}/graphql.json"
        self._access_token = access_token

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
            GraphQLTimeoutError: If the request exceeds the configured timeout.
            SessionNotActiveError: If client is not configured.
        """
        if not self._endpoint or not self._access_token:
            raise SessionNotActiveError("GraphQL client not configured. Call login() first.")

        if self._get_effective_timeout() is None:
            return self._execute_query(query, variables)

        return self._execute_with_timeout(query, variables)

    def _execute_query(
        self,
        query: str,
        variables: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Execute query via direct HTTP request.

        Note: Caller must ensure client is configured (endpoint and token set).
        """
        # These are guaranteed non-None when called from execute()
        endpoint: str = self._endpoint  # type: ignore[assignment]
        access_token: str = self._access_token  # type: ignore[assignment]

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        data = orjson.dumps(payload)
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": access_token,
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self._get_effective_timeout()) as response:
            return orjson.loads(response.read())

    def _execute_with_timeout(
        self,
        query: str,
        variables: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Execute query with timeout using ThreadPoolExecutor."""
        # self.timeout is guaranteed to be a positive float when this method is called
        timeout_value: float = self.timeout  # type: ignore[assignment]
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._execute_query, query, variables)
            try:
                return future.result(timeout=timeout_value)
            except FuturesTimeoutError as exc:
                logger.warning(f"GraphQL query timed out after {timeout_value}s, query_preview='{query[:100]}...'")
                raise GraphQLTimeoutError(
                    f"GraphQL query timed out after {timeout_value} seconds",
                    timeout=timeout_value,
                    query=query,
                ) from exc


@dataclass(frozen=True)
class SessionInfo:
    """Lightweight session information container.

    Replaces the external shopify.Session dependency with a simple dataclass.

    Attributes:
        shop_url: Shopify store URL.
        api_version: Shopify API version.
        access_token: OAuth access token.
    """

    shop_url: str
    api_version: str
    access_token: str


class ShopifySessionManager:
    """Session manager for Shopify API.

    Implements :class:`~lib_shopify_graphql.application.ports.SessionManagerPort`.

    This is a lightweight implementation that doesn't depend on
    external libraries. Sessions are simple dataclasses containing
    the necessary authentication information.
    """

    def __init__(self) -> None:
        """Initialize the session manager."""
        self._active_session: SessionInfo | None = None

    def create_session(
        self,
        shop_url: str,
        api_version: str,
        access_token: str,
    ) -> SessionInfo:
        """Create a new Shopify API session.

        Args:
            shop_url: Shopify store URL.
            api_version: Shopify API version (format: YYYY-MM).
            access_token: OAuth access token.

        Returns:
            SessionInfo object containing session data.
        """
        return SessionInfo(
            shop_url=shop_url,
            api_version=api_version,
            access_token=access_token,
        )

    def activate_session(self, session: Any) -> None:
        """Activate a session for API calls.

        Args:
            session: SessionInfo object to activate.
        """
        if isinstance(session, SessionInfo):
            self._active_session = session

    def clear_session(self) -> None:
        """Clear/deactivate the current session."""
        self._active_session = None


__all__ = [
    "SessionInfo",
    "ShopifyGraphQLClient",
    "ShopifySessionManager",
    "ShopifyTokenProvider",
]
