"""Shared pytest fixtures and markers for the test suite.

Provides centralized test infrastructure including:
- OS-specific markers (os_agnostic, posix_only, windows_only, macos_only, linux_only)
- Environment markers (local_only - skipped in CI environments)
- CLI test fixtures (cli_runner, strip_ansi)
- Configuration isolation fixtures (isolated_traceback_config, preserve_traceback_state)
- Real test adapters for behavioral testing (InMemoryCache, FakeGraphQLClient)
- Shopify model fixtures for consistent test data

Note:
    Coverage uses JSON output to avoid SQLite locking issues during parallel execution.
    Tests prefer real behavior over mocks - see InMemoryCache and FakeGraphQLClient.
"""

from __future__ import annotations

# Load .env file before any other imports that might use environment variables
from pathlib import Path

from dotenv import load_dotenv

_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

import os  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from dataclasses import dataclass, field, fields  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from decimal import Decimal  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from click.testing import CliRunner  # noqa: E402

import lib_cli_exit_tools  # noqa: E402

from lib_shopify_graphql.models import (  # noqa: E402
    Money,
    Product,
    ProductImage,
    ProductOption,
    ProductStatus,
    ProductVariant,
    ShopifyCredentials,
)


# =============================================================================
# Constants
# =============================================================================

ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
CONFIG_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(type(lib_cli_exit_tools.config)))

# Detect CI environment (used for local_only marker and MySQL tests)
_CI_ENVIRONMENT = os.environ.get("CI") in ("true", "1")


# =============================================================================
# Real Test Adapters (No Mocks!)
# =============================================================================
# These provide real behavior for testing without external dependencies.
# Using real adapters validates actual system behavior, not assumptions.


