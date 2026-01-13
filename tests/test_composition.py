"""Composition root tests: verifying factory functions and adapter creation.

Tests use real implementations and temporary directories to validate
actual composition behavior. Each test reads like plain English.

Coverage:
- create_adapters returns proper bundles
- get_default_adapters returns singleton
- create_json_cache creates file adapter
- create_sku_resolver with cache path
- create_location_resolver with defaults
- create_cached_token_provider with cache path
- Error handling for missing required arguments
- Config-driven default resolvers/providers
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lib_shopify_graphql.composition import (
    AdapterBundle,
    create_adapters,
    create_cached_token_provider,
    create_json_cache,
    create_location_resolver,
    create_sku_resolver,
    get_default_adapters,
    get_default_sku_resolver,
    get_default_token_provider,
    reset_default_resolvers,
    _create_sku_cache_from_config,
    _create_token_cache_from_config,
)
from lib_shopify_graphql.adapters import (
    CachedSKUResolver,
    CachedTokenProvider,
    JsonFileCacheAdapter,
    LocationResolver,
)

from conftest import FakeGraphQLClient, FakeTokenProvider, InMemoryCache


# =============================================================================
# create_adapters
# =============================================================================


@pytest.mark.os_agnostic
class TestCreateAdapters:
    """create_adapters creates adapter bundles for injection."""

    def test_returns_adapter_bundle(self) -> None:
        """Returns an AdapterBundle with required keys."""
        bundle = create_adapters()

        assert "token_provider" in bundle
        assert "session_manager" in bundle
        assert "graphql_client" in bundle

    def test_uses_custom_token_provider(self, fake_token_provider: FakeTokenProvider) -> None:
        """Custom token provider is used when provided."""
        bundle = create_adapters(token_provider=fake_token_provider)

        assert bundle["token_provider"] is fake_token_provider

    def test_uses_custom_graphql_client(self, fake_graphql_client: FakeGraphQLClient) -> None:
        """Custom GraphQL client is used when provided."""
        bundle = create_adapters(graphql_client=fake_graphql_client)

        assert bundle["graphql_client"] is fake_graphql_client


# =============================================================================
# get_default_adapters
# =============================================================================


@pytest.mark.os_agnostic
class TestGetDefaultAdapters:
    """get_default_adapters returns singleton bundle."""

    def test_returns_adapter_bundle(self) -> None:
        """Returns an AdapterBundle."""
        bundle = get_default_adapters()

        assert isinstance(bundle, dict)
        assert "token_provider" in bundle

    def test_returns_same_instance(self) -> None:
        """Multiple calls return same instance (singleton)."""
        bundle1 = get_default_adapters()
        bundle2 = get_default_adapters()

        assert bundle1 is bundle2


# =============================================================================
# create_json_cache
# =============================================================================


@pytest.mark.os_agnostic
class TestCreateJsonCache:
    """create_json_cache creates JSON file cache adapters."""

    def test_creates_json_cache_adapter(self, tmp_path: Path) -> None:
        """Returns JsonFileCacheAdapter with correct path."""
        cache_path = tmp_path / "cache.json"

        cache = create_json_cache(cache_path)

        assert isinstance(cache, JsonFileCacheAdapter)
        assert cache.cache_path == cache_path

    def test_uses_custom_lock_timeout(self, tmp_path: Path) -> None:
        """Custom lock timeout is passed to adapter."""
        cache_path = tmp_path / "cache.json"

        cache = create_json_cache(cache_path, lock_timeout=30.0)

        assert isinstance(cache, JsonFileCacheAdapter)
        assert cache.lock_timeout == 30.0


# =============================================================================
# create_sku_resolver
# =============================================================================


@pytest.mark.os_agnostic
class TestCreateSkuResolver:
    """create_sku_resolver creates cached SKU resolvers."""

    def test_creates_with_cache_path(self, tmp_path: Path, fake_graphql_client: FakeGraphQLClient) -> None:
        """Creates resolver with JSON cache from path."""
        cache_path = tmp_path / "sku_cache.json"

        resolver = create_sku_resolver(
            cache_path=cache_path,
            graphql_client=fake_graphql_client,
        )

        assert isinstance(resolver, CachedSKUResolver)

    def test_creates_with_custom_cache(self, in_memory_cache: InMemoryCache, fake_graphql_client: FakeGraphQLClient) -> None:
        """Creates resolver with custom cache implementation."""
        resolver = create_sku_resolver(
            cache=in_memory_cache,
            graphql_client=fake_graphql_client,
        )

        assert isinstance(resolver, CachedSKUResolver)

    def test_uses_custom_ttl(self, tmp_path: Path, fake_graphql_client: FakeGraphQLClient) -> None:
        """Custom cache TTL is used."""
        cache_path = tmp_path / "sku_cache.json"

        resolver = create_sku_resolver(
            cache_path=cache_path,
            graphql_client=fake_graphql_client,
            cache_ttl=7200,
        )

        assert isinstance(resolver, CachedSKUResolver)
        assert resolver.cache_ttl == 7200

    def test_raises_without_cache_or_path(self, fake_graphql_client: FakeGraphQLClient) -> None:
        """ValueError raised when neither cache nor cache_path provided."""
        with pytest.raises(ValueError, match="Either cache or cache_path must be provided"):
            create_sku_resolver(graphql_client=fake_graphql_client)


# =============================================================================
# create_location_resolver
# =============================================================================


@pytest.mark.os_agnostic
class TestCreateLocationResolver:
    """create_location_resolver creates location resolvers."""

    def test_creates_with_custom_graphql_client(self, fake_graphql_client: FakeGraphQLClient) -> None:
        """Creates resolver with custom GraphQL client."""
        resolver = create_location_resolver(graphql_client=fake_graphql_client)

        assert isinstance(resolver, LocationResolver)
        assert resolver.graphql is fake_graphql_client

    def test_uses_default_location(self, fake_graphql_client: FakeGraphQLClient) -> None:
        """Default location ID is passed to resolver."""
        resolver = create_location_resolver(
            graphql_client=fake_graphql_client,
            default_location_id="gid://shopify/Location/12345",
        )

        # Cast to concrete type to access implementation detail
        assert isinstance(resolver, LocationResolver)
        assert resolver.default_location_id == "gid://shopify/Location/12345"


# =============================================================================
# create_cached_token_provider
# =============================================================================


@pytest.mark.os_agnostic
class TestCreateCachedTokenProvider:
    """create_cached_token_provider creates cached token providers."""

    def test_creates_with_cache_path(self, tmp_path: Path, fake_token_provider: FakeTokenProvider) -> None:
        """Creates provider with JSON cache from path."""
        cache_path = tmp_path / "token_cache.json"

        provider = create_cached_token_provider(
            cache_path=cache_path,
            delegate=fake_token_provider,
        )

        assert isinstance(provider, CachedTokenProvider)

    def test_creates_with_custom_cache(self, in_memory_cache: InMemoryCache, fake_token_provider: FakeTokenProvider) -> None:
        """Creates provider with custom cache implementation."""
        provider = create_cached_token_provider(
            cache=in_memory_cache,
            delegate=fake_token_provider,
        )

        assert isinstance(provider, CachedTokenProvider)
        assert provider.cache is in_memory_cache

    def test_uses_custom_refresh_margin(self, tmp_path: Path, fake_token_provider: FakeTokenProvider) -> None:
        """Custom refresh margin is used."""
        cache_path = tmp_path / "token_cache.json"

        provider = create_cached_token_provider(
            cache_path=cache_path,
            delegate=fake_token_provider,
            refresh_margin=600,
        )

        assert isinstance(provider, CachedTokenProvider)
        assert provider.refresh_margin == 600

    def test_raises_without_cache_or_path(self, fake_token_provider: FakeTokenProvider) -> None:
        """ValueError raised when neither cache nor cache_path provided."""
        with pytest.raises(ValueError, match="Either cache or cache_path must be provided"):
            create_cached_token_provider(delegate=fake_token_provider)


# =============================================================================
# AdapterBundle Type
# =============================================================================


@pytest.mark.os_agnostic
class TestAdapterBundleType:
    """AdapterBundle is a proper TypedDict."""

    def test_bundle_has_correct_keys(self) -> None:
        """AdapterBundle has expected key annotations."""
        # Check that required keys are in annotations
        annotations = AdapterBundle.__annotations__

        assert "token_provider" in annotations
        assert "session_manager" in annotations
        assert "graphql_client" in annotations


# =============================================================================
# Config-Driven Default Resolvers/Providers
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singletons() -> None:
    """Reset singleton state before each test."""
    reset_default_resolvers()


@pytest.mark.os_agnostic
class TestCreateSkuCacheFromConfig:
    """_create_sku_cache_from_config creates caches from config dicts."""

    def test_json_backend_with_path(self, tmp_path: Path) -> None:
        """Creates JSON cache when backend is 'json' with path."""
        cache_path = tmp_path / "test_sku_cache.json"
        config = {"backend": "json", "json_path": str(cache_path)}

        cache = _create_sku_cache_from_config(config)

        assert cache is not None
        assert isinstance(cache, JsonFileCacheAdapter)

    def test_json_backend_without_path_uses_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Creates JSON cache with default path when not specified."""
        from lib_shopify_graphql.adapters import constants

        default_path = tmp_path / "default_sku_cache.json"
        monkeypatch.setattr(constants, "get_default_sku_cache_path", lambda: default_path)

        config = {"backend": "json"}

        cache = _create_sku_cache_from_config(config)

        assert cache is not None
        assert isinstance(cache, JsonFileCacheAdapter)

    def test_unknown_backend_returns_none(self) -> None:
        """Returns None for unknown backend."""
        config = {"backend": "redis"}

        cache = _create_sku_cache_from_config(config)

        assert cache is None

    def test_mysql_backend_without_connection_returns_none(self) -> None:
        """Returns None when MySQL backend has no connection string."""
        config = {"backend": "mysql"}

        cache = _create_sku_cache_from_config(config)

        assert cache is None

    def test_mysql_backend_without_pymysql_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when MySQL backend requested but pymysql not available."""
        import lib_shopify_graphql.composition as composition_module

        monkeypatch.setattr(composition_module, "PYMYSQL_AVAILABLE", False)
        config = {"backend": "mysql", "mysql_connection": "mysql://user:pass@host/db"}

        cache = _create_sku_cache_from_config(config)

        assert cache is None


@pytest.mark.os_agnostic
class TestCreateTokenCacheFromConfig:
    """_create_token_cache_from_config creates caches from config dicts."""

    def test_json_backend_with_path(self, tmp_path: Path) -> None:
        """Creates JSON cache when backend is 'json' with path."""
        cache_path = tmp_path / "test_token_cache.json"
        config = {"backend": "json", "json_path": str(cache_path)}

        cache = _create_token_cache_from_config(config)

        assert cache is not None
        assert isinstance(cache, JsonFileCacheAdapter)

    def test_json_backend_without_path_uses_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Creates JSON cache with default path when not specified."""
        from lib_shopify_graphql.adapters import constants

        default_path = tmp_path / "default_token_cache.json"
        monkeypatch.setattr(constants, "get_default_token_cache_path", lambda: default_path)

        config = {"backend": "json"}

        cache = _create_token_cache_from_config(config)

        assert cache is not None
        assert isinstance(cache, JsonFileCacheAdapter)

    def test_unknown_backend_returns_none(self) -> None:
        """Returns None for unknown backend."""
        config = {"backend": "memcached"}

        cache = _create_token_cache_from_config(config)

        assert cache is None

    def test_mysql_backend_without_connection_returns_none(self) -> None:
        """Returns None when MySQL backend has no connection string."""
        config = {"backend": "mysql"}

        cache = _create_token_cache_from_config(config)

        assert cache is None

    def test_mysql_backend_without_pymysql_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when MySQL backend requested but pymysql not available."""
        import lib_shopify_graphql.composition as composition_module

        monkeypatch.setattr(composition_module, "PYMYSQL_AVAILABLE", False)
        config = {"backend": "mysql", "mysql_connection": "mysql://user:pass@host/db"}

        cache = _create_token_cache_from_config(config)

        assert cache is None


# =============================================================================
# MySQL Individual Parameters Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestMySQLIndividualParametersSku:
    """Test MySQL individual parameters for SKU cache."""

    def test_mysql_with_individual_params_without_pymysql_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when MySQL requested but pymysql not available."""
        import lib_shopify_graphql.composition as composition_module

        monkeypatch.setattr(composition_module, "PYMYSQL_AVAILABLE", False)
        config = {"backend": "mysql"}
        mysql_config = {
            "host": "localhost",
            "port": 3306,
            "user": "shopify_user",
            "password": "secret",
            "database": "shopify_cache",
        }

        cache = _create_sku_cache_from_config(config, mysql_config)

        assert cache is None

    def test_mysql_without_user_returns_none(self) -> None:
        """Returns None when MySQL individual params missing user."""
        config = {"backend": "mysql"}
        mysql_config = {
            "host": "localhost",
            "port": 3306,
            "password": "secret",
            "database": "shopify_cache",
        }

        cache = _create_sku_cache_from_config(config, mysql_config)

        assert cache is None

    def test_mysql_without_database_returns_none(self) -> None:
        """Returns None when MySQL individual params missing database."""
        config = {"backend": "mysql"}
        mysql_config = {
            "host": "localhost",
            "port": 3306,
            "user": "shopify_user",
            "password": "secret",
        }

        cache = _create_sku_cache_from_config(config, mysql_config)

        assert cache is None

    def test_connection_string_takes_precedence_over_individual_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Connection string in cache config takes precedence."""
        import lib_shopify_graphql.composition as composition_module
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        monkeypatch.setattr(composition_module, "PYMYSQL_AVAILABLE", True)

        # Mock MySQLCacheAdapter.from_url to track calls
        created_params: dict[str, Any] = {}

        def mock_from_url(connection_string: str, **kwargs: Any) -> "MySQLCacheAdapter":
            created_params["connection_string"] = connection_string
            created_params.update(kwargs)
            raise ValueError("Mock: stop here")  # Stop before actual connection

        monkeypatch.setattr(MySQLCacheAdapter, "from_url", mock_from_url)

        config = {"backend": "mysql", "mysql_connection": "mysql://cache_user:pass@cache-host/cache_db"}
        mysql_config = {
            "host": "shared-host",
            "user": "shared_user",
            "password": "shared_pass",
            "database": "shared_db",
        }

        try:
            _create_sku_cache_from_config(config, mysql_config)
        except ValueError:
            pass  # Expected

        # Should use cache-level connection string, not shared config
        assert created_params["connection_string"] == "mysql://cache_user:pass@cache-host/cache_db"

    def test_shared_connection_takes_precedence_over_individual_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Connection string in mysql_config takes precedence over individual params."""
        import lib_shopify_graphql.composition as composition_module
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        monkeypatch.setattr(composition_module, "PYMYSQL_AVAILABLE", True)

        created_params: dict[str, Any] = {}

        def mock_from_url(connection_string: str, **kwargs: Any) -> "MySQLCacheAdapter":
            created_params["connection_string"] = connection_string
            created_params.update(kwargs)
            raise ValueError("Mock: stop here")

        monkeypatch.setattr(MySQLCacheAdapter, "from_url", mock_from_url)

        config = {"backend": "mysql"}  # No cache-level connection
        mysql_config = {
            "connection": "mysql://shared:pass@shared-host/shared_db",  # Shared connection string
            "host": "individual-host",  # These should be ignored
            "user": "individual_user",
            "password": "individual_pass",
            "database": "individual_db",
        }

        try:
            _create_sku_cache_from_config(config, mysql_config)
        except ValueError:
            pass  # Expected

        # Should use shared connection string
        assert created_params["connection_string"] == "mysql://shared:pass@shared-host/shared_db"


