"""Session management for Shopify API.

This module provides the ShopifySession class and login/logout functions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..application.ports import (
        GraphQLClientPort,
        SessionManagerPort,
        SKUResolverPort,
        TokenProviderPort,
    )

from ..adapters.parsers import format_graphql_errors, parse_graphql_errors
from ..exceptions import AuthenticationError, SessionNotActiveError
from ..models import ShopifyCredentials, ShopifySessionInfo
from ._common import _get_default_graphql_client, _get_default_session_manager, _get_default_token_provider

logger = logging.getLogger(__name__)


@dataclass
class ShopifySession:
    """Active Shopify session wrapper.

    Wraps session state with additional tracking and a clean API.
    Use :func:`login` to create a session and :func:`logout` to terminate it.

    For client credentials grant, the session automatically tracks token
    expiration and can be refreshed.

    Attributes:
        _credentials: The credentials used to create this session.
        _access_token: The current access token.
        _is_active: Whether the session is currently active.
        _token_expiration: When the access token expires.
        _raw_session: The underlying session object (implementation-specific).
        _token_provider: Port for refreshing tokens.
        _session_manager: Port for session lifecycle management.
        _graphql_client: Port for executing GraphQL queries.
        _sku_resolver: Optional SKU resolver for SKU-to-GID lookups.
    """

    _credentials: ShopifyCredentials
    _access_token: str
    _is_active: bool = field(default=True)
    _token_expiration: datetime | None = field(default=None)
    _raw_session: Any = field(default=None)
    _token_provider: TokenProviderPort = field(default_factory=_get_default_token_provider)
    _session_manager: SessionManagerPort = field(default_factory=_get_default_session_manager)
    _graphql_client: GraphQLClientPort = field(default_factory=_get_default_graphql_client)
    _sku_resolver: SKUResolverPort | None = field(default=None)

    @property
    def is_active(self) -> bool:
        """Whether the session is currently active."""
        return self._is_active

    @property
    def info(self) -> ShopifySessionInfo:
        """Read-only session information."""
        return ShopifySessionInfo(
            shop_url=self._credentials.shop_url,
            api_version=self._credentials.api_version,
            is_active=self._is_active,
            token_expiration=self._token_expiration,
        )

    def get_credentials(self) -> ShopifyCredentials:
        """Get the credentials used for this session."""
        return self._credentials

    def get_raw_session(self) -> Any:
        """Get the underlying session object."""
        return self._raw_session

    def mark_inactive(self) -> None:
        """Mark this session as inactive (internal use by logout)."""
        object.__setattr__(self, "_is_active", False)

    def clear_session(self) -> None:
        """Clear the underlying session (internal use by logout)."""
        self._session_manager.clear_session()

    def is_token_expired(self) -> bool:
        """Check if the access token has expired."""
        if self._token_expiration is None:
            return False
        return datetime.now(timezone.utc) >= self._token_expiration

    def refresh_token(self) -> None:
        """Refresh the access token using stored credentials.

        For direct access tokens (Custom Apps), this is a no-op since they don't expire.
        For OAuth tokens (Partner Apps), obtains a new token via client credentials grant.

        Raises:
            AuthenticationError: If client credentials are not available for OAuth refresh.
        """
        # Direct access tokens don't expire - nothing to refresh
        if self._credentials.access_token:
            logger.debug("Direct access token - no refresh needed")
            return

        # OAuth tokens require client credentials
        if not self._credentials.client_id or not self._credentials.client_secret:
            raise AuthenticationError(
                "Cannot refresh token: client credentials not available",
                shop_url=self._credentials.shop_url,
            )

        new_token, new_expiration = self._token_provider.obtain_token(
            self._credentials.shop_url,
            self._credentials.client_id,
            self._credentials.client_secret,
        )
        new_session = self._session_manager.create_session(
            self._credentials.shop_url,
            self._credentials.api_version,
            new_token,
        )
        self._session_manager.activate_session(new_session)
        # Reconfigure GraphQL client with new token
        self._graphql_client.configure(
            self._credentials.shop_url,
            self._credentials.api_version,
            new_token,
        )
        object.__setattr__(self, "_raw_session", new_session)
        object.__setattr__(self, "_access_token", new_token)
        object.__setattr__(self, "_token_expiration", new_expiration)
        logger.info(f"Refreshed access token for shop '{self._credentials.shop_url}'")

    def execute_graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query using this session.

        Args:
            query: GraphQL query string.
            variables: Optional query variables.

        Returns:
            Parsed JSON response as a dictionary.
        """
        self._session_manager.activate_session(self._raw_session)
        return self._graphql_client.execute(query, variables)


def _parse_shop_name_from_response(data: dict[str, Any]) -> str:
    """Parse shop name from GraphQL response.

    Args:
        data: Raw GraphQL response from shop query.

    Returns:
        Shop name string, or "Unknown" if not found.
    """
    data_field: dict[str, Any] | None = data.get("data")  # type: ignore[assignment]
    if not isinstance(data_field, dict):
        return "Unknown"
    shop_field: dict[str, Any] | None = data_field.get("shop")  # type: ignore[assignment]
    if not isinstance(shop_field, dict):
        return "Unknown"
    name: str | None = shop_field.get("name")  # type: ignore[assignment]
    return str(name) if name is not None else "Unknown"