class MockConfig:
    """Real fake Config mimicking lib_layered_config.Config interface.

    Use this instead of MagicMock for testing functions that accept Config.
    Provides actual dot-notation key lookups with configurable data.

    Example:
        >>> config = MockConfig({"shopify": {"shop_url": "test.myshopify.com"}})
        >>> config.get("shopify.shop_url")
        'test.myshopify.com'
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data or {}

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        """Get nested config value using dot-notation key."""
        parts = key.split(".")
        value: Any = self._data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)  # type: ignore[union-attr]
                if value is None:
                    return default  # type: ignore[return-value]
            else:
                return default  # type: ignore[return-value]
        return value  # type: ignore[return-value]


@dataclass
class CacheEntry:
    """A cache entry with value and optional expiration."""

    value: str
    expires_at: float | None = None

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class InMemoryCache:
    """Real in-memory cache implementing CachePort.

    Use this instead of MagicMock to test actual cache behavior.
    Supports TTL expiration and all cache operations.
    """

    def __init__(self) -> None:
        self._data: dict[str, CacheEntry] = {}

    def get(self, key: str) -> str | None:
        """Get a value, returning None if missing or expired."""
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._data[key]
            return None
        return entry.value

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Store a value with optional TTL."""
        expires_at = time.time() + ttl if ttl else None
        self._data[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        self._data.pop(key, None)

    def clear(self) -> None:
        """Clear all entries."""
        self._data.clear()

    def keys(self, prefix: str | None = None) -> list[str]:
        """List all keys, optionally filtered by prefix."""
        # Filter out expired entries
        valid_keys = [key for key, entry in self._data.items() if not entry.is_expired()]
        if prefix:
            return [k for k in valid_keys if k.startswith(prefix)]
        return valid_keys

    def __len__(self) -> int:
        """Return number of entries (for test assertions)."""
        return len(self._data)


@dataclass
class FakeGraphQLClient:
    """Real fake GraphQL client implementing GraphQLClientPort.

    Use this instead of MagicMock to test actual resolution behavior.
    Configure responses via the sku_to_variant mapping (SKU -> (variant_gid, product_gid)).
    """

    # SKU -> (variant_gid, product_gid)
    sku_to_variant: dict[str, tuple[str, str]] = field(default_factory=lambda: {})
    # Multiple variants for same SKU: SKU -> [(variant_gid, product_gid), ...]
    sku_to_variants: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: {})
    call_count: int = field(default=0, init=False)
    last_query: str | None = field(default=None, init=False)
    last_variables: dict[str, Any] | None = field(default=None, init=False)
    should_raise: Exception | None = field(default=None, init=False)

    def configure(self, shop_url: str, api_version: str, access_token: str) -> None:
        """Configure the GraphQL client (no-op for fake)."""

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a fake GraphQL query returning configured responses."""
        self.call_count += 1
        self.last_query = query
        self.last_variables = variables

        if self.should_raise:
            raise self.should_raise

        # Extract SKU from variables for variant lookup
        if variables and "sku" in variables:
            sku_query = variables["sku"]
            # Handle 'sku:"ABC-123"' format from resolver (supports escaped quotes)
            import re

            # Match SKU with escaped characters: (?:[^"\\]|\\.)* matches non-quote/non-backslash OR escaped char
            match = re.search(r'sku:"((?:[^"\\]|\\.)*)"', sku_query)
            if match:
                # Unescape the captured SKU (reverse what _escape_graphql_string does)
                sku = match.group(1).replace('\\"', '"').replace("\\\\", "\\")
                return self._build_variant_response(sku)

        return {"data": {"productVariants": {"edges": []}}}

    def _build_variant_response(self, sku: str) -> dict[str, Any]:
        """Build a Shopify-like variant response for the given SKU (includes product.id)."""
        # Check for multiple variants first (for ambiguity/resolve_all tests)
        if sku in self.sku_to_variants:
            variants = self.sku_to_variants[sku]
            edges = [
                {
                    "node": {
                        "id": variant_gid,
                        "sku": sku,
                        "product": {"id": product_gid},
                    }
                }
                for variant_gid, product_gid in variants
            ]
            return {"data": {"productVariants": {"edges": edges}}}

        # Single variant: SKU -> (variant_gid, product_gid)
        if sku in self.sku_to_variant:
            variant_gid, product_gid = self.sku_to_variant[sku]
            return {
                "data": {
                    "productVariants": {
                        "edges": [
                            {
                                "node": {
                                    "id": variant_gid,
                                    "sku": sku,
                                    "product": {"id": product_gid},
                                }
                            }
                        ]
                    }
                }
            }

        # SKU not found
        return {"data": {"productVariants": {"edges": []}}}

    def add_sku_mapping(self, sku: str, gid: str, product_gid: str | None = None) -> None:
        """Add a SKU to variant mapping for testing.

        Args:
            sku: The SKU to map.
            gid: The variant GID.
            product_gid: The product GID. If None, uses a default.
        """
        if product_gid is None:
            product_gid = "gid://shopify/Product/default"
        self.sku_to_variant[sku] = (gid, product_gid)

    def add_sku_mappings(self, sku: str, gids: list[str], product_gids: list[str] | None = None) -> None:
        """Add a SKU to multiple variants mapping for testing resolve_all/ambiguity.

        Args:
            sku: The SKU to map.
            gids: List of variant GIDs.
            product_gids: List of product GIDs. If None, generates defaults.
        """
        if product_gids is None:
            product_gids = [f"gid://shopify/Product/{i}" for i in range(len(gids))]
        self.sku_to_variants[sku] = list(zip(gids, product_gids, strict=False))

    def configure_error(self, error: Exception) -> None:
        """Configure the client to raise an error on next call."""
        self.should_raise = error

    def reset_error(self) -> None:
        """Clear configured error."""
        self.should_raise = None


@dataclass
class FakeTokenProvider:
    """Real fake token provider implementing TokenProviderPort.

    Returns predictable tokens for testing authentication flows.
    """

    token: str = "fake_access_token_12345"
    expires_in_seconds: int = 86400
    should_raise: Exception | None = None

    def obtain_token(
        self,
        shop_url: str,
        client_id: str,
        client_secret: str,
    ) -> tuple[str, datetime]:
        """Return a fake token with predictable expiration."""
        if self.should_raise:
            raise self.should_raise
        expires_at = datetime.now(timezone.utc).replace(microsecond=0) + __import__("datetime").timedelta(seconds=self.expires_in_seconds)
        return (self.token, expires_at)


@dataclass
class FakeSession:
    """Real fake session for testing CLI commands that use ShopifySession.

    Simulates a ShopifySession without hitting the real API.
    Configure responses via the graphql_responses dict.

    Example:
        >>> session = FakeSession()
        >>> session.graphql_responses["products"] = {"data": {"products": {"nodes": []}}}
        >>> result = session.execute_graphql("query { products { nodes { id } } }")
        >>> result["data"]["products"]["nodes"]
        []
    """

    is_active: bool = True
    shop_url: str = "fake-shop.myshopify.com"
    # Query name/keyword -> response mapping
    graphql_responses: dict[str, dict[str, Any]] = field(default_factory=lambda: {})
    # Default response when no match found
    default_response: dict[str, Any] = field(default_factory=lambda: {"data": {}})
    # Error to raise on execute_graphql (if set)
    should_raise: Exception | None = field(default=None)
    # Track calls for assertions
    call_count: int = field(default=0, init=False)
    last_query: str | None = field(default=None, init=False)
    last_variables: dict[str, Any] | None = field(default=None, init=False)

    def execute_graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a fake GraphQL query returning configured responses."""
        self.call_count += 1
        self.last_query = query
        self.last_variables = variables

        # Raise configured error if set
        if self.should_raise is not None:
            raise self.should_raise

        # Match query to configured responses by checking if key is in query
        for key, response in self.graphql_responses.items():
            if key in query:
                return response

        return self.default_response

    def get_credentials(self) -> ShopifyCredentials:
        """Return fake credentials."""
        return ShopifyCredentials(
            shop_url=self.shop_url,
            client_id="fake_client_id",
            client_secret="fake_client_secret",
        )

    def configure_error(self, error: Exception) -> None:
        """Configure the session to raise an error on next execute_graphql call."""
        self.should_raise = error

    def reset_error(self) -> None:
        """Clear configured error."""
        self.should_raise = None


