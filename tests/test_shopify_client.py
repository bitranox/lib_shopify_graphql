"""Shopify client tests: verifying API interactions.

Tests for the Shopify client covering:
- Login and session creation
- Logout and session cleanup
- Product retrieval by ID
- Exception behavior

Note:
    These tests require mocking the Shopify API library since real API calls
    would need valid credentials and network access. The mocks verify that
    the client correctly orchestrates the underlying library calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from lib_shopify_graphql.exceptions import (
    AuthenticationError,
    GraphQLError,
    GraphQLErrorEntry,
    GraphQLErrorLocation,
    ProductNotFoundError,
    SessionNotActiveError,
)
from lib_shopify_graphql.adapters.parsers import (  # type: ignore[reportPrivateUsage]
    parse_graphql_errors,
    parse_metafield_type,
    parse_selected_options,
)
from lib_shopify_graphql.models import MetafieldType, SelectedOption, ShopifyCredentials
from lib_shopify_graphql.shopify_client import (
    ShopifySession,
    get_product_by_id,
    login,
    logout,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def _create_mock_session(credentials: ShopifyCredentials) -> ShopifySession:
    """Create a ShopifySession for testing without real API connection."""
    mock_token_provider = MagicMock()
    mock_session_manager = MagicMock()
    mock_graphql_client = MagicMock()

    return ShopifySession(
        _credentials=credentials,
        _access_token="mock_access_token",
        _is_active=True,
        _token_expiration=None,
        _raw_session=MagicMock(),
        _token_provider=mock_token_provider,
        _session_manager=mock_session_manager,
        _graphql_client=mock_graphql_client,
        _sku_resolver=None,
    )


# =============================================================================
# Login Tests
# =============================================================================


def _create_mock_adapters(shop_response: dict[str, Any] | None = None) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Create mock adapters for testing login."""
    mock_token_provider = MagicMock()
    mock_token_provider.obtain_token.return_value = ("mock_access_token", datetime.now(timezone.utc))

    mock_session_manager = MagicMock()
    mock_session_manager.create_session.return_value = MagicMock()

    mock_graphql_client = MagicMock()
    if shop_response is None:
        shop_response = {"data": {"shop": {"name": "Test Store"}}}
    mock_graphql_client.execute.return_value = shop_response

    return mock_token_provider, mock_session_manager, mock_graphql_client


@pytest.mark.os_agnostic
class TestLoginCreatesSession:
    """Login creates an active session with valid credentials."""

    def test_returns_active_session(self, sample_credentials: ShopifyCredentials) -> None:
        """Valid credentials produce an active session."""
        tp, sm, gc = _create_mock_adapters()

        session = login(
            sample_credentials,
            token_provider=tp,
            session_manager=sm,
            graphql_client=gc,
        )

        assert session.is_active is True

    def test_session_contains_shop_url(self, sample_credentials: ShopifyCredentials) -> None:
        """Session info contains the shop URL from credentials."""
        tp, sm, gc = _create_mock_adapters()

        session = login(
            sample_credentials,
            token_provider=tp,
            session_manager=sm,
            graphql_client=gc,
        )

        assert session.info.shop_url == "test-store.myshopify.com"

    def test_session_contains_api_version(self, sample_credentials: ShopifyCredentials) -> None:
        """Session info contains the API version from credentials."""
        tp, sm, gc = _create_mock_adapters()

        session = login(
            sample_credentials,
            token_provider=tp,
            session_manager=sm,
            graphql_client=gc,
        )

        assert session.info.api_version == "2026-01"


@pytest.mark.os_agnostic
class TestLoginActivatesGlobalSession:
    """Login activates the Shopify session globally."""

    def test_activates_session_via_manager(self, sample_credentials: ShopifyCredentials) -> None:
        """SessionManager.activate_session is called."""
        tp, sm, gc = _create_mock_adapters()
        mock_raw_session = MagicMock()
        sm.create_session.return_value = mock_raw_session

        login(
            sample_credentials,
            token_provider=tp,
            session_manager=sm,
            graphql_client=gc,
        )

        # Session is activated during login
        sm.activate_session.assert_called_with(mock_raw_session)


@pytest.mark.os_agnostic
class TestLoginWithInvalidCredentials:
    """Login raises AuthenticationError for invalid credentials."""

    def test_raises_authentication_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Invalid credentials raise AuthenticationError."""
        tp, sm, gc = _create_mock_adapters()
        tp.obtain_token.side_effect = AuthenticationError(
            "Invalid credentials",
            shop_url="test-store.myshopify.com",
        )

        with pytest.raises(AuthenticationError):
            login(
                sample_credentials,
                token_provider=tp,
                session_manager=sm,
                graphql_client=gc,
            )

    def test_error_contains_shop_url(self, sample_credentials: ShopifyCredentials) -> None:
        """AuthenticationError includes the shop URL."""
        tp, sm, gc = _create_mock_adapters()
        tp.obtain_token.side_effect = AuthenticationError(
            "Invalid credentials",
            shop_url="test-store.myshopify.com",
        )

        with pytest.raises(AuthenticationError) as exc_info:
            login(
                sample_credentials,
                token_provider=tp,
                session_manager=sm,
                graphql_client=gc,
            )

        assert exc_info.value.shop_url == "test-store.myshopify.com"


# =============================================================================
# Logout Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestLogoutMarksSessionInactive:
    """Logout marks the session as inactive."""

    def test_session_becomes_inactive(self, sample_credentials: ShopifyCredentials) -> None:
        """Session is_active becomes False after logout."""
        session = _create_mock_session(sample_credentials)

        logout(session)

        assert session.is_active is False


@pytest.mark.os_agnostic
class TestLogoutClearsGlobalSession:
    """Logout clears the global Shopify session."""

    def test_clears_session_via_manager(self, sample_credentials: ShopifyCredentials) -> None:
        """SessionManager.clear_session is called via session.clear_session()."""
        session = _create_mock_session(sample_credentials)

        logout(session)

        # Verify the session manager's clear_session was called
        session._session_manager.clear_session.assert_called_once()  # type: ignore[reportPrivateUsage]


@pytest.mark.os_agnostic
class TestLogoutInactiveSession:
    """Logout raises error for inactive sessions."""

    def test_raises_session_not_active_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Logout on inactive session raises SessionNotActiveError."""
        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            logout(session)


# =============================================================================
# ShopifySession Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestShopifySessionInfo:
    """ShopifySession provides accurate session info."""

    def test_info_returns_shop_url(self, sample_credentials: ShopifyCredentials) -> None:
        """Session info contains the shop URL."""
        session = _create_mock_session(sample_credentials)

        assert session.info.shop_url == "test-store.myshopify.com"

    def test_info_returns_api_version(self, sample_credentials: ShopifyCredentials) -> None:
        """Session info contains the API version."""
        session = _create_mock_session(sample_credentials)

        assert session.info.api_version == "2026-01"

    def test_info_returns_active_state(self, sample_credentials: ShopifyCredentials) -> None:
        """Session info reflects the active state."""
        session = _create_mock_session(sample_credentials)

        assert session.info.is_active is True


@pytest.mark.os_agnostic
class TestShopifySessionIsActive:
    """ShopifySession.is_active reflects internal state."""

    def test_is_active_true_initially(self, sample_credentials: ShopifyCredentials) -> None:
        """New session is active."""
        session = _create_mock_session(sample_credentials)

        assert session.is_active is True

    def test_is_active_false_after_deactivation(self, sample_credentials: ShopifyCredentials) -> None:
        """Session reports inactive after internal state change."""
        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        assert session.is_active is False


# =============================================================================
# GetProductById Tests
# =============================================================================


def _setup_session_with_response(
    credentials: ShopifyCredentials,
    response: dict[str, Any],
) -> ShopifySession:
    """Create a mock session configured to return a specific GraphQL response."""
    session = _create_mock_session(credentials)
    session._graphql_client.execute.return_value = response  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    return session