@pytest.mark.os_agnostic
class TestMySQLIndividualParametersToken:
    """Test MySQL individual parameters for token cache."""

    def test_mysql_with_individual_params_without_pymysql_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when MySQL requested but pymysql not available."""
        import lib_shopify_graphql.composition as composition_module

        monkeypatch.setattr(composition_module, "PYMYSQL_AVAILABLE", False)
        config = {"backend": "mysql"}
        mysql_config = {
            "host": "localhost",
            "port": 3306,
            "user": "shopify_user",
            "password": "secret",
            "database": "shopify_cache",
        }

        cache = _create_token_cache_from_config(config, mysql_config)

        assert cache is None

    def test_mysql_without_user_returns_none(self) -> None:
        """Returns None when MySQL individual params missing user."""
        config = {"backend": "mysql"}
        mysql_config = {
            "host": "localhost",
            "port": 3306,
            "password": "secret",
            "database": "shopify_cache",
        }

        cache = _create_token_cache_from_config(config, mysql_config)

        assert cache is None

    def test_mysql_without_database_returns_none(self) -> None:
        """Returns None when MySQL individual params missing database."""
        config = {"backend": "mysql"}
        mysql_config = {
            "host": "localhost",
            "port": 3306,
            "user": "shopify_user",
            "password": "secret",
        }

        cache = _create_token_cache_from_config(config, mysql_config)

        assert cache is None

    def test_uses_connect_timeout_from_mysql_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Uses connect_timeout from mysql_config when provided."""
        import lib_shopify_graphql.composition as composition_module
        from lib_shopify_graphql.adapters import MySQLCacheAdapter

        monkeypatch.setattr(composition_module, "PYMYSQL_AVAILABLE", True)

        created_params: dict[str, Any] = {}

        def mock_from_url(connection_string: str, **kwargs: Any) -> "MySQLCacheAdapter":
            created_params.update(kwargs)
            raise ValueError("Mock: stop here")

        monkeypatch.setattr(MySQLCacheAdapter, "from_url", mock_from_url)

        config = {"backend": "mysql", "mysql_connection": "mysql://user:pass@host/db"}
        mysql_config = {
            "connect_timeout": 30,
            "auto_create_database": False,
        }

        try:
            _create_token_cache_from_config(config, mysql_config)
        except ValueError:
            pass

        assert created_params["connect_timeout"] == 30
        assert created_params["auto_create_database"] is False