# =============================================================================
# Real Adapter Fixtures
# =============================================================================


@pytest.fixture
def in_memory_cache() -> InMemoryCache:
    """Provide a fresh in-memory cache for testing."""
    return InMemoryCache()


@pytest.fixture
def fake_graphql_client() -> FakeGraphQLClient:
    """Provide a fake GraphQL client for testing."""
    return FakeGraphQLClient()


@pytest.fixture
def fake_token_provider() -> FakeTokenProvider:
    """Provide a fake token provider for testing."""
    return FakeTokenProvider()


@pytest.fixture
def mock_config() -> Callable[[dict[str, object] | None], MockConfig]:
    """Factory fixture for creating MockConfig instances.

    Returns a factory function that creates MockConfig with specified data.

    Example:
        >>> def test_example(mock_config):
        ...     config = mock_config({"shopify": {"shop_url": "test.myshopify.com"}})
        ...     assert config.get("shopify.shop_url") == "test.myshopify.com"
    """

    def _create(data: dict[str, object] | None = None) -> MockConfig:
        return MockConfig(data)

    return _create


@pytest.fixture
def fake_session() -> FakeSession:
    """Provide a fresh fake session for testing.

    Returns a FakeSession that can be configured with custom responses.
    """
    return FakeSession()


# =============================================================================
# OS-Specific Markers Registration
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for OS-specific and environment test categorization."""
    config.addinivalue_line("markers", "os_agnostic: test runs on all platforms")
    config.addinivalue_line("markers", "posix_only: test runs only on POSIX systems (Linux, macOS)")
    config.addinivalue_line("markers", "windows_only: test runs only on Windows")
    config.addinivalue_line("markers", "macos_only: test runs only on macOS")
    config.addinivalue_line("markers", "linux_only: test runs only on Linux")
    config.addinivalue_line("markers", "local_only: test runs only locally (skipped in CI environments)")


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip tests based on OS/environment markers when running on incompatible platforms."""
    if item.get_closest_marker("windows_only") and sys.platform != "win32":
        pytest.skip("test requires Windows")
    if item.get_closest_marker("posix_only") and sys.platform == "win32":
        pytest.skip("test requires POSIX system")
    if item.get_closest_marker("macos_only") and sys.platform != "darwin":
        pytest.skip("test requires macOS")
    if item.get_closest_marker("linux_only") and sys.platform != "linux":
        pytest.skip("test requires Linux")
    if item.get_closest_marker("local_only") and _CI_ENVIRONMENT:
        pytest.skip("test runs only locally (skipped in CI)")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Sort CLI tests alphabetically within TestCLICommands class.

    This ensures cache management tests (00-09) run first,
    other tests (10-79) run in the middle, and cache consistency
    checks (90+) run last.
    """
    # Group items by their parent class
    cli_tests: list[pytest.Item] = []
    other_tests: list[pytest.Item] = []

    for item in items:
        if "TestCLICommands" in item.nodeid:
            cli_tests.append(item)
        else:
            other_tests.append(item)

    # Sort CLI tests alphabetically by name (which respects numeric prefixes)
    cli_tests.sort(key=lambda x: x.name)

    # Replace items in-place with sorted order
    items[:] = other_tests + cli_tests


# =============================================================================
# ANSI Escape Handling
# =============================================================================


def _remove_ansi_codes(text: str) -> str:
    """Strip ANSI escape sequences from text for stable assertions."""
    return ANSI_ESCAPE_PATTERN.sub("", text)


# =============================================================================
# CLI Configuration Snapshot/Restore
# =============================================================================


def _snapshot_cli_config() -> dict[str, object]:
    """Capture all attributes from lib_cli_exit_tools.config."""
    return {name: getattr(lib_cli_exit_tools.config, name) for name in CONFIG_FIELDS}


def _restore_cli_config(snapshot: dict[str, object]) -> None:
    """Restore lib_cli_exit_tools.config from a snapshot."""
    for name, value in snapshot.items():
        setattr(lib_cli_exit_tools.config, name, value)


# =============================================================================
# CLI Test Fixtures
# =============================================================================


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a fresh CliRunner for invoking Click commands.

    Click 8.x provides separate result.stdout and result.stderr attributes.
    Use result.stdout for clean output (e.g., JSON parsing) to avoid
    async log messages from stderr contaminating the output.
    """
    return CliRunner()