def _verify_authentication(session: ShopifySession, credentials: ShopifyCredentials) -> str:
    """Verify authentication by querying shop name.

    Args:
        session: Active ShopifySession to verify.
        credentials: Credentials used for authentication.

    Returns:
        Shop name if authentication is successful.

    Raises:
        AuthenticationError: If the GraphQL query returns errors.
    """
    data = session.execute_graphql(query="{ shop { name } }")
    errors_list = data.get("errors")
    if errors_list:
        parsed_errors = parse_graphql_errors(errors_list)
        formatted_message = format_graphql_errors(parsed_errors)
        raise AuthenticationError(
            f"Invalid credentials: {formatted_message}",
            shop_url=credentials.shop_url,
        )
    return _parse_shop_name_from_response(data)


def login(
    credentials: ShopifyCredentials,
    *,
    token_provider: TokenProviderPort | None = None,
    session_manager: SessionManagerPort | None = None,
    graphql_client: GraphQLClientPort | None = None,
) -> ShopifySession:
    """Authenticate with Shopify and create an active session.

    Supports two authentication methods:

    1. **Direct Access Token** (for Custom Apps):
       If ``credentials.access_token`` is provided, uses it directly.
       Custom Apps created in Shopify Admin provide a static access token
       (starts with ``shpat_``) that doesn't expire.

    2. **Client Credentials Grant** (for Partner Apps):
       If ``credentials.client_id`` and ``credentials.client_secret`` are
       provided, obtains an access token via OAuth 2.0 client credentials
       grant. Tokens are valid for 24 hours.

    Args:
        credentials: Shopify credentials containing shop_url, api_version,
            and either access_token OR (client_id + client_secret).
        token_provider: Optional custom token provider (for testing/DI).
        session_manager: Optional custom session manager (for testing/DI).
        graphql_client: Optional custom GraphQL client (for testing/DI).

    Returns:
        An active ShopifySession ready for API calls.

    Raises:
        AuthenticationError: If authentication fails or credentials are invalid.
    """
    # Use provided adapters or defaults from composition root
    # Token provider uses get_default_token_provider() which auto-enables caching if configured
    if token_provider is None:
        from ..composition import get_default_token_provider

        tp: TokenProviderPort = get_default_token_provider()
    else:
        tp = token_provider
    sm: SessionManagerPort = session_manager or _get_default_session_manager()
    gc: GraphQLClientPort = graphql_client or _get_default_graphql_client()

    try:
        access_token, token_expiration = _obtain_access_token(credentials, tp)
        raw_session = sm.create_session(
            credentials.shop_url,
            credentials.api_version,
            access_token,
        )
        sm.activate_session(raw_session)

        # Configure GraphQL client with endpoint and token
        gc.configure(credentials.shop_url, credentials.api_version, access_token)

        # SKU resolver uses get_default_sku_resolver() which auto-enables caching if configured
        from ..composition import get_default_sku_resolver

        sku_resolver = get_default_sku_resolver(gc)

        session = ShopifySession(
            _credentials=credentials,
            _access_token=access_token,
            _is_active=True,
            _token_expiration=token_expiration,
            _raw_session=raw_session,
            _token_provider=tp,
            _session_manager=sm,
            _graphql_client=gc,
            _sku_resolver=sku_resolver,
        )

        shop_name = _verify_authentication(session, credentials)
        logger.info(f"Successfully authenticated with Shopify: shop='{shop_name}', url='{credentials.shop_url}'")
        return session
    except AuthenticationError:
        raise
    except Exception as exc:
        logger.error(f"Failed to authenticate with Shopify for shop '{credentials.shop_url}': {exc}")
        raise AuthenticationError(f"Failed to authenticate with Shopify: {exc}", shop_url=credentials.shop_url) from exc


def _obtain_access_token(
    credentials: ShopifyCredentials,
    token_provider: TokenProviderPort,
) -> tuple[str, datetime | None]:
    """Obtain access token using direct token or OAuth flow.

    Args:
        credentials: Shopify credentials.
        token_provider: Token provider for OAuth flow.

    Returns:
        Tuple of (access_token, expiration). Expiration is None for direct tokens.

    Raises:
        AuthenticationError: If neither direct token nor OAuth credentials provided.
    """
    # Direct access token (Custom Apps)
    if credentials.access_token:
        logger.info(f"Authenticating with Shopify using direct access token: shop='{credentials.shop_url}', api_version='{credentials.api_version}'")
        return credentials.access_token, None

    # Client Credentials Grant (Partner Apps)
    if credentials.client_id and credentials.client_secret:
        logger.info(f"Authenticating with Shopify via client credentials grant: shop='{credentials.shop_url}', api_version='{credentials.api_version}'")
        return token_provider.obtain_token(
            credentials.shop_url,
            credentials.client_id,
            credentials.client_secret,
        )

    # Neither method available
    raise AuthenticationError(
        "Either access_token OR (client_id + client_secret) must be provided",
        shop_url=credentials.shop_url,
    )


def logout(session: ShopifySession) -> None:
    """Terminate an active Shopify session.

    Clears the session and marks it as inactive. After logout,
    the session cannot be used for API calls.

    Args:
        session: An active ShopifySession to terminate.

    Raises:
        SessionNotActiveError: If the session is already inactive.
    """
    if not session.is_active:
        raise SessionNotActiveError("Cannot logout: session is already inactive")
    logger.info(f"Logging out from Shopify: shop='{session.get_credentials().shop_url}'")
    try:
        session.clear_session()
        session.mark_inactive()
        logger.info("Successfully logged out from Shopify")
    except Exception as exc:
        logger.error(f"Error during logout: {exc}")
        session.mark_inactive()
        raise


__all__ = [
    "ShopifySession",
    "login",
    "logout",
]