@pytest.mark.os_agnostic
class TestGetDefaultSkuResolver:
    """get_default_sku_resolver returns resolver based on config."""

    def test_returns_none_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when SKU cache is disabled in config."""
        mock_config = {"shopify": {"sku_cache": {"enabled": False}}}
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        resolver = get_default_sku_resolver()

        assert resolver is None

    def test_returns_none_when_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when sku_cache section is missing."""
        mock_config: dict[str, Any] = {"shopify": {}}
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        resolver = get_default_sku_resolver()

        assert resolver is None

    def test_returns_resolver_when_enabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_graphql_client: FakeGraphQLClient) -> None:
        """Returns CachedSKUResolver when enabled with valid config."""
        cache_path = tmp_path / "sku_cache.json"
        mock_config = {
            "shopify": {
                "sku_cache": {
                    "enabled": True,
                    "backend": "json",
                    "json_path": str(cache_path),
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        resolver = get_default_sku_resolver(graphql_client=fake_graphql_client)

        assert resolver is not None
        assert isinstance(resolver, CachedSKUResolver)

    def test_singleton_behavior(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns same instance on subsequent calls."""
        cache_path = tmp_path / "sku_cache.json"
        mock_config = {
            "shopify": {
                "sku_cache": {
                    "enabled": True,
                    "backend": "json",
                    "json_path": str(cache_path),
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        resolver1 = get_default_sku_resolver()
        resolver2 = get_default_sku_resolver()

        assert resolver1 is resolver2

    def test_handles_config_error_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when config raises an exception."""

        def raise_error() -> dict[str, Any]:
            raise RuntimeError("Config error")

        monkeypatch.setattr("lib_shopify_graphql.config.get_config", raise_error)

        resolver = get_default_sku_resolver()

        assert resolver is None

    def test_returns_none_when_cache_creation_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when cache creation fails (e.g., invalid backend)."""
        mock_config = {
            "shopify": {
                "sku_cache": {
                    "enabled": True,
                    "backend": "invalid_backend",
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        resolver = get_default_sku_resolver()

        assert resolver is None


@pytest.mark.os_agnostic
class TestGetDefaultTokenProvider:
    """get_default_token_provider returns provider based on config."""

    def test_returns_base_provider_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns base provider when token cache is disabled."""
        from lib_shopify_graphql.adapters import ShopifyTokenProvider

        mock_config = {"shopify": {"token_cache": {"enabled": False}}}
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        provider = get_default_token_provider()

        assert provider is not None
        assert isinstance(provider, ShopifyTokenProvider)

    def test_returns_base_provider_when_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns base provider when token_cache section is missing."""
        from lib_shopify_graphql.adapters import ShopifyTokenProvider

        mock_config: dict[str, Any] = {"shopify": {}}
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        provider = get_default_token_provider()

        assert provider is not None
        assert isinstance(provider, ShopifyTokenProvider)

    def test_returns_cached_provider_when_enabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns CachedTokenProvider when enabled with valid config."""
        cache_path = tmp_path / "token_cache.json"
        mock_config = {
            "shopify": {
                "token_cache": {
                    "enabled": True,
                    "backend": "json",
                    "json_path": str(cache_path),
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        provider = get_default_token_provider()

        assert provider is not None
        assert isinstance(provider, CachedTokenProvider)

    def test_singleton_behavior(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns same instance on subsequent calls."""
        cache_path = tmp_path / "token_cache.json"
        mock_config = {
            "shopify": {
                "token_cache": {
                    "enabled": True,
                    "backend": "json",
                    "json_path": str(cache_path),
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        provider1 = get_default_token_provider()
        provider2 = get_default_token_provider()

        assert provider1 is provider2

    def test_handles_config_error_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns base provider when config raises an exception."""
        from lib_shopify_graphql.adapters import ShopifyTokenProvider

        def raise_error() -> dict[str, Any]:
            raise RuntimeError("Config error")

        monkeypatch.setattr("lib_shopify_graphql.config.get_config", raise_error)

        provider = get_default_token_provider()

        assert provider is not None
        assert isinstance(provider, ShopifyTokenProvider)

    def test_uses_custom_refresh_margin(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Uses refresh_margin from config."""
        cache_path = tmp_path / "token_cache.json"
        mock_config = {
            "shopify": {
                "token_cache": {
                    "enabled": True,
                    "backend": "json",
                    "json_path": str(cache_path),
                    "refresh_margin": 600,
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        provider = get_default_token_provider()

        assert isinstance(provider, CachedTokenProvider)
        assert provider.refresh_margin == 600

    def test_returns_base_provider_when_cache_creation_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns base provider when cache creation fails (e.g., invalid backend)."""
        from lib_shopify_graphql.adapters import ShopifyTokenProvider

        mock_config = {
            "shopify": {
                "token_cache": {
                    "enabled": True,
                    "backend": "invalid_backend",
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        provider = get_default_token_provider()

        assert provider is not None
        assert isinstance(provider, ShopifyTokenProvider)


@pytest.mark.os_agnostic
class TestResetDefaultResolvers:
    """reset_default_resolvers clears singleton state."""

    def test_resets_sku_resolver(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reset allows new resolver to be created."""
        cache_path = tmp_path / "sku_cache.json"
        mock_config = {
            "shopify": {
                "sku_cache": {
                    "enabled": True,
                    "backend": "json",
                    "json_path": str(cache_path),
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        resolver1 = get_default_sku_resolver()
        reset_default_resolvers()
        resolver2 = get_default_sku_resolver()

        # After reset, new instance is created
        assert resolver1 is not resolver2

    def test_resets_token_provider(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reset allows new provider to be created."""
        cache_path = tmp_path / "token_cache.json"
        mock_config = {
            "shopify": {
                "token_cache": {
                    "enabled": True,
                    "backend": "json",
                    "json_path": str(cache_path),
                }
            }
        }
        monkeypatch.setattr("lib_shopify_graphql.config.get_config", lambda: mock_config)

        provider1 = get_default_token_provider()
        reset_default_resolvers()
        provider2 = get_default_token_provider()

        # After reset, new instance is created
        assert provider1 is not provider2