@pytest.fixture
def strip_ansi() -> Callable[[str], str]:
    """Provide a helper to strip ANSI escape sequences from strings."""
    return _remove_ansi_codes


# =============================================================================
# Traceback Configuration Fixtures
# =============================================================================


@pytest.fixture
def preserve_traceback_state() -> Iterator[None]:
    """Snapshot and restore the entire lib_cli_exit_tools configuration."""
    snapshot = _snapshot_cli_config()
    try:
        yield
    finally:
        _restore_cli_config(snapshot)


@pytest.fixture
def isolated_traceback_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset traceback flags to a known baseline before each test."""
    lib_cli_exit_tools.reset_config()
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False, raising=False)


# =============================================================================
# Shopify Test Data Fixtures
# =============================================================================


@pytest.fixture
def sample_credentials() -> ShopifyCredentials:
    """Provide valid Shopify credentials for testing."""
    return ShopifyCredentials(
        shop_url="test-store.myshopify.com",
        client_id="test_client_id",
        client_secret="test_client_secret",
        api_version="2026-01",
    )


@pytest.fixture
def sample_money() -> Money:
    """Provide a Money instance for testing."""
    return Money(amount=Decimal("19.99"), currency_code="USD")


@pytest.fixture
def sample_product_image() -> ProductImage:
    """Provide a ProductImage instance for testing."""
    return ProductImage(
        id="gid://shopify/ProductImage/123",
        url="https://cdn.shopify.com/image.jpg",
        alt_text="Product photo",
        width=800,
        height=600,
    )


@pytest.fixture
def sample_product_variant(sample_money: Money) -> ProductVariant:
    """Provide a ProductVariant instance for testing."""
    return ProductVariant(
        id="gid://shopify/ProductVariant/123",
        title="Small / Red",
        sku="SKU-001",
        price=sample_money,
        available_for_sale=True,
    )


@pytest.fixture
def sample_product_option() -> ProductOption:
    """Provide a ProductOption instance for testing."""
    return ProductOption(
        id="gid://shopify/ProductOption/1",
        name="Size",
        position=1,
        values=["Small", "Medium", "Large"],
    )


@pytest.fixture
def sample_product(
    sample_product_variant: ProductVariant,
    sample_product_image: ProductImage,
) -> Product:
    """Provide a complete Product instance for testing."""
    now = datetime.now(timezone.utc)
    return Product(
        id="gid://shopify/Product/123",
        title="Test Product",
        handle="test-product",
        status=ProductStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        variants=[sample_product_variant],
        images=[sample_product_image],
        featured_image=sample_product_image,
        tags=["tag1", "tag2"],
    )


@pytest.fixture
def graphql_product_response() -> dict[str, Any]:
    """Provide a realistic GraphQL product response for testing."""
    return {
        "data": {
            "product": {
                "id": "gid://shopify/Product/123456789",
                "legacyResourceId": "123456789",
                "title": "Test Product",
                "description": "A test product",
                "descriptionHtml": "<p>A test product</p>",
                "handle": "test-product",
                "vendor": "Test Vendor",
                "productType": "Test Type",
                "status": "ACTIVE",
                "tags": ["tag1", "tag2"],
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-02T00:00:00Z",
                "publishedAt": "2024-01-01T12:00:00Z",
                "totalInventory": 100,
                "tracksInventory": True,
                "hasOnlyDefaultVariant": True,
                "hasOutOfStockVariants": False,
                "isGiftCard": False,
                "onlineStoreUrl": "https://test-store.myshopify.com/products/test-product",
                "onlineStorePreviewUrl": "https://test-store.myshopify.com/products/test-product?preview=true",
                "templateSuffix": None,
                "featuredImage": {
                    "id": "gid://shopify/ProductImage/1",
                    "url": "https://cdn.shopify.com/featured.jpg",
                    "altText": "Featured image",
                    "width": 800,
                    "height": 600,
                },
                "images": {
                    "nodes": [
                        {
                            "id": "gid://shopify/ProductImage/1",
                            "url": "https://cdn.shopify.com/featured.jpg",
                            "altText": "Featured image",
                            "width": 800,
                            "height": 600,
                        },
                        {
                            "id": "gid://shopify/ProductImage/2",
                            "url": "https://cdn.shopify.com/second.jpg",
                            "altText": None,
                            "width": 1024,
                            "height": 768,
                        },
                    ],
                },
                "options": [
                    {
                        "id": "gid://shopify/ProductOption/1",
                        "name": "Title",
                        "position": 1,
                        "values": ["Default Title"],
                    },
                ],
                "seo": {
                    "title": "Test Product - SEO Title",
                    "description": "SEO description for the test product",
                },
                "priceRangeV2": {
                    "minVariantPrice": {
                        "amount": "19.99",
                        "currencyCode": "USD",
                    },
                    "maxVariantPrice": {
                        "amount": "19.99",
                        "currencyCode": "USD",
                    },
                },
                "metafields": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Metafield/1",
                            "namespace": "custom",
                            "key": "color",
                            "value": "blue",
                            "type": "single_line_text_field",
                            "createdAt": "2024-01-01T00:00:00Z",
                            "updatedAt": "2024-01-02T00:00:00Z",
                        },
                    ],
                },
                "variants": {
                    "nodes": [
                        {
                            "id": "gid://shopify/ProductVariant/1",
                            "title": "Default Title",
                            "displayName": "Test Product - Default Title",
                            "sku": "TEST-SKU-001",
                            "barcode": "1234567890123",
                            "price": "19.99",
                            "compareAtPrice": "29.99",
                            "inventoryQuantity": 100,
                            "inventoryPolicy": "DENY",
                            "availableForSale": True,
                            "taxable": True,
                            "position": 1,
                            "createdAt": "2024-01-01T00:00:00Z",
                            "updatedAt": "2024-01-02T00:00:00Z",
                            "image": None,
                            "selectedOptions": [
                                {"name": "Title", "value": "Default Title"},
                            ],
                            "metafields": {
                                "nodes": [],
                            },
                        },
                    ],
                },
            },
        },
    }


# =============================================================================
# Integration Test Fixtures (for slow tests)
# =============================================================================


@pytest.fixture(scope="session")
def integration_credentials() -> ShopifyCredentials | None:
    """Get credentials for integration tests from environment.

    Supports two authentication methods:
    1. Direct access token: Set SHOPIFY__SHOP_URL and SHOPIFY__ACCESS_TOKEN
    2. Client credentials: Set SHOPIFY__SHOP_URL, SHOPIFY__CLIENT_ID, SHOPIFY__CLIENT_SECRET

    Returns None if credentials are not configured, allowing tests to be skipped.
    """
    import os

    shop_url = os.environ.get("SHOPIFY__SHOP_URL")
    if shop_url is None:
        return None

    # Method 1: Direct access token (Custom Apps)
    access_token = os.environ.get("SHOPIFY__ACCESS_TOKEN")
    if access_token:
        return ShopifyCredentials(
            shop_url=shop_url,
            access_token=access_token,
        )

    # Method 2: Client credentials grant (Partner Apps)
    client_id = os.environ.get("SHOPIFY__CLIENT_ID")
    client_secret = os.environ.get("SHOPIFY__CLIENT_SECRET")

    if client_id is None or client_secret is None:
        return None

    return ShopifyCredentials(
        shop_url=shop_url,
        client_id=client_id,
        client_secret=client_secret,
    )


@pytest.fixture(scope="session")
def integration_session(integration_credentials: ShopifyCredentials | None) -> Iterator[Any]:
    """Create a session for the entire integration test run.

    Skips all integration tests if credentials are not configured.
    """
    if integration_credentials is None:
        pytest.skip("Integration credentials not configured (SHOPIFY__* env vars)")

    from lib_shopify_graphql import login, logout

    session = login(integration_credentials)
    yield session
    logout(session)


def _find_product_with_sku(session: Any) -> Product:
    """Find a product in the shop that has at least one variant with a SKU.

    Args:
        session: Active Shopify session.

    Returns:
        A Product that has at least one variant with a non-empty SKU.

    Raises:
        pytest.skip: If no product with a SKU is found in the shop.
    """
    from lib_shopify_graphql import iter_products

    for product in iter_products(session):
        for variant in product.variants:
            if variant.sku:
                return product

    pytest.skip("No product with a SKU found in the shop")
    raise AssertionError("Unreachable")  # For type checker


@pytest.fixture(scope="session")
def primary_location(integration_session: Any) -> str:
    """Get the shop's primary location GID for inventory tests.

    Fetches the first active location from the shop. Inventory operations
    require a location ID.

    Returns:
        Location GID (e.g., "gid://shopify/Location/123456789").
    """
    from lib_shopify_graphql.adapters.location_resolver import PRIMARY_LOCATION_QUERY

    result = integration_session.execute_graphql(PRIMARY_LOCATION_QUERY)
    edges = result.get("data", {}).get("locations", {}).get("edges", [])

    if not edges:
        pytest.skip("No locations found in shop")

    location_id = edges[0].get("node", {}).get("id")
    if not location_id:
        pytest.skip("No valid location ID found")

    return location_id


# GraphQL mutation to activate inventory at a location
INVENTORY_ACTIVATE_MUTATION = """
mutation InventoryActivate($inventoryItemId: ID!, $locationId: ID!, $available: Int) {
    inventoryActivate(
        inventoryItemId: $inventoryItemId
        locationId: $locationId
        available: $available
    ) {
        inventoryLevel {
            id
            quantities(names: ["available"]) {
                name
                quantity
            }
        }
        userErrors {
            field
            message
        }
    }
}
"""

# GraphQL query to get variant's inventory item ID
VARIANT_INVENTORY_ITEM_QUERY = """
query VariantInventoryItem($id: ID!) {
    productVariant(id: $id) {
        id
        inventoryItem {
            id
        }
    }
}
"""


def _activate_inventory_at_location(
    session: Any,
    variant_id: str,
    location_id: str,
    quantity: int = 0,
) -> None:
    """Activate inventory for a variant at a location.

    This is required before setting/adjusting inventory for a variant
    at a location that doesn't already stock it.
    """
    # Get inventory item ID for the variant
    result = session.execute_graphql(VARIANT_INVENTORY_ITEM_QUERY, {"id": variant_id})
    inventory_item_id = result.get("data", {}).get("productVariant", {}).get("inventoryItem", {}).get("id")
    if not inventory_item_id:
        return

    # Activate inventory at location
    session.execute_graphql(
        INVENTORY_ACTIVATE_MUTATION,
        {
            "inventoryItemId": inventory_item_id,
            "locationId": location_id,
            "available": quantity,
        },
    )


@pytest.fixture(scope="session")
def test_product(integration_session: Any, primary_location: str) -> Iterator[Product]:
    """Duplicate a product for testing, delete at end of session.

    Automatically finds a product with a SKU in the shop to use as source.
    The duplicated product is created with DRAFT status and a unique title.
    After duplication, assigns random SKUs and activates inventory at primary location.
    """
    import uuid

    from lib_shopify_graphql import (
        VariantUpdate,
        delete_product,
        duplicate_product,
        get_product_by_id,
        update_variant,
    )

    # Find a product with a SKU to use as source
    source_product = _find_product_with_sku(integration_session)

    # Duplicate it with unique test title
    test_title = f"[TEST] {source_product.title} - {uuid.uuid4().hex[:8]}"
    result = duplicate_product(
        integration_session,
        source_product.id,
        test_title,
        include_images=True,  # Copy images for full test coverage
        new_status=ProductStatus.DRAFT,  # Keep as draft
    )

    new_product = result.new_product

    # Assign random SKUs and activate inventory at primary location
    for variant in new_product.variants:
        new_sku = f"TEST-{uuid.uuid4().hex[:12]}"
        update_variant(
            integration_session,
            variant.id,
            VariantUpdate(sku=new_sku),
            product_id=new_product.id,
        )
        # Activate inventory at primary location for inventory tests
        _activate_inventory_at_location(
            integration_session,
            variant.id,
            primary_location,
            quantity=0,
        )

    # Re-fetch product to get updated variant SKUs
    updated_product = get_product_by_id(integration_session, new_product.id)

    yield updated_product

    # Cleanup: delete the test product
    delete_product(integration_session, updated_product.id)


# =============================================================================
# MySQL Integration Test Fixtures
# =============================================================================


@dataclass
class MySQLTestConfig:
    """MySQL connection parameters for tests."""

    host: str
    port: int
    user: str
    password: str
    database: str


def _get_mysql_config() -> MySQLTestConfig | None:
    """Get MySQL config from environment (connection string OR individual params).

    Supports two configuration methods:
    1. Connection string: SHOPIFY__MYSQL__CONNECTION=mysql://user:pass@host:port/db
    2. Individual parameters: SHOPIFY__MYSQL__HOST, USER, PASSWORD, PORT, DATABASE

    Returns:
        MySQLTestConfig if configured, None otherwise.
    """
    import os

    # Option 1: Connection string (takes precedence)
    connection = os.environ.get("SHOPIFY__MYSQL__CONNECTION")
    if connection:
        from urllib.parse import urlparse

        parsed = urlparse(connection)
        return MySQLTestConfig(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "",
            password=parsed.password or "",
            database=parsed.path.lstrip("/"),
        )

    # Option 2: Individual parameters
    host = os.environ.get("SHOPIFY__MYSQL__HOST")
    user = os.environ.get("SHOPIFY__MYSQL__USER")
    database = os.environ.get("SHOPIFY__MYSQL__DATABASE")

    if host and user and database:
        return MySQLTestConfig(
            host=host,
            port=int(os.environ.get("SHOPIFY__MYSQL__PORT", "3306")),
            user=user,
            password=os.environ.get("SHOPIFY__MYSQL__PASSWORD", ""),
            database=database,
        )

    return None


def _verify_mysql_connection(config: MySQLTestConfig) -> tuple[bool, bool, str]:
    """Verify MySQL connection and permissions.

    Args:
        config: MySQL connection configuration.

    Returns:
        Tuple of (can_connect, database_exists, error_message).
        On success, error_message is empty.
    """
    try:
        import pymysql

        # First try connecting to the specific database (if it exists)
        try:
            conn = pymysql.connect(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                database=config.database,
            )
            conn.close()
            return True, True, ""  # Can connect, database exists
        except pymysql.err.OperationalError as e:
            # Database doesn't exist (1049) - check if we can connect at server level
            if e.args[0] == 1049:
                try:
                    conn = pymysql.connect(
                        host=config.host,
                        port=config.port,
                        user=config.user,
                        password=config.password,
                    )
                    conn.close()
                    return True, False, ""  # Can connect, but database doesn't exist
                except pymysql.err.OperationalError:
                    # User can only connect to specific database, which doesn't exist
                    return False, False, f"Database '{config.database}' does not exist and user lacks CREATE privilege"
            else:
                return False, False, str(e)
    except Exception as e:
        return False, False, str(e)


def _drop_mysql_database(config: MySQLTestConfig) -> None:
    """Drop MySQL database if it exists.

    Args:
        config: MySQL connection configuration.

    Note:
        Logs warning on failure but does not raise - cleanup is best-effort.
    """
    try:
        import pymysql

        conn = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
        )
        with conn.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{config.database}`")
        conn.commit()
        conn.close()
        print(f"[MySQL cleanup] Dropped database: {config.database}")
    except Exception as e:
        print(f"[MySQL cleanup] Warning - failed to drop database {config.database}: {e}")


@dataclass
class MySQLTestState:
    """Extended MySQL config with runtime state."""

    config: MySQLTestConfig
    database_exists: bool  # If True, use auto_create_database=False


@pytest.fixture(scope="session")
def mysql_test_config() -> Iterator[MySQLTestState]:
    """Get MySQL test configuration and manage database lifecycle.

    Supports both connection string and individual parameter configuration.
    Attempts to drop database on test start (cleanup from previous runs) and after tests complete.

    Skipped when:
    - Running in CI environment (CI=true)
    - pymysql not installed
    - MySQL not configured in environment
    - MySQL connection fails (wrong credentials, server unreachable)

    Yields:
        MySQLTestState: Connection configuration with runtime state.
    """
    if _CI_ENVIRONMENT:
        pytest.skip("MySQL tests skipped in CI")

    # Check if pymysql is available
    try:
        from lib_shopify_graphql.adapters.cache_mysql import PYMYSQL_AVAILABLE

        if not PYMYSQL_AVAILABLE:
            pytest.skip("pymysql not installed (install with: pip install lib_shopify_graphql[mysql])")
    except ImportError:
        pytest.skip("cache_mysql module not available")

    config = _get_mysql_config()
    if config is None:
        pytest.skip("MySQL not configured (set SHOPIFY__MYSQL__CONNECTION or individual params)")

    # Verify MySQL connection before proceeding
    can_connect, database_exists, error = _verify_mysql_connection(config)
    if not can_connect:
        pytest.skip(f"MySQL connection failed: {error}")

    # If we can connect at server level, try dropping the database for cleanup
    if not database_exists:
        _drop_mysql_database(config)

    state = MySQLTestState(config=config, database_exists=database_exists)

    yield state

    # Cleanup: Drop the database after tests complete - best effort
    _drop_mysql_database(config)


@pytest.fixture(scope="session")
def mysql_sku_cache(mysql_test_config: MySQLTestState) -> Any:
    """MySQL SKU cache adapter for integration tests.

    Uses session-scoped mysql_test_config fixture for database lifecycle management.

    Args:
        mysql_test_config: MySQL test state with connection config.

    Returns:
        MySQLCacheAdapter: Configured cache adapter for SKU storage.
    """
    from lib_shopify_graphql.adapters import MySQLCacheAdapter

    cfg = mysql_test_config.config
    # If database already exists, don't try to create it (user may lack CREATE privilege)
    auto_create = not mysql_test_config.database_exists

    cache = MySQLCacheAdapter(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        table_name="sku_cache",
        auto_create_database=auto_create,
    )

    return cache


@pytest.fixture(scope="session")
def mysql_token_cache(mysql_test_config: MySQLTestState) -> Any:
    """MySQL token cache adapter for integration tests.

    Uses session-scoped mysql_test_config fixture for database lifecycle management.

    Args:
        mysql_test_config: MySQL test state with connection config.

    Returns:
        MySQLCacheAdapter: Configured cache adapter for token storage.
    """
    from lib_shopify_graphql.adapters import MySQLCacheAdapter

    cfg = mysql_test_config.config
    # If database already exists, don't try to create it (user may lack CREATE privilege)
    auto_create = not mysql_test_config.database_exists

    cache = MySQLCacheAdapter(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        table_name="token_cache",
        auto_create_database=auto_create,
    )

    return cache