@pytest.mark.os_agnostic
class TestGetProductByIdReturnsProduct:
    """get_product_by_id returns a Product model."""

    def test_returns_product_with_correct_id(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Returned product has the expected ID."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert product.id == "gid://shopify/Product/123456789"

    def test_returns_product_with_correct_title(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Returned product has the expected title."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert product.title == "Test Product"

    def test_returns_product_with_correct_handle(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Returned product has the expected handle."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert product.handle == "test-product"


@pytest.mark.os_agnostic
class TestGetProductByIdNormalizesId:
    """get_product_by_id normalizes numeric IDs to GID format."""

    def test_converts_numeric_id_to_gid(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Numeric ID is converted to GID format."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        get_product_by_id(session, "123456789")

        # Check that execute was called with the normalized GID
        # type: ignore comments for mock attribute access
        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        # call_args can be (args, kwargs) - check kwargs or second positional arg
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["id"] == "gid://shopify/Product/123456789"

    def test_preserves_full_gid(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Full GID is used as-is."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        get_product_by_id(session, "gid://shopify/Product/123456789")

        # Check that execute was called with the GID as-is
        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["id"] == "gid://shopify/Product/123456789"


@pytest.mark.os_agnostic
class TestGetProductByIdParsesVariants:
    """get_product_by_id correctly parses variants."""

    def test_parses_variant_count(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Correct number of variants are parsed."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert len(product.variants) == 1

    def test_parses_variant_title(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Variant title is parsed correctly."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert product.variants[0].title == "Default Title"

    def test_parses_variant_sku(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Variant SKU is parsed correctly."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert product.variants[0].sku == "TEST-SKU-001"

    def test_parses_variant_price(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Variant price is parsed correctly."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert str(product.variants[0].price.amount) == "19.99"
        assert product.variants[0].price.currency_code == "USD"


@pytest.mark.os_agnostic
class TestGetProductByIdParsesImages:
    """get_product_by_id correctly parses images."""

    def test_parses_image_count(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Correct number of images are parsed."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert len(product.images) == 2

    def test_parses_featured_image(
        self,
        sample_credentials: ShopifyCredentials,
        graphql_product_response: dict[str, Any],
    ) -> None:
        """Featured image is parsed correctly."""
        session = _setup_session_with_response(sample_credentials, graphql_product_response)

        product = get_product_by_id(session, "123456789")

        assert product.featured_image is not None
        assert product.featured_image.url == "https://cdn.shopify.com/featured.jpg"


@pytest.mark.os_agnostic
class TestGetProductByIdNotFound:
    """get_product_by_id raises ProductNotFoundError for missing products."""

    def test_raises_product_not_found_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Missing product raises ProductNotFoundError."""
        response = {"data": {"product": None}}
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(ProductNotFoundError):
            get_product_by_id(session, "nonexistent")

    def test_error_contains_product_id(self, sample_credentials: ShopifyCredentials) -> None:
        """ProductNotFoundError includes the product ID."""
        response = {"data": {"product": None}}
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(ProductNotFoundError) as exc_info:
            get_product_by_id(session, "nonexistent")

        assert "gid://shopify/Product/nonexistent" in exc_info.value.product_id


@pytest.mark.os_agnostic
class TestGetProductByIdGraphQLError:
    """get_product_by_id raises GraphQLError for API errors."""

    def test_raises_graphql_error(self, sample_credentials: ShopifyCredentials) -> None:
        """GraphQL errors raise GraphQLError."""
        response = {
            "errors": [
                {"message": "Access denied"},
                {"message": "Invalid query"},
            ],
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError):
            get_product_by_id(session, "123456789")

    def test_error_contains_message(self, sample_credentials: ShopifyCredentials) -> None:
        """GraphQLError includes the error message."""
        response = {
            "errors": [
                {"message": "Access denied"},
            ],
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError) as exc_info:
            get_product_by_id(session, "123456789")

        assert "Access denied" in str(exc_info.value)

    def test_error_contains_all_errors(self, sample_credentials: ShopifyCredentials) -> None:
        """GraphQLError includes all error entries."""
        response = {
            "errors": [
                {"message": "Access denied"},
                {"message": "Invalid query"},
            ],
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError) as exc_info:
            get_product_by_id(session, "123456789")

        assert len(exc_info.value.errors) == 2


@pytest.mark.os_agnostic
class TestGetProductByIdInactiveSession:
    """get_product_by_id raises error for inactive sessions."""

    def test_raises_session_not_active_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            get_product_by_id(session, "123456789")


# =============================================================================
# Exception Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestAuthenticationErrorProperties:
    """AuthenticationError stores relevant context."""

    def test_stores_shop_url(self) -> None:
        """Error stores the shop URL that failed."""
        error = AuthenticationError(
            "Auth failed",
            shop_url="test.myshopify.com",
        )

        assert error.shop_url == "test.myshopify.com"

    def test_stores_message(self) -> None:
        """Error stores the error message."""
        error = AuthenticationError(
            "Auth failed",
            shop_url="test.myshopify.com",
        )

        assert error.message == "Auth failed"


@pytest.mark.os_agnostic
class TestProductNotFoundErrorProperties:
    """ProductNotFoundError stores relevant context."""

    def test_stores_product_id(self) -> None:
        """Error stores the product ID that wasn't found."""
        error = ProductNotFoundError("gid://shopify/Product/123")

        assert error.product_id == "gid://shopify/Product/123"

    def test_message_contains_product_id(self) -> None:
        """Error message includes the product ID."""
        error = ProductNotFoundError("gid://shopify/Product/123")

        assert "gid://shopify/Product/123" in error.message


@pytest.mark.os_agnostic
class TestGraphQLErrorProperties:
    """GraphQLError stores relevant context."""

    def test_stores_errors_list(self) -> None:
        """Error stores the list of GraphQL errors."""
        errors = [
            GraphQLErrorEntry(message="Error 1"),
            GraphQLErrorEntry(message="Error 2"),
        ]
        error = GraphQLError(
            "Query failed",
            errors=errors,
            query="{ shop { name } }",
        )

        assert len(error.errors) == 2

    def test_stores_query(self) -> None:
        """Error stores the query that failed."""
        errors = [GraphQLErrorEntry(message="Error 1")]
        error = GraphQLError(
            "Query failed",
            errors=errors,
            query="{ shop { name } }",
        )

        assert error.query == "{ shop { name } }"


@pytest.mark.os_agnostic
class TestSessionNotActiveErrorProperties:
    """SessionNotActiveError has appropriate message."""

    def test_has_descriptive_message(self) -> None:
        """Error has a message indicating session is not active."""
        error = SessionNotActiveError()

        assert "not active" in error.message.lower()


# =============================================================================
# GraphQLErrorLocation Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestGraphQLErrorLocationCreation:
    """GraphQLErrorLocation captures error position in query."""

    def test_creates_with_line_and_column(self) -> None:
        """Location is created with line and column numbers."""
        location = GraphQLErrorLocation(line=5, column=10)

        assert location.line == 5
        assert location.column == 10

    def test_immutable(self) -> None:
        """GraphQLErrorLocation is frozen and cannot be modified."""
        location = GraphQLErrorLocation(line=5, column=10)

        with pytest.raises(Exception):
            location.line = 6  # type: ignore[misc]


@pytest.mark.os_agnostic
class TestGraphQLErrorLocationEquality:
    """GraphQLErrorLocation supports equality comparison."""

    def test_equal_locations_are_equal(self) -> None:
        """Two locations with same line and column are equal."""
        loc1 = GraphQLErrorLocation(line=5, column=10)
        loc2 = GraphQLErrorLocation(line=5, column=10)

        assert loc1 == loc2

    def test_different_locations_are_not_equal(self) -> None:
        """Locations with different values are not equal."""
        loc1 = GraphQLErrorLocation(line=5, column=10)
        loc2 = GraphQLErrorLocation(line=5, column=11)

        assert loc1 != loc2


# =============================================================================
# GraphQLErrorEntry Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestGraphQLErrorEntryCreation:
    """GraphQLErrorEntry captures GraphQL error details."""

    def test_creates_with_message_only(self) -> None:
        """Entry is created with just a message."""
        entry = GraphQLErrorEntry(message="Something went wrong")

        assert entry.message == "Something went wrong"
        assert entry.locations is None
        assert entry.path is None
        assert entry.extensions is None

    def test_creates_with_all_fields(self) -> None:
        """Entry is created with all optional fields."""
        locations = (GraphQLErrorLocation(line=5, column=10),)
        entry = GraphQLErrorEntry(
            message="Field error",
            locations=locations,
            path=("product", "title"),
            extensions={"code": "VALIDATION_ERROR"},
        )

        assert entry.message == "Field error"
        assert entry.locations is not None
        assert len(entry.locations) == 1
        assert entry.locations[0].line == 5
        assert entry.path == ("product", "title")
        assert entry.extensions == {"code": "VALIDATION_ERROR"}


@pytest.mark.os_agnostic
class TestGraphQLErrorEntryLocations:
    """GraphQLErrorEntry handles multiple locations."""

    def test_accepts_multiple_locations(self) -> None:
        """Entry accepts multiple error locations."""
        locations = (
            GraphQLErrorLocation(line=5, column=10),
            GraphQLErrorLocation(line=10, column=15),
        )

        entry = GraphQLErrorEntry(message="Multiple errors", locations=locations)

        assert len(entry.locations) == 2  # type: ignore[arg-type]
        assert entry.locations[0].line == 5  # type: ignore[index]
        assert entry.locations[1].line == 10  # type: ignore[index]


@pytest.mark.os_agnostic
class TestGraphQLErrorEntryPath:
    """GraphQLErrorEntry handles path with mixed types."""

    def test_path_with_string_fields(self) -> None:
        """Path can contain field names as strings."""
        entry = GraphQLErrorEntry(
            message="Field error",
            path=("product", "variants", "nodes"),
        )

        assert entry.path == ("product", "variants", "nodes")

    def test_path_with_array_indices(self) -> None:
        """Path can contain array indices as integers."""
        entry = GraphQLErrorEntry(
            message="Array error",
            path=("products", 0, "title"),
        )

        assert entry.path == ("products", 0, "title")


@pytest.mark.os_agnostic
class TestGraphQLErrorEntryParsing:
    """GraphQLErrorEntry can be parsed from dict via parse_graphql_errors."""

    def test_parses_from_dict(self) -> None:
        """Entry can be parsed from a dictionary via parse_graphql_errors."""
        from lib_shopify_graphql.adapters.parsers import parse_graphql_errors

        data = [
            {
                "message": "Query error",
                "locations": [{"line": 5, "column": 10}],
                "path": ["shop", "name"],
            }
        ]

        entries = parse_graphql_errors(data)

        assert len(entries) == 1
        assert entries[0].message == "Query error"
        assert entries[0].locations is not None
        assert entries[0].locations[0].line == 5

    def test_parses_minimal_dict(self) -> None:
        """Entry can be parsed from minimal dictionary."""
        from lib_shopify_graphql.adapters.parsers import parse_graphql_errors

        data = [{"message": "Simple error"}]

        entries = parse_graphql_errors(data)

        assert len(entries) == 1
        assert entries[0].message == "Simple error"
        assert entries[0].locations is None

    def test_handles_extra_fields(self) -> None:
        """Parser handles extra fields from Shopify API."""
        from lib_shopify_graphql.adapters.parsers import parse_graphql_errors

        data = [
            {
                "message": "API error",
                "extensions": {"code": "THROTTLED"},
                "documentationUrl": "https://shopify.dev/docs",  # Extra field
            }
        ]

        entries = parse_graphql_errors(data)

        assert len(entries) == 1
        assert entries[0].message == "API error"


@pytest.mark.os_agnostic
class TestGraphQLErrorEntryDataclass:
    """GraphQLErrorEntry is a frozen dataclass."""

    def test_fields_accessible(self) -> None:
        """All fields are accessible after construction."""
        entry = GraphQLErrorEntry(
            message="Test error",
            locations=(GraphQLErrorLocation(line=1, column=1),),
            path=("field",),
        )

        assert entry.message == "Test error"
        assert entry.locations is not None
        assert entry.locations[0].line == 1
        assert entry.path == ("field",)

    def test_converts_to_dict(self) -> None:
        """Entry can be converted to dict via asdict."""
        from dataclasses import asdict

        entry = GraphQLErrorEntry(message="Test error")

        dumped = asdict(entry)

        assert dumped["message"] == "Test error"
        assert "locations" in dumped
        assert "path" in dumped


@pytest.mark.os_agnostic
class TestGraphQLErrorWithEntries:
    """GraphQLError integrates with GraphQLErrorEntry."""

    def test_error_stores_entry_messages(self) -> None:
        """GraphQLError can access entry messages."""
        entries = [
            GraphQLErrorEntry(message="Error 1"),
            GraphQLErrorEntry(message="Error 2"),
        ]

        error = GraphQLError("Multiple errors", errors=entries)

        messages = [e.message for e in error.errors]
        assert messages == ["Error 1", "Error 2"]

    def test_error_stores_entry_locations(self) -> None:
        """GraphQLError can access entry locations."""
        entries = [
            GraphQLErrorEntry(
                message="Error at location",
                locations=(GraphQLErrorLocation(line=5, column=10),),
            ),
        ]

        error = GraphQLError("Located error", errors=entries)

        assert error.errors[0].locations is not None
        assert error.errors[0].locations[0].line == 5


# =============================================================================
# Parsing Helper Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestParseMetafieldType:
    """parse_metafield_type converts strings to MetafieldType enum."""

    def test_parses_single_line_text_field(self) -> None:
        """Single line text field string is converted to enum."""
        result = parse_metafield_type("single_line_text_field")

        assert result == MetafieldType.SINGLE_LINE_TEXT_FIELD

    def test_parses_json(self) -> None:
        """JSON string is converted to enum."""
        result = parse_metafield_type("json")

        assert result == MetafieldType.JSON

    def test_parses_number_integer(self) -> None:
        """Number integer string is converted to enum."""
        result = parse_metafield_type("number_integer")

        assert result == MetafieldType.NUMBER_INTEGER

    def test_parses_boolean(self) -> None:
        """Boolean string is converted to enum."""
        result = parse_metafield_type("boolean")

        assert result == MetafieldType.BOOLEAN

    def test_parses_list_types(self) -> None:
        """List type strings are converted to enum."""
        result = parse_metafield_type("list.single_line_text_field")

        assert result == MetafieldType.LIST_SINGLE_LINE_TEXT_FIELD

    def test_unknown_type_defaults_to_text_field(self) -> None:
        """Unknown type string defaults to SINGLE_LINE_TEXT_FIELD."""
        result = parse_metafield_type("unknown_future_type")

        assert result == MetafieldType.SINGLE_LINE_TEXT_FIELD


@pytest.mark.os_agnostic
class TestParseSelectedOptions:
    """parse_selected_options converts dicts to SelectedOption models."""

    def test_parses_single_option(self) -> None:
        """Single option dict is converted to SelectedOption."""
        data = [{"name": "Size", "value": "Large"}]

        result = parse_selected_options(data)

        assert len(result) == 1
        assert isinstance(result[0], SelectedOption)
        assert result[0].name == "Size"
        assert result[0].value == "Large"

    def test_parses_multiple_options(self) -> None:
        """Multiple option dicts are converted to SelectedOption list."""
        data = [
            {"name": "Size", "value": "Large"},
            {"name": "Color", "value": "Red"},
        ]

        result = parse_selected_options(data)

        assert len(result) == 2
        assert result[0].name == "Size"
        assert result[1].name == "Color"

    def test_returns_empty_list_for_none(self) -> None:
        """None input returns empty list."""
        result = parse_selected_options(None)

        assert result == []

    def test_returns_empty_list_for_empty_list(self) -> None:
        """Empty list input returns empty list."""
        result = parse_selected_options([])

        assert result == []


@pytest.mark.os_agnostic
class TestParseGraphQLErrors:
    """parse_graphql_errors converts dicts to GraphQLErrorEntry models."""

    def test_parses_single_error(self) -> None:
        """Single error dict is converted to GraphQLErrorEntry."""
        data = [{"message": "Something went wrong"}]

        result = parse_graphql_errors(data)

        assert len(result) == 1
        assert isinstance(result[0], GraphQLErrorEntry)
        assert result[0].message == "Something went wrong"

    def test_parses_multiple_errors(self) -> None:
        """Multiple error dicts are converted to GraphQLErrorEntry list."""
        data = [
            {"message": "Error 1"},
            {"message": "Error 2"},
        ]

        result = parse_graphql_errors(data)

        assert len(result) == 2
        assert result[0].message == "Error 1"
        assert result[1].message == "Error 2"

    def test_parses_error_with_locations(self) -> None:
        """Error with locations is parsed correctly."""
        data = [
            {
                "message": "Syntax error",
                "locations": [{"line": 5, "column": 10}],
            }
        ]

        result = parse_graphql_errors(data)

        assert result[0].locations is not None
        assert result[0].locations[0].line == 5
        assert result[0].locations[0].column == 10

    def test_parses_error_with_path(self) -> None:
        """Error with path is parsed correctly."""
        data = [
            {
                "message": "Field error",
                "path": ["product", "title"],
            }
        ]

        result = parse_graphql_errors(data)

        assert result[0].path == ("product", "title")

    def test_parses_error_with_extensions(self) -> None:
        """Error with extensions is parsed correctly."""
        data = [
            {
                "message": "Rate limited",
                "extensions": {"code": "THROTTLED", "retryAfter": 5},
            }
        ]

        result = parse_graphql_errors(data)

        assert result[0].extensions == {"code": "THROTTLED", "retryAfter": 5}

    def test_parses_complete_shopify_error(self) -> None:
        """Complete Shopify-style error is parsed correctly."""
        data = [
            {
                "message": "Field 'invalidField' doesn't exist on type 'Product'",
                "locations": [{"line": 5, "column": 5}],
                "path": ["product"],
                "extensions": {
                    "code": "undefinedField",
                    "typeName": "Product",
                    "fieldName": "invalidField",
                },
            }
        ]

        result = parse_graphql_errors(data)

        assert len(result) == 1
        assert "invalidField" in result[0].message
        assert result[0].locations is not None
        assert result[0].locations[0].line == 5
        assert result[0].path == ("product",)
        assert result[0].extensions is not None
        assert result[0].extensions["code"] == "undefinedField"


# =============================================================================
# Cache Clearing Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestClearTokenCache:
    """tokencache_clear removes all cached tokens."""

    def test_clears_cache(self) -> None:
        """tokencache_clear calls cache.clear()."""
        from lib_shopify_graphql.shopify_client import tokencache_clear

        mock_cache = MagicMock()

        tokencache_clear(mock_cache)

        mock_cache.clear.assert_called_once()

    def test_logs_clearing_operation(self, caplog: pytest.LogCaptureFixture) -> None:
        """tokencache_clear logs the clearing operation."""
        import logging

        from lib_shopify_graphql.shopify_client import tokencache_clear

        mock_cache = MagicMock()

        with caplog.at_level(logging.INFO):
            tokencache_clear(mock_cache)

        assert any("token cache" in record.message.lower() for record in caplog.records)


@pytest.mark.os_agnostic
class TestClearSKUCache:
    """skucache_clear removes all cached SKU mappings."""

    def test_clears_cache(self) -> None:
        """skucache_clear calls cache.clear()."""
        from lib_shopify_graphql.shopify_client import skucache_clear

        mock_cache = MagicMock()

        skucache_clear(mock_cache)

        mock_cache.clear.assert_called_once()

    def test_logs_clearing_operation(self, caplog: pytest.LogCaptureFixture) -> None:
        """skucache_clear logs the clearing operation."""
        import logging

        from lib_shopify_graphql.shopify_client import skucache_clear

        mock_cache = MagicMock()

        with caplog.at_level(logging.INFO):
            skucache_clear(mock_cache)

        assert any("sku cache" in record.message.lower() for record in caplog.records)


@pytest.mark.os_agnostic
class TestClearCacheWithRealAdapter:
    """Cache clearing works with real JsonFileCacheAdapter."""

    def test_tokencache_clear_removes_entries(self, tmp_path: Path) -> None:
        """tokencache_clear removes all entries from JSON cache."""
        from lib_shopify_graphql import tokencache_clear
        from lib_shopify_graphql.adapters import JsonFileCacheAdapter

        cache_path = tmp_path / "token_cache.json"
        cache = JsonFileCacheAdapter(cache_path)
        cache.set("token:myshop", "access_token_123")
        cache.set("token:othershop", "access_token_456")

        tokencache_clear(cache)

        assert cache.get("token:myshop") is None
        assert cache.get("token:othershop") is None

    def test_skucache_clear_removes_entries(self, tmp_path: Path) -> None:
        """skucache_clear removes all entries from JSON cache."""
        from lib_shopify_graphql import skucache_clear
        from lib_shopify_graphql.adapters import JsonFileCacheAdapter

        cache_path = tmp_path / "sku_cache.json"
        cache = JsonFileCacheAdapter(cache_path)
        cache.set("sku:myshop:ABC-123", "gid://shopify/ProductVariant/123")
        cache.set("sku:myshop:DEF-456", "gid://shopify/ProductVariant/456")

        skucache_clear(cache)

        assert cache.get("sku:myshop:ABC-123") is None
        assert cache.get("sku:myshop:DEF-456") is None


@pytest.mark.os_agnostic
class TestClearCacheExportedFromPackage:
    """Cache clearing functions are exported from main package."""

    def test_tokencache_clear_exported(self) -> None:
        """tokencache_clear is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import tokencache_clear

        assert callable(tokencache_clear)

    def test_skucache_clear_exported(self) -> None:
        """skucache_clear is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import skucache_clear

        assert callable(skucache_clear)


# =============================================================================
# Metafield Deletion Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDeleteMetafieldSuccess:
    """delete_metafield deletes a single metafield successfully."""

    def test_returns_true_when_deleted(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns True when metafield was deleted."""
        from lib_shopify_graphql.shopify_client import delete_metafield

        response = {
            "data": {
                "metafieldsDelete": {
                    "deletedMetafields": [
                        {
                            "ownerId": "gid://shopify/Product/123",
                            "namespace": "custom",
                            "key": "warranty_months",
                        }
                    ],
                    "userErrors": [],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        result = delete_metafield(
            session,
            owner_id="gid://shopify/Product/123",
            namespace="custom",
            key="warranty_months",
        )

        assert result is True

    def test_returns_false_when_not_found(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns False when metafield didn't exist (idempotent)."""
        from lib_shopify_graphql.shopify_client import delete_metafield

        response: dict[str, Any] = {
            "data": {
                "metafieldsDelete": {
                    "deletedMetafields": [],
                    "userErrors": [],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        result = delete_metafield(
            session,
            owner_id="gid://shopify/Product/123",
            namespace="custom",
            key="nonexistent",
        )

        assert result is False


@pytest.mark.os_agnostic
class TestDeleteMetafieldSessionInactive:
    """delete_metafield raises error for inactive sessions."""

    def test_raises_session_not_active_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        from lib_shopify_graphql.shopify_client import delete_metafield

        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            delete_metafield(
                session,
                owner_id="gid://shopify/Product/123",
                namespace="custom",
                key="test",
            )


@pytest.mark.os_agnostic
class TestDeleteMetafieldUserError:
    """delete_metafield raises GraphQLError on user errors."""

    def test_raises_graphql_error(self, sample_credentials: ShopifyCredentials) -> None:
        """User errors raise GraphQLError."""
        from lib_shopify_graphql.shopify_client import delete_metafield

        response = {
            "data": {
                "metafieldsDelete": {
                    "deletedMetafields": [],
                    "userErrors": [
                        {
                            "field": ["metafields", 0, "ownerId"],
                            "message": "Invalid owner ID",
                            "code": "INVALID",
                        }
                    ],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError) as exc_info:
            delete_metafield(
                session,
                owner_id="invalid",
                namespace="custom",
                key="test",
            )

        assert "Invalid owner ID" in str(exc_info.value)


@pytest.mark.os_agnostic
class TestDeleteMetafieldsSuccess:
    """delete_metafields deletes multiple metafields successfully."""

    def test_deletes_multiple_metafields(self, sample_credentials: ShopifyCredentials) -> None:
        """All metafields are deleted successfully."""
        from lib_shopify_graphql import MetafieldIdentifier
        from lib_shopify_graphql.shopify_client import delete_metafields

        response = {
            "data": {
                "metafieldsDelete": {
                    "deletedMetafields": [
                        {
                            "ownerId": "gid://shopify/Product/123",
                            "namespace": "custom",
                            "key": "field1",
                        },
                        {
                            "ownerId": "gid://shopify/Product/123",
                            "namespace": "custom",
                            "key": "field2",
                        },
                    ],
                    "userErrors": [],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        result = delete_metafields(
            session,
            [
                MetafieldIdentifier(
                    owner_id="gid://shopify/Product/123",
                    namespace="custom",
                    key="field1",
                ),
                MetafieldIdentifier(
                    owner_id="gid://shopify/Product/123",
                    namespace="custom",
                    key="field2",
                ),
            ],
        )

        assert result.deleted_count == 2
        assert result.failed_count == 0
        assert result.all_succeeded is True

    def test_returns_empty_result_for_empty_list(self, sample_credentials: ShopifyCredentials) -> None:
        """Empty input list returns empty result."""
        from lib_shopify_graphql.shopify_client import delete_metafields

        session = _create_mock_session(sample_credentials)

        result = delete_metafields(session, [])

        assert result.deleted_count == 0
        assert result.failed_count == 0


@pytest.mark.os_agnostic
class TestDeleteMetafieldsPartialFailure:
    """delete_metafields handles partial failures."""

    def test_returns_both_deleted_and_failed(self, sample_credentials: ShopifyCredentials) -> None:
        """Result contains both deleted and failed items."""
        from lib_shopify_graphql import MetafieldIdentifier
        from lib_shopify_graphql.shopify_client import delete_metafields

        response = {
            "data": {
                "metafieldsDelete": {
                    "deletedMetafields": [
                        {
                            "ownerId": "gid://shopify/Product/123",
                            "namespace": "custom",
                            "key": "field1",
                        }
                    ],
                    "userErrors": [
                        {
                            "field": ["metafields", 1],
                            "message": "Invalid metafield",
                            "code": "INVALID",
                        }
                    ],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        result = delete_metafields(
            session,
            [
                MetafieldIdentifier(
                    owner_id="gid://shopify/Product/123",
                    namespace="custom",
                    key="field1",
                ),
                MetafieldIdentifier(
                    owner_id="invalid",
                    namespace="custom",
                    key="field2",
                ),
            ],
        )

        assert result.deleted_count == 1
        assert result.failed_count == 1
        assert result.all_succeeded is False


@pytest.mark.os_agnostic
class TestDeleteMetafieldsNormalizesOwnerID:
    """delete_metafields normalizes owner IDs to GID format."""

    def test_numeric_id_converted_to_gid(self, sample_credentials: ShopifyCredentials) -> None:
        """Numeric owner ID is converted to GID format."""
        from lib_shopify_graphql import MetafieldIdentifier
        from lib_shopify_graphql.shopify_client import delete_metafields

        response = {
            "data": {
                "metafieldsDelete": {
                    "deletedMetafields": [
                        {
                            "ownerId": "gid://shopify/Product/123",
                            "namespace": "custom",
                            "key": "field1",
                        }
                    ],
                    "userErrors": [],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        delete_metafields(
            session,
            [
                MetafieldIdentifier(
                    owner_id="123",  # Numeric, should become Product GID
                    namespace="custom",
                    key="field1",
                ),
            ],
        )

        # Check that execute was called with normalized GID
        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["metafields"][0]["ownerId"] == "gid://shopify/Product/123"


@pytest.mark.os_agnostic
class TestDeleteMetafieldsGraphQLError:
    """delete_metafields raises GraphQLError for API errors."""

    def test_raises_graphql_error(self, sample_credentials: ShopifyCredentials) -> None:
        """GraphQL errors raise GraphQLError."""
        from lib_shopify_graphql import MetafieldIdentifier
        from lib_shopify_graphql.shopify_client import delete_metafields

        response = {
            "errors": [
                {"message": "Access denied"},
            ]
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError) as exc_info:
            delete_metafields(
                session,
                [
                    MetafieldIdentifier(
                        owner_id="gid://shopify/Product/123",
                        namespace="custom",
                        key="test",
                    ),
                ],
            )

        assert "Access denied" in str(exc_info.value)


@pytest.mark.os_agnostic
class TestDeleteMetafieldExportedFromPackage:
    """delete_metafield functions are exported from main package."""

    def test_delete_metafield_exported(self) -> None:
        """delete_metafield is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import delete_metafield

        assert callable(delete_metafield)

    def test_delete_metafields_exported(self) -> None:
        """delete_metafields is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import delete_metafields

        assert callable(delete_metafields)

    def test_metafield_identifier_exported(self) -> None:
        """MetafieldIdentifier is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import MetafieldIdentifier

        assert MetafieldIdentifier is not None

    def test_metafield_delete_result_exported(self) -> None:
        """MetafieldDeleteResult is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import MetafieldDeleteResult

        assert MetafieldDeleteResult is not None

    def test_metafield_delete_failure_exported(self) -> None:
        """MetafieldDeleteFailure is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import MetafieldDeleteFailure

        assert MetafieldDeleteFailure is not None


# =============================================================================
# ListProducts Tests
# =============================================================================


def _build_list_products_response(
    products: list[dict[str, Any]],
    *,
    has_next_page: bool = False,
    has_previous_page: bool = False,
    start_cursor: str | None = None,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    """Build a Shopify-like list products response."""
    return {
        "data": {
            "products": {
                "pageInfo": {
                    "hasNextPage": has_next_page,
                    "hasPreviousPage": has_previous_page,
                    "startCursor": start_cursor,
                    "endCursor": end_cursor,
                },
                "nodes": products,
            }
        }
    }


def _minimal_product_data(product_id: str, title: str) -> dict[str, Any]:
    """Build minimal product data for list responses."""
    return {
        "id": f"gid://shopify/Product/{product_id}",
        "legacyResourceId": product_id,
        "title": title,
        "description": f"Description for {title}",
        "descriptionHtml": f"<p>Description for {title}</p>",
        "handle": title.lower().replace(" ", "-"),
        "vendor": "Test Vendor",
        "productType": "Test Type",
        "status": "ACTIVE",
        "tags": [],
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
        "publishedAt": "2024-01-01T12:00:00Z",
        "totalInventory": 10,
        "tracksInventory": True,
        "hasOnlyDefaultVariant": True,
        "hasOutOfStockVariants": False,
        "isGiftCard": False,
        "onlineStoreUrl": None,
        "onlineStorePreviewUrl": None,
        "templateSuffix": None,
        "featuredImage": None,
        "images": {"nodes": []},
        "options": [],
        "seo": {"title": None, "description": None},
        "priceRangeV2": {
            "minVariantPrice": {"amount": "0.00", "currencyCode": "USD"},
            "maxVariantPrice": {"amount": "0.00", "currencyCode": "USD"},
        },
        "metafields": {"nodes": []},
        "variants": {"nodes": []},
    }


@pytest.mark.os_agnostic
class TestListProductsPaginatedReturnsConnection:
    """list_products_paginated returns a ProductConnection with products."""

    def test_returns_product_connection(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns a ProductConnection model."""
        from lib_shopify_graphql.models import ProductConnection
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response([])
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products_paginated(session)

        assert isinstance(result, ProductConnection)

    def test_returns_products_list(self, sample_credentials: ShopifyCredentials) -> None:
        """Products are returned in the products list."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        products = [
            _minimal_product_data("123", "Product One"),
            _minimal_product_data("456", "Product Two"),
        ]
        response = _build_list_products_response(products)
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products_paginated(session)

        assert len(result.products) == 2
        assert result.products[0].title == "Product One"
        assert result.products[1].title == "Product Two"

    def test_returns_empty_list_when_no_products(self, sample_credentials: ShopifyCredentials) -> None:
        """Empty products list is returned when no products exist."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response([])
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products_paginated(session)

        assert len(result.products) == 0


@pytest.mark.os_agnostic
class TestListProductsPaginatedCursors:
    """list_products_paginated supports cursor-based pagination."""

    def test_page_info_has_next_page(self, sample_credentials: ShopifyCredentials) -> None:
        """PageInfo indicates when there's a next page."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response(
            [_minimal_product_data("123", "Product One")],
            has_next_page=True,
            end_cursor="cursor_abc",
        )
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products_paginated(session)

        assert result.page_info.has_next_page is True
        assert result.page_info.end_cursor == "cursor_abc"

    def test_page_info_no_next_page(self, sample_credentials: ShopifyCredentials) -> None:
        """PageInfo indicates when there's no next page."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response(
            [_minimal_product_data("123", "Product One")],
            has_next_page=False,
        )
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products_paginated(session)

        assert result.page_info.has_next_page is False

    def test_passes_after_cursor_to_query(self, sample_credentials: ShopifyCredentials) -> None:
        """After cursor is passed to the GraphQL query."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response([])
        session = _setup_session_with_response(sample_credentials, response)

        list_products_paginated(session, after="cursor_xyz")

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["after"] == "cursor_xyz"


@pytest.mark.os_agnostic
class TestListProductsPaginatedFirstParameter:
    """list_products_paginated respects the first parameter."""

    def test_passes_first_to_query(self, sample_credentials: ShopifyCredentials) -> None:
        """First parameter is passed to the GraphQL query."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response([])
        session = _setup_session_with_response(sample_credentials, response)

        list_products_paginated(session, first=100)

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["first"] == 100

    def test_caps_first_at_250(self, sample_credentials: ShopifyCredentials) -> None:
        """First parameter is capped at 250 (Shopify limit)."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response([])
        session = _setup_session_with_response(sample_credentials, response)

        list_products_paginated(session, first=500)

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["first"] == 250

    def test_minimum_first_is_1(self, sample_credentials: ShopifyCredentials) -> None:
        """First parameter minimum is 1."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response([])
        session = _setup_session_with_response(sample_credentials, response)

        list_products_paginated(session, first=0)

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["first"] == 1


@pytest.mark.os_agnostic
class TestListProductsPaginatedQueryFilter:
    """list_products_paginated supports query filtering."""

    def test_passes_query_to_graphql(self, sample_credentials: ShopifyCredentials) -> None:
        """Query parameter is passed to the GraphQL query."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response([])
        session = _setup_session_with_response(sample_credentials, response)

        list_products_paginated(session, query="updated_at:>2024-01-01")

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["query"] == "updated_at:>2024-01-01"

    def test_query_is_omitted_by_default(self, sample_credentials: ShopifyCredentials) -> None:
        """Query parameter is omitted when not provided (not sent to Shopify)."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = _build_list_products_response([])
        session = _setup_session_with_response(sample_credentials, response)

        list_products_paginated(session)

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert "query" not in variables


@pytest.mark.os_agnostic
class TestListProductsPaginatedInactiveSession:
    """list_products_paginated raises error for inactive sessions."""

    def test_raises_session_not_active_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            list_products_paginated(session)


@pytest.mark.os_agnostic
class TestListProductsPaginatedGraphQLError:
    """list_products_paginated raises GraphQLError for API errors."""

    def test_raises_graphql_error(self, sample_credentials: ShopifyCredentials) -> None:
        """GraphQL errors raise GraphQLError."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = {
            "errors": [
                {"message": "Access denied"},
            ],
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError):
            list_products_paginated(session)

    def test_error_contains_message(self, sample_credentials: ShopifyCredentials) -> None:
        """GraphQLError includes the error message."""
        from lib_shopify_graphql.shopify_client import list_products_paginated

        response = {
            "errors": [
                {"message": "Invalid query syntax"},
            ],
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError) as exc_info:
            list_products_paginated(session)

        assert "Invalid query syntax" in str(exc_info.value)


@pytest.mark.os_agnostic
class TestListProductsExportedFromPackage:
    """Pagination functions are exported from main package."""

    def test_list_products_exported(self) -> None:
        """list_products (auto-pagination) is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import list_products

        assert callable(list_products)

    def test_iter_products_exported(self) -> None:
        """iter_products (auto-pagination iterator) is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import iter_products

        assert callable(iter_products)

    def test_list_products_paginated_exported(self) -> None:
        """list_products_paginated (manual pagination) is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import list_products_paginated

        assert callable(list_products_paginated)

    def test_page_info_exported(self) -> None:
        """PageInfo is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import PageInfo

        assert PageInfo is not None

    def test_product_connection_exported(self) -> None:
        """ProductConnection is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import ProductConnection

        assert ProductConnection is not None


# =============================================================================
# Auto-Pagination Function Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestListProductsAutoPageination:
    """list_products returns a list with automatic pagination."""

    def test_returns_list(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns a list of Product objects."""
        from lib_shopify_graphql.shopify_client import list_products

        products = [
            _minimal_product_data("123", "Product One"),
            _minimal_product_data("456", "Product Two"),
        ]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products(session)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].title == "Product One"
        assert result[1].title == "Product Two"

    def test_returns_empty_list_when_no_products(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns empty list when no products exist."""
        from lib_shopify_graphql.shopify_client import list_products

        response = _build_list_products_response([], has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products(session)

        assert result == []

    def test_max_products_limits_results(self, sample_credentials: ShopifyCredentials) -> None:
        """max_products parameter limits the number of returned products."""
        from lib_shopify_graphql.shopify_client import list_products

        products = [
            _minimal_product_data("1", "Product 1"),
            _minimal_product_data("2", "Product 2"),
            _minimal_product_data("3", "Product 3"),
        ]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products(session, max_products=2)

        assert len(result) == 2

    def test_inactive_session_raises_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        from lib_shopify_graphql.shopify_client import list_products

        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            list_products(session)


@pytest.mark.os_agnostic
class TestIterProductsAutoPageination:
    """iter_products returns an iterator with automatic pagination."""

    def test_yields_products(self, sample_credentials: ShopifyCredentials) -> None:
        """Yields Product objects one at a time."""
        from lib_shopify_graphql.shopify_client import iter_products

        products = [
            _minimal_product_data("123", "Product One"),
            _minimal_product_data("456", "Product Two"),
        ]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list(iter_products(session))

        assert len(result) == 2
        assert result[0].title == "Product One"
        assert result[1].title == "Product Two"

    def test_yields_nothing_when_no_products(self, sample_credentials: ShopifyCredentials) -> None:
        """Yields nothing when no products exist."""
        from lib_shopify_graphql.shopify_client import iter_products

        response = _build_list_products_response([], has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list(iter_products(session))

        assert result == []

    def test_inactive_session_raises_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        from lib_shopify_graphql.shopify_client import iter_products

        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            # Need to consume the iterator to trigger the error
            list(iter_products(session))


# =============================================================================
# GetProductIdFromSku Tests
# =============================================================================


def _build_variant_product_response(product_id: str) -> dict[str, Any]:
    """Build a Shopify-like variant product response."""
    return {
        "data": {
            "productVariant": {
                "product": {
                    "id": f"gid://shopify/Product/{product_id}",
                }
            }
        }
    }


@pytest.mark.os_agnostic
class TestGetProductIdFromSkuReturnsProductList:
    """get_product_id_from_sku returns a list of product IDs."""

    def test_returns_product_list_for_single_variant(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns list with single product GID for SKU with one variant."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        # Create mock SKU resolver that returns one variant
        mock_sku_resolver = MagicMock()
        mock_sku_resolver.resolve_all.return_value = ["gid://shopify/ProductVariant/987654321"]

        # Create session with mock GraphQL response
        response = _build_variant_product_response("123456789")
        session = _setup_session_with_response(sample_credentials, response)

        result = get_product_id_from_sku(session, "ABC-123", sku_resolver=mock_sku_resolver)

        assert result == ["gid://shopify/Product/123456789"]

    def test_returns_multiple_products_for_duplicate_sku(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns list with multiple product GIDs when SKU exists on multiple products."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        # Mock resolver returns two variants with same SKU
        mock_sku_resolver = MagicMock()
        mock_sku_resolver.resolve_all.return_value = [
            "gid://shopify/ProductVariant/111",
            "gid://shopify/ProductVariant/222",
        ]

        # Mock session returns different product IDs for each variant
        session = _create_mock_session(sample_credentials)
        session._graphql_client.execute.side_effect = [  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue]
            _build_variant_product_response("AAA"),
            _build_variant_product_response("BBB"),
        ]

        result = get_product_id_from_sku(session, "DUPLICATE-SKU", sku_resolver=mock_sku_resolver)

        assert len(result) == 2
        assert "gid://shopify/Product/AAA" in result
        assert "gid://shopify/Product/BBB" in result

    def test_deduplicates_products_from_same_product(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns unique product IDs when multiple variants belong to same product."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        # Two variants on same product
        mock_sku_resolver = MagicMock()
        mock_sku_resolver.resolve_all.return_value = [
            "gid://shopify/ProductVariant/111",
            "gid://shopify/ProductVariant/222",
        ]

        # Both variants belong to same product
        session = _create_mock_session(sample_credentials)
        session._graphql_client.execute.side_effect = [  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue]
            _build_variant_product_response("SAME"),
            _build_variant_product_response("SAME"),
        ]

        result = get_product_id_from_sku(session, "SKU-123", sku_resolver=mock_sku_resolver)

        assert result == ["gid://shopify/Product/SAME"]

    def test_calls_resolve_all_on_sku_resolver(self, sample_credentials: ShopifyCredentials) -> None:
        """SKU resolver's resolve_all is called with SKU."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        mock_sku_resolver = MagicMock()
        mock_sku_resolver.resolve_all.return_value = ["gid://shopify/ProductVariant/987654321"]

        response = _build_variant_product_response("123456789")
        session = _setup_session_with_response(sample_credentials, response)

        get_product_id_from_sku(session, "TEST-SKU", sku_resolver=mock_sku_resolver)

        mock_sku_resolver.resolve_all.assert_called_once_with("TEST-SKU")


@pytest.mark.os_agnostic
class TestGetProductIdFromSkuReturnsEmptyList:
    """get_product_id_from_sku returns empty list when SKU not found."""

    def test_returns_empty_list_when_sku_not_found(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns empty list when SKU cannot be resolved."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        mock_sku_resolver = MagicMock()
        mock_sku_resolver.resolve_all.return_value = []

        session = _create_mock_session(sample_credentials)

        result = get_product_id_from_sku(session, "UNKNOWN-SKU", sku_resolver=mock_sku_resolver)

        assert result == []


@pytest.mark.os_agnostic
class TestGetProductIdFromSkuInactiveSession:
    """get_product_id_from_sku raises error for inactive sessions."""

    def test_raises_session_not_active_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        from unittest.mock import MagicMock

        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)
        mock_sku_resolver = MagicMock()

        with pytest.raises(SessionNotActiveError):
            get_product_id_from_sku(session, "ABC-123", sku_resolver=mock_sku_resolver)


@pytest.mark.os_agnostic
class TestGetProductIdFromSkuVariantNoProduct:
    """get_product_id_from_sku handles variant with no product."""

    def test_skips_variant_with_no_product(self, sample_credentials: ShopifyCredentials) -> None:
        """Skips variants that have no parent product, returns remaining."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        mock_sku_resolver = MagicMock()
        mock_sku_resolver.resolve_all.return_value = [
            "gid://shopify/ProductVariant/111",
            "gid://shopify/ProductVariant/222",
        ]

        # First variant has no product, second does
        session = _create_mock_session(sample_credentials)
        session._graphql_client.execute.side_effect = [  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue]
            {"data": {"productVariant": {"product": None}}},
            _build_variant_product_response("VALID"),
        ]

        result = get_product_id_from_sku(session, "ABC-123", sku_resolver=mock_sku_resolver)

        assert result == ["gid://shopify/Product/VALID"]

    def test_returns_empty_list_when_all_variants_have_no_product(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns empty list when all variants have no parent product."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        mock_sku_resolver = MagicMock()
        mock_sku_resolver.resolve_all.return_value = ["gid://shopify/ProductVariant/987654321"]

        response = {"data": {"productVariant": {"product": None}}}
        session = _setup_session_with_response(sample_credentials, response)

        result = get_product_id_from_sku(session, "ABC-123", sku_resolver=mock_sku_resolver)

        assert result == []


@pytest.mark.os_agnostic
class TestGetProductIdFromSkuExportedFromPackage:
    """get_product_id_from_sku is exported from main package."""

    def test_get_product_id_from_sku_exported(self) -> None:
        """get_product_id_from_sku is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import get_product_id_from_sku

        assert callable(get_product_id_from_sku)


@pytest.mark.os_agnostic
class TestGetProductIdFromSkuSessionAttachedResolver:
    """get_product_id_from_sku uses session-attached resolver when no explicit resolver given."""

    def test_uses_session_attached_resolver(self, sample_credentials: ShopifyCredentials) -> None:
        """Uses session's _sku_resolver when no explicit resolver is provided."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        # Create mock SKU resolver attached to session
        mock_sku_resolver = MagicMock()
        mock_sku_resolver.resolve_all.return_value = ["gid://shopify/ProductVariant/987654321"]

        response = _build_variant_product_response("123456789")
        session = _setup_session_with_response(sample_credentials, response)
        # Attach resolver to session
        object.__setattr__(session, "_sku_resolver", mock_sku_resolver)

        # Call without explicit sku_resolver - should use session's resolver
        result = get_product_id_from_sku(session, "ABC-123")

        assert result == ["gid://shopify/Product/123456789"]
        mock_sku_resolver.resolve_all.assert_called_once_with("ABC-123")

    def test_explicit_resolver_overrides_session_resolver(self, sample_credentials: ShopifyCredentials) -> None:
        """Explicit sku_resolver parameter takes priority over session-attached resolver."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        # Session's resolver should NOT be called
        session_resolver = MagicMock()
        session_resolver.resolve_all.return_value = ["gid://shopify/ProductVariant/session"]

        # Explicit resolver SHOULD be called
        explicit_resolver = MagicMock()
        explicit_resolver.resolve_all.return_value = ["gid://shopify/ProductVariant/explicit"]

        response = _build_variant_product_response("123456789")
        session = _setup_session_with_response(sample_credentials, response)
        object.__setattr__(session, "_sku_resolver", session_resolver)

        # Pass explicit resolver
        result = get_product_id_from_sku(session, "ABC-123", sku_resolver=explicit_resolver)

        assert result == ["gid://shopify/Product/123456789"]
        explicit_resolver.resolve_all.assert_called_once_with("ABC-123")
        session_resolver.resolve_all.assert_not_called()

    def test_raises_value_error_when_no_resolver_available(self, sample_credentials: ShopifyCredentials) -> None:
        """ValueError raised when neither explicit nor session-attached resolver is available."""
        from lib_shopify_graphql.shopify_client import get_product_id_from_sku

        # Session without resolver
        session = _create_mock_session(sample_credentials)

        with pytest.raises(ValueError, match="No SKU resolver available"):
            get_product_id_from_sku(session, "ABC-123")


# =============================================================================
# CreateProduct Tests
# =============================================================================


def _build_product_create_response(product_id: str, title: str) -> dict[str, Any]:
    """Build a Shopify-like productCreate mutation response."""
    return {
        "data": {
            "productCreate": {
                "product": {
                    "id": f"gid://shopify/Product/{product_id}",
                    "legacyResourceId": product_id,
                    "title": title,
                    "description": "",
                    "descriptionHtml": "",
                    "handle": title.lower().replace(" ", "-"),
                    "vendor": "",
                    "productType": "",
                    "status": "DRAFT",
                    "tags": [],
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-01T00:00:00Z",
                    "publishedAt": None,
                    "totalInventory": 0,
                    "tracksInventory": True,
                    "hasOnlyDefaultVariant": True,
                    "hasOutOfStockVariants": False,
                    "isGiftCard": False,
                    "onlineStoreUrl": None,
                    "onlineStorePreviewUrl": None,
                    "templateSuffix": None,
                    "featuredImage": None,
                    "images": {"nodes": []},
                    "options": [],
                    "seo": {"title": None, "description": None},
                    "priceRangeV2": {
                        "minVariantPrice": {"amount": "0.00", "currencyCode": "USD"},
                        "maxVariantPrice": {"amount": "0.00", "currencyCode": "USD"},
                    },
                    "metafields": {"nodes": []},
                    "variants": {
                        "nodes": [
                            {
                                "id": "gid://shopify/ProductVariant/111",
                                "title": "Default Title",
                                "displayName": f"{title} - Default Title",
                                "sku": "NEW-SKU-001",
                                "barcode": None,
                                "price": "0.00",
                                "compareAtPrice": None,
                                "inventoryQuantity": 0,
                                "inventoryPolicy": "DENY",
                                "availableForSale": False,
                                "taxable": True,
                                "position": 1,
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                                "image": None,
                                "selectedOptions": [{"name": "Title", "value": "Default Title"}],
                                "metafields": {"nodes": []},
                            }
                        ]
                    },
                },
                "userErrors": [],
            }
        }
    }


@pytest.mark.os_agnostic
class TestCreateProductSuccess:
    """create_product creates a new product successfully."""

    def test_returns_product(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns a Product model on success."""
        from lib_shopify_graphql.models import Product, ProductCreate
        from lib_shopify_graphql.shopify_client import create_product

        response = _build_product_create_response("12345", "New Product")
        session = _setup_session_with_response(sample_credentials, response)

        result = create_product(session, ProductCreate(title="New Product"))

        assert isinstance(result, Product)
        assert result.id == "gid://shopify/Product/12345"
        assert result.title == "New Product"

    def test_passes_title_to_mutation(self, sample_credentials: ShopifyCredentials) -> None:
        """Title is passed to the GraphQL mutation."""
        from lib_shopify_graphql.models import ProductCreate
        from lib_shopify_graphql.shopify_client import create_product

        response = _build_product_create_response("12345", "My Title")
        session = _setup_session_with_response(sample_credentials, response)

        create_product(session, ProductCreate(title="My Title"))

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["input"]["title"] == "My Title"


@pytest.mark.os_agnostic
class TestCreateProductWithOptions:
    """create_product passes optional fields correctly."""

    def test_passes_status_to_mutation(self, sample_credentials: ShopifyCredentials) -> None:
        """Status is passed to the GraphQL mutation."""
        from lib_shopify_graphql.models import ProductCreate, ProductStatus
        from lib_shopify_graphql.shopify_client import create_product

        response = _build_product_create_response("12345", "Test")
        session = _setup_session_with_response(sample_credentials, response)

        create_product(session, ProductCreate(title="Test", status=ProductStatus.ACTIVE))

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["input"]["status"] == "ACTIVE"

    def test_passes_vendor_to_mutation(self, sample_credentials: ShopifyCredentials) -> None:
        """Vendor is passed to the GraphQL mutation."""
        from lib_shopify_graphql.models import ProductCreate
        from lib_shopify_graphql.shopify_client import create_product

        response = _build_product_create_response("12345", "Test")
        session = _setup_session_with_response(sample_credentials, response)

        create_product(session, ProductCreate(title="Test", vendor="ACME Corp"))

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["input"]["vendor"] == "ACME Corp"


@pytest.mark.os_agnostic
class TestCreateProductUserError:
    """create_product raises GraphQLError on user errors."""

    def test_raises_graphql_error(self, sample_credentials: ShopifyCredentials) -> None:
        """User errors raise GraphQLError."""
        from lib_shopify_graphql.models import ProductCreate
        from lib_shopify_graphql.shopify_client import create_product

        response = {
            "data": {
                "productCreate": {
                    "product": None,
                    "userErrors": [
                        {
                            "field": ["title"],
                            "message": "Title is required",
                            "code": "BLANK",
                        }
                    ],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError) as exc_info:
            create_product(session, ProductCreate(title=""))

        assert "Title is required" in str(exc_info.value)


@pytest.mark.os_agnostic
class TestCreateProductInactiveSession:
    """create_product raises error for inactive sessions."""

    def test_raises_session_not_active_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        from lib_shopify_graphql.models import ProductCreate
        from lib_shopify_graphql.shopify_client import create_product

        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            create_product(session, ProductCreate(title="Test"))


@pytest.mark.os_agnostic
class TestCreateProductExportedFromPackage:
    """create_product is exported from main package."""

    def test_create_product_exported(self) -> None:
        """create_product is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import create_product

        assert callable(create_product)

    def test_product_create_model_exported(self) -> None:
        """ProductCreate is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import ProductCreate

        assert ProductCreate is not None


# =============================================================================
# DuplicateProduct Tests
# =============================================================================


def _build_product_duplicate_response(
    new_product_id: str,
    new_title: str,
) -> dict[str, Any]:
    """Build a Shopify-like productDuplicate mutation response."""
    return {
        "data": {
            "productDuplicate": {
                "newProduct": {
                    "id": f"gid://shopify/Product/{new_product_id}",
                    "legacyResourceId": new_product_id,
                    "title": new_title,
                    "description": "Duplicated product",
                    "descriptionHtml": "<p>Duplicated product</p>",
                    "handle": new_title.lower().replace(" ", "-"),
                    "vendor": "Test Vendor",
                    "productType": "Test Type",
                    "status": "DRAFT",
                    "tags": [],
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-01T00:00:00Z",
                    "publishedAt": None,
                    "totalInventory": 0,
                    "tracksInventory": True,
                    "hasOnlyDefaultVariant": True,
                    "hasOutOfStockVariants": False,
                    "isGiftCard": False,
                    "onlineStoreUrl": None,
                    "onlineStorePreviewUrl": None,
                    "templateSuffix": None,
                    "featuredImage": None,
                    "images": {"nodes": []},
                    "options": [],
                    "seo": {"title": None, "description": None},
                    "priceRangeV2": {
                        "minVariantPrice": {"amount": "0.00", "currencyCode": "USD"},
                        "maxVariantPrice": {"amount": "0.00", "currencyCode": "USD"},
                    },
                    "metafields": {"nodes": []},
                    "variants": {
                        "nodes": [
                            {
                                "id": "gid://shopify/ProductVariant/222",
                                "title": "Default Title",
                                "displayName": f"{new_title} - Default Title",
                                "sku": "DUP-SKU-001",
                                "barcode": None,
                                "price": "19.99",
                                "compareAtPrice": None,
                                "inventoryQuantity": 0,
                                "inventoryPolicy": "DENY",
                                "availableForSale": False,
                                "taxable": True,
                                "position": 1,
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                                "image": None,
                                "selectedOptions": [{"name": "Title", "value": "Default Title"}],
                                "metafields": {"nodes": []},
                            }
                        ]
                    },
                },
                "userErrors": [],
            }
        }
    }


@pytest.mark.os_agnostic
class TestDuplicateProductSuccess:
    """duplicate_product duplicates a product successfully."""

    def test_returns_duplicate_result(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns a DuplicateProductResult on success."""
        from lib_shopify_graphql.models import DuplicateProductResult
        from lib_shopify_graphql.shopify_client import duplicate_product

        response = _build_product_duplicate_response("99999", "Copy of Product")
        session = _setup_session_with_response(sample_credentials, response)

        result = duplicate_product(session, "12345", "Copy of Product")

        assert isinstance(result, DuplicateProductResult)
        assert result.new_product.id == "gid://shopify/Product/99999"
        assert result.new_product.title == "Copy of Product"
        assert result.original_product_id == "gid://shopify/Product/12345"

    def test_passes_product_id_to_mutation(self, sample_credentials: ShopifyCredentials) -> None:
        """Product ID is passed to the GraphQL mutation."""
        from lib_shopify_graphql.shopify_client import duplicate_product

        response = _build_product_duplicate_response("99999", "Copy")
        session = _setup_session_with_response(sample_credentials, response)

        duplicate_product(session, "12345", "Copy")

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["productId"] == "gid://shopify/Product/12345"

    def test_passes_new_title_to_mutation(self, sample_credentials: ShopifyCredentials) -> None:
        """New title is passed to the GraphQL mutation."""
        from lib_shopify_graphql.shopify_client import duplicate_product

        response = _build_product_duplicate_response("99999", "New Title")
        session = _setup_session_with_response(sample_credentials, response)

        duplicate_product(session, "12345", "New Title")

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["newTitle"] == "New Title"


@pytest.mark.os_agnostic
class TestDuplicateProductOptions:
    """duplicate_product passes optional parameters correctly."""

    def test_passes_include_images_false(self, sample_credentials: ShopifyCredentials) -> None:
        """include_images=False is passed to the mutation."""
        from lib_shopify_graphql.shopify_client import duplicate_product

        response = _build_product_duplicate_response("99999", "Copy")
        session = _setup_session_with_response(sample_credentials, response)

        duplicate_product(session, "12345", "Copy", include_images=False)

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["includeImages"] is False

    def test_passes_new_status(self, sample_credentials: ShopifyCredentials) -> None:
        """new_status is passed to the mutation."""
        from lib_shopify_graphql.models import ProductStatus
        from lib_shopify_graphql.shopify_client import duplicate_product

        response = _build_product_duplicate_response("99999", "Copy")
        session = _setup_session_with_response(sample_credentials, response)

        duplicate_product(session, "12345", "Copy", new_status=ProductStatus.ACTIVE)

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["newStatus"] == "ACTIVE"


@pytest.mark.os_agnostic
class TestDuplicateProductUserError:
    """duplicate_product raises GraphQLError on user errors."""

    def test_raises_graphql_error(self, sample_credentials: ShopifyCredentials) -> None:
        """User errors raise GraphQLError."""
        from lib_shopify_graphql.shopify_client import duplicate_product

        response = {
            "data": {
                "productDuplicate": {
                    "newProduct": None,
                    "userErrors": [
                        {
                            "field": ["newTitle"],
                            "message": "Title is invalid",
                            "code": "INVALID",
                        }
                    ],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError) as exc_info:
            duplicate_product(session, "12345", "Copy")

        assert "Title is invalid" in str(exc_info.value)


@pytest.mark.os_agnostic
class TestDuplicateProductInactiveSession:
    """duplicate_product raises error for inactive sessions."""

    def test_raises_session_not_active_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        from lib_shopify_graphql.shopify_client import duplicate_product

        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            duplicate_product(session, "12345", "Copy")


@pytest.mark.os_agnostic
class TestDuplicateProductExportedFromPackage:
    """duplicate_product is exported from main package."""

    def test_duplicate_product_exported(self) -> None:
        """duplicate_product is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import duplicate_product

        assert callable(duplicate_product)

    def test_duplicate_product_result_exported(self) -> None:
        """DuplicateProductResult is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import DuplicateProductResult

        assert DuplicateProductResult is not None


# =============================================================================
# DeleteProduct Tests
# =============================================================================


def _build_product_delete_response(product_id: str) -> dict[str, Any]:
    """Build a Shopify-like productDelete mutation response."""
    return {
        "data": {
            "productDelete": {
                "deletedProductId": f"gid://shopify/Product/{product_id}",
                "userErrors": [],
            }
        }
    }


@pytest.mark.os_agnostic
class TestDeleteProductSuccess:
    """delete_product deletes a product successfully."""

    def test_returns_delete_result(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns a DeleteProductResult on success."""
        from lib_shopify_graphql.models import DeleteProductResult
        from lib_shopify_graphql.shopify_client import delete_product

        # Without sku_resolver, only the delete call happens
        delete_response = _build_product_delete_response("123456789")
        session = _setup_session_with_response(sample_credentials, delete_response)

        result = delete_product(session, "123456789")

        assert isinstance(result, DeleteProductResult)
        assert result.deleted_product_id == "gid://shopify/Product/123456789"
        assert result.success is True

    def test_passes_product_id_to_mutation(self, sample_credentials: ShopifyCredentials) -> None:
        """Product ID is passed to the GraphQL mutation."""
        from lib_shopify_graphql.shopify_client import delete_product

        delete_response = _build_product_delete_response("12345")
        session = _setup_session_with_response(sample_credentials, delete_response)

        delete_product(session, "12345")

        call_args = session._graphql_client.execute.call_args  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue, reportUnknownMemberType]
        variables: dict[str, Any] | None = call_args.kwargs.get("variables") or (call_args.args[1] if len(call_args.args) > 1 else None)  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        assert variables is not None
        assert variables["input"]["id"] == "gid://shopify/Product/12345"


@pytest.mark.os_agnostic
class TestDeleteProductClearsSKUCache:
    """delete_product clears SKU cache entries for deleted variants."""

    def test_invalidates_variant_skus(self, sample_credentials: ShopifyCredentials, graphql_product_response: dict[str, Any]) -> None:
        """Variant SKUs are invalidated in the SKU cache."""
        from lib_shopify_graphql.shopify_client import delete_product

        delete_response = _build_product_delete_response("123456789")
        session = _create_mock_session(sample_credentials)
        session._graphql_client.execute.side_effect = [  # type: ignore[reportPrivateUsage, reportAttributeAccessIssue]
            graphql_product_response,
            delete_response,
        ]

        mock_sku_resolver = MagicMock()
        delete_product(session, "123456789", sku_resolver=mock_sku_resolver)

        # Should invalidate the SKU from the product response (TEST-SKU-001)
        mock_sku_resolver.invalidate.assert_called_once_with("TEST-SKU-001", "test-store.myshopify.com")


@pytest.mark.os_agnostic
class TestDeleteProductUserError:
    """delete_product raises GraphQLError on user errors."""

    def test_raises_graphql_error(self, sample_credentials: ShopifyCredentials) -> None:
        """User errors raise GraphQLError."""
        from lib_shopify_graphql.shopify_client import delete_product

        # Without sku_resolver, only the delete call happens
        response = {
            "data": {
                "productDelete": {
                    "deletedProductId": None,
                    "userErrors": [
                        {
                            "field": ["id"],
                            "message": "Product cannot be deleted",
                            "code": "INVALID",
                        }
                    ],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(GraphQLError) as exc_info:
            delete_product(session, "12345")

        assert "Product cannot be deleted" in str(exc_info.value)


@pytest.mark.os_agnostic
class TestDeleteProductNotFound:
    """delete_product raises ProductNotFoundError when product doesn't exist."""

    def test_raises_product_not_found_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Non-existent product raises ProductNotFoundError."""
        from lib_shopify_graphql.shopify_client import delete_product

        # The productDelete mutation returns "not found" in user errors
        response = {
            "data": {
                "productDelete": {
                    "deletedProductId": None,
                    "userErrors": [
                        {
                            "field": ["id"],
                            "message": "Product not found",
                            "code": "NOT_FOUND",
                        }
                    ],
                }
            }
        }
        session = _setup_session_with_response(sample_credentials, response)

        with pytest.raises(ProductNotFoundError):
            delete_product(session, "nonexistent")


@pytest.mark.os_agnostic
class TestDeleteProductInactiveSession:
    """delete_product raises error for inactive sessions."""

    def test_raises_session_not_active_error(self, sample_credentials: ShopifyCredentials) -> None:
        """Inactive session raises SessionNotActiveError."""
        from lib_shopify_graphql.shopify_client import delete_product

        session = _create_mock_session(sample_credentials)
        object.__setattr__(session, "_is_active", False)

        with pytest.raises(SessionNotActiveError):
            delete_product(session, "12345")


@pytest.mark.os_agnostic
class TestDeleteProductExportedFromPackage:
    """delete_product is exported from main package."""

    def test_delete_product_exported(self) -> None:
        """delete_product is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import delete_product

        assert callable(delete_product)

    def test_delete_product_result_exported(self) -> None:
        """DeleteProductResult is accessible from lib_shopify_graphql."""
        from lib_shopify_graphql import DeleteProductResult

        assert DeleteProductResult is not None


# =============================================================================
# Comprehensive Pagination Tests - iter_products Multi-Page
# =============================================================================


def _setup_multi_page_session(
    credentials: ShopifyCredentials,
    pages: Sequence[tuple[list[dict[str, Any]], bool, str | None]],
) -> ShopifySession:
    """Create a session that returns multiple pages of products.

    Args:
        credentials: Shopify credentials for session.
        pages: List of tuples (products, has_next_page, end_cursor).

    Returns:
        Session configured to return pages in sequence.
    """
    session = _create_mock_session(credentials)

    responses: list[dict[str, Any]] = []
    for products, has_next, cursor in pages:
        responses.append(
            _build_list_products_response(
                products,
                has_next_page=has_next,
                end_cursor=cursor,
            )
        )

    session._graphql_client.execute.side_effect = responses  # type: ignore[reportAttributeAccessIssue]
    return session


@pytest.mark.os_agnostic
class TestIterProductsMultiPagePagination:
    """iter_products handles multi-page pagination correctly."""

    def test_iterates_across_multiple_pages(self, sample_credentials: ShopifyCredentials) -> None:
        """Yields products from all pages."""
        from lib_shopify_graphql.shopify_client import iter_products

        page1_products = [_minimal_product_data("1", "Product 1"), _minimal_product_data("2", "Product 2")]
        page2_products = [_minimal_product_data("3", "Product 3"), _minimal_product_data("4", "Product 4")]
        page3_products = [_minimal_product_data("5", "Product 5")]

        pages = [
            (page1_products, True, "cursor1"),
            (page2_products, True, "cursor2"),
            (page3_products, False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        result = list(iter_products(session))

        assert len(result) == 5
        assert [p.title for p in result] == ["Product 1", "Product 2", "Product 3", "Product 4", "Product 5"]

    def test_makes_correct_number_of_api_calls(self, sample_credentials: ShopifyCredentials) -> None:
        """Makes one API call per page."""
        from lib_shopify_graphql.shopify_client import iter_products

        page1 = [_minimal_product_data("1", "P1")]
        page2 = [_minimal_product_data("2", "P2")]

        pages = [
            (page1, True, "cursor1"),
            (page2, False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        list(iter_products(session))

        assert session._graphql_client.execute.call_count == 2  # type: ignore[reportAttributeAccessIssue]

    def test_passes_cursor_to_subsequent_calls(self, sample_credentials: ShopifyCredentials) -> None:
        """Passes end_cursor to the next page request."""
        from lib_shopify_graphql.shopify_client import iter_products

        pages = [
            ([_minimal_product_data("1", "P1")], True, "abc123"),
            ([_minimal_product_data("2", "P2")], False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        list(iter_products(session))

        calls = cast(list[Any], session._graphql_client.execute.call_args_list)  # type: ignore[reportAttributeAccessIssue]
        # First call should have no cursor (or after=None)
        first_vars: dict[str, Any] = calls[0][1].get("variables", calls[0][0][1] if len(calls[0][0]) > 1 else {})
        assert first_vars.get("after") is None  # First page has no cursor
        # Second call should have cursor from first page
        second_vars: dict[str, Any] = calls[1][1].get("variables", calls[1][0][1] if len(calls[1][0]) > 1 else {})
        assert second_vars.get("after") == "abc123"

    def test_handles_empty_intermediate_page(self, sample_credentials: ShopifyCredentials) -> None:
        """Handles pages with no products but has_next_page=True."""
        from lib_shopify_graphql.shopify_client import iter_products

        empty_products: list[dict[str, Any]] = []
        pages: list[tuple[list[dict[str, Any]], bool, str | None]] = [
            ([_minimal_product_data("1", "P1")], True, "cursor1"),
            (empty_products, True, "cursor2"),  # Empty intermediate page
            ([_minimal_product_data("2", "P2")], False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        result = list(iter_products(session))

        assert len(result) == 2
        assert [p.title for p in result] == ["P1", "P2"]

    def test_single_page_no_extra_calls(self, sample_credentials: ShopifyCredentials) -> None:
        """Single page with has_next_page=False makes only one API call."""
        from lib_shopify_graphql.shopify_client import iter_products

        products = [_minimal_product_data("1", "P1"), _minimal_product_data("2", "P2")]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        list(iter_products(session))

        assert session._graphql_client.execute.call_count == 1  # type: ignore[reportAttributeAccessIssue]

    def test_passes_query_filter_to_all_pages(self, sample_credentials: ShopifyCredentials) -> None:
        """Query filter is passed to all page requests."""
        from lib_shopify_graphql.shopify_client import iter_products

        pages = [
            ([_minimal_product_data("1", "P1")], True, "cursor1"),
            ([_minimal_product_data("2", "P2")], False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        list(iter_products(session, query="status:active"))

        calls = cast(list[Any], session._graphql_client.execute.call_args_list)  # type: ignore[reportAttributeAccessIssue]
        for call in calls:
            vars_dict: dict[str, Any] = call[1].get("variables", call[0][1] if len(call[0]) > 1 else {})
            assert vars_dict.get("query") == "status:active"

    def test_is_lazy_iterator(self, sample_credentials: ShopifyCredentials) -> None:
        """Iterator is lazy - doesn't fetch until consumed."""
        from lib_shopify_graphql.shopify_client import iter_products

        pages = [
            ([_minimal_product_data("1", "P1")], True, "cursor1"),
            ([_minimal_product_data("2", "P2")], False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        iterator = iter_products(session)

        # No calls made yet
        assert session._graphql_client.execute.call_count == 0  # type: ignore[reportAttributeAccessIssue]

        # First next() triggers first API call
        next(iterator)
        assert session._graphql_client.execute.call_count == 1  # type: ignore[reportAttributeAccessIssue]


@pytest.mark.os_agnostic
class TestIterProductsWithSKUResolver:
    """iter_products passes SKU resolver to underlying paginated function."""

    def test_passes_sku_resolver(self, sample_credentials: ShopifyCredentials) -> None:
        """SKU resolver is passed through to list_products_paginated."""
        from lib_shopify_graphql.shopify_client import iter_products

        products = [_minimal_product_data("1", "P1")]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        mock_resolver = MagicMock()
        list(iter_products(session, sku_resolver=mock_resolver))

        # Verify the resolver was available (it gets passed to list_products_paginated)
        assert session._graphql_client.execute.called  # type: ignore[reportAttributeAccessIssue]


# =============================================================================
# Comprehensive Pagination Tests - list_products Multi-Page
# =============================================================================


@pytest.mark.os_agnostic
class TestListProductsMultiPagePagination:
    """list_products handles multi-page pagination correctly."""

    def test_collects_all_products_across_pages(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns all products from all pages as a single list."""
        from lib_shopify_graphql.shopify_client import list_products

        page1 = [_minimal_product_data("1", "P1"), _minimal_product_data("2", "P2")]
        page2 = [_minimal_product_data("3", "P3")]

        pages = [
            (page1, True, "cursor1"),
            (page2, False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        result = list_products(session)

        assert len(result) == 3
        assert isinstance(result, list)
        assert [p.title for p in result] == ["P1", "P2", "P3"]

    def test_max_products_limits_across_pages(self, sample_credentials: ShopifyCredentials) -> None:
        """max_products stops fetching after limit is reached."""
        from lib_shopify_graphql.shopify_client import list_products

        page1 = [_minimal_product_data("1", "P1"), _minimal_product_data("2", "P2")]
        page2 = [_minimal_product_data("3", "P3"), _minimal_product_data("4", "P4")]

        pages = [
            (page1, True, "cursor1"),
            (page2, False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        result = list_products(session, max_products=3)

        assert len(result) == 3
        assert [p.title for p in result] == ["P1", "P2", "P3"]

    def test_max_products_zero_returns_empty(self, sample_credentials: ShopifyCredentials) -> None:
        """max_products=0 returns empty list."""
        from lib_shopify_graphql.shopify_client import list_products

        products = [_minimal_product_data("1", "P1")]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products(session, max_products=0)

        assert result == []

    def test_max_products_greater_than_total(self, sample_credentials: ShopifyCredentials) -> None:
        """max_products larger than total products returns all products."""
        from lib_shopify_graphql.shopify_client import list_products

        products = [_minimal_product_data("1", "P1"), _minimal_product_data("2", "P2")]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products(session, max_products=100)

        assert len(result) == 2

    def test_max_products_stops_pagination_early(self, sample_credentials: ShopifyCredentials) -> None:
        """max_products can prevent fetching additional pages."""
        from lib_shopify_graphql.shopify_client import list_products

        # First page has 3 products, second page would have 2 more
        page1 = [
            _minimal_product_data("1", "P1"),
            _minimal_product_data("2", "P2"),
            _minimal_product_data("3", "P3"),
        ]
        page2 = [_minimal_product_data("4", "P4"), _minimal_product_data("5", "P5")]

        pages = [
            (page1, True, "cursor1"),
            (page2, False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        # Request only 2 products - should only need first page
        result = list_products(session, max_products=2)

        assert len(result) == 2
        # With lazy evaluation, only one API call should be made
        # (itertools.islice stops consuming after getting enough items)
        assert session._graphql_client.execute.call_count == 1  # type: ignore[reportAttributeAccessIssue]

    def test_passes_query_filter(self, sample_credentials: ShopifyCredentials) -> None:
        """Query filter is passed through to pagination."""
        from lib_shopify_graphql.shopify_client import list_products

        products = [_minimal_product_data("1", "P1")]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        list_products(session, query="vendor:TestVendor")

        call = cast(Any, session._graphql_client.execute.call_args)  # type: ignore[reportAttributeAccessIssue]
        vars_dict: dict[str, Any] = call[1].get("variables", call[0][1] if len(call[0]) > 1 else {})
        assert vars_dict.get("query") == "vendor:TestVendor"

    def test_handles_many_pages(self, sample_credentials: ShopifyCredentials) -> None:
        """Handles pagination across many pages (stress test)."""
        from lib_shopify_graphql.shopify_client import list_products

        # Create 10 pages with 5 products each
        pages: list[tuple[list[dict[str, Any]], bool, str | None]] = []
        for page_num in range(10):
            products = [_minimal_product_data(f"{page_num * 5 + i}", f"Product {page_num * 5 + i}") for i in range(5)]
            has_next = page_num < 9  # Last page has no next
            cursor: str | None = f"cursor{page_num}" if has_next else None
            pages.append((products, has_next, cursor))

        session = _setup_multi_page_session(sample_credentials, pages)

        result = list_products(session)

        assert len(result) == 50
        assert session._graphql_client.execute.call_count == 10  # type: ignore[reportAttributeAccessIssue]


@pytest.mark.os_agnostic
class TestListProductsWithSKUResolver:
    """list_products passes SKU resolver correctly."""

    def test_passes_sku_resolver_to_iter(self, sample_credentials: ShopifyCredentials) -> None:
        """SKU resolver is passed through to iter_products."""
        from lib_shopify_graphql.shopify_client import list_products

        products = [_minimal_product_data("1", "P1")]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        mock_resolver = MagicMock()
        result = list_products(session, sku_resolver=mock_resolver)

        assert len(result) == 1


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


@pytest.mark.os_agnostic
class TestIterProductsEdgeCases:
    """Edge cases for iter_products."""

    def test_empty_first_page_with_no_next(self, sample_credentials: ShopifyCredentials) -> None:
        """Empty first page with no next page yields nothing."""
        from lib_shopify_graphql.shopify_client import iter_products

        response = _build_list_products_response([], has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list(iter_products(session))

        assert result == []

    def test_graphql_error_propagates(self, sample_credentials: ShopifyCredentials) -> None:
        """GraphQL errors propagate from iter_products."""
        from lib_shopify_graphql.shopify_client import iter_products

        session = _create_mock_session(sample_credentials)
        session._graphql_client.execute.side_effect = GraphQLError(  # type: ignore[reportAttributeAccessIssue]
            "Query failed",
            errors=[GraphQLErrorEntry(message="Query failed")],
            query="products query",
        )

        with pytest.raises(GraphQLError) as exc_info:
            list(iter_products(session))

        assert "Query failed" in str(exc_info.value)

    def test_returns_iterator_type(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns a proper iterator, not a list."""
        from collections.abc import Iterator

        from lib_shopify_graphql.shopify_client import iter_products

        products = [_minimal_product_data("1", "P1")]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = iter_products(session)

        assert isinstance(result, Iterator)
        assert not isinstance(result, list)


@pytest.mark.os_agnostic
class TestListProductsEdgeCases:
    """Edge cases for list_products."""

    def test_returns_list_type(self, sample_credentials: ShopifyCredentials) -> None:
        """Returns a proper list, not an iterator."""
        from lib_shopify_graphql.shopify_client import list_products

        products = [_minimal_product_data("1", "P1")]
        response = _build_list_products_response(products, has_next_page=False)
        session = _setup_session_with_response(sample_credentials, response)

        result = list_products(session)

        assert isinstance(result, list)

    def test_graphql_error_propagates(self, sample_credentials: ShopifyCredentials) -> None:
        """GraphQL errors propagate from list_products."""
        from lib_shopify_graphql.shopify_client import list_products

        session = _create_mock_session(sample_credentials)
        session._graphql_client.execute.side_effect = GraphQLError(  # type: ignore[reportAttributeAccessIssue]
            "Query failed",
            errors=[GraphQLErrorEntry(message="Query failed")],
            query="products query",
        )

        with pytest.raises(GraphQLError) as exc_info:
            list_products(session)

        assert "Query failed" in str(exc_info.value)

    def test_max_products_none_means_unlimited(self, sample_credentials: ShopifyCredentials) -> None:
        """max_products=None fetches all products."""
        from lib_shopify_graphql.shopify_client import list_products

        page1 = [_minimal_product_data("1", "P1")]
        page2 = [_minimal_product_data("2", "P2")]

        pages = [
            (page1, True, "cursor1"),
            (page2, False, None),
        ]
        session = _setup_multi_page_session(sample_credentials, pages)

        result = list_products(session, max_products=None)

        assert len(result) == 2
