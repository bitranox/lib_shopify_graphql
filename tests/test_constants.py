"""Tests for the constants module."""

from __future__ import annotations

import pytest


@pytest.mark.os_agnostic
class TestDefaultConstants:
    """Default constants have expected values."""

    def test_token_refresh_margin_is_five_minutes(self) -> None:
        """Token refresh margin defaults to 5 minutes."""
        from lib_shopify_graphql.adapters.constants import (
            DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS,
        )

        assert DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS == 300  # 5 minutes

    def test_token_expires_in_is_24_hours(self) -> None:
        """Token expiration defaults to 24 hours."""
        from lib_shopify_graphql.adapters.constants import (
            DEFAULT_TOKEN_EXPIRES_IN_SECONDS,
        )

        assert DEFAULT_TOKEN_EXPIRES_IN_SECONDS == 86400  # 24 hours

    def test_sku_cache_ttl_is_30_days(self) -> None:
        """SKU cache TTL defaults to 30 days."""
        from lib_shopify_graphql.adapters.constants import (
            DEFAULT_SKU_CACHE_TTL_SECONDS,
        )

        assert DEFAULT_SKU_CACHE_TTL_SECONDS == 2592000  # 30 days

    def test_lock_timeout_is_ten_seconds(self) -> None:
        """Lock timeout defaults to 10 seconds."""
        from lib_shopify_graphql.adapters.constants import (
            DEFAULT_LOCK_TIMEOUT_SECONDS,
        )

        assert DEFAULT_LOCK_TIMEOUT_SECONDS == 10.0

    def test_mysql_connect_timeout_is_ten_seconds(self) -> None:
        """MySQL connect timeout defaults to 10 seconds."""
        from lib_shopify_graphql.adapters.constants import (
            DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS,
        )

        assert DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS == 10

    def test_mysql_port_is_standard(self) -> None:
        """MySQL port defaults to standard 3306."""
        from lib_shopify_graphql.adapters.constants import DEFAULT_MYSQL_PORT

        assert DEFAULT_MYSQL_PORT == 3306

    def test_token_cache_table_name(self) -> None:
        """Token cache table has expected name."""
        from lib_shopify_graphql.adapters.constants import DEFAULT_TOKEN_CACHE_TABLE

        assert DEFAULT_TOKEN_CACHE_TABLE == "token_cache"

    def test_sku_cache_table_name(self) -> None:
        """SKU cache table has expected name."""
        from lib_shopify_graphql.adapters.constants import DEFAULT_SKU_CACHE_TABLE

        assert DEFAULT_SKU_CACHE_TABLE == "sku_cache"

    def test_default_currency_is_usd(self) -> None:
        """Default currency is USD."""
        from lib_shopify_graphql.adapters.constants import DEFAULT_CURRENCY_CODE

        assert DEFAULT_CURRENCY_CODE == "USD"


@pytest.mark.os_agnostic
class TestAdaptersUseConstants:
    """Adapters use constants for their defaults."""

    def test_json_cache_uses_lock_timeout_constant(self) -> None:
        """JsonFileCacheAdapter uses DEFAULT_LOCK_TIMEOUT_SECONDS."""
        from pathlib import Path

        from lib_shopify_graphql.adapters import JsonFileCacheAdapter
        from lib_shopify_graphql.adapters.constants import DEFAULT_LOCK_TIMEOUT_SECONDS

        cache = JsonFileCacheAdapter(Path("/tmp/test.json"))
        assert cache.lock_timeout == DEFAULT_LOCK_TIMEOUT_SECONDS

    def test_sku_resolver_uses_ttl_constant(self) -> None:
        """CachedSKUResolver uses DEFAULT_SKU_CACHE_TTL_SECONDS."""
        from unittest.mock import MagicMock

        from lib_shopify_graphql.adapters import CachedSKUResolver
        from lib_shopify_graphql.adapters.constants import DEFAULT_SKU_CACHE_TTL_SECONDS

        cache = MagicMock()
        graphql = MagicMock()
        resolver = CachedSKUResolver(cache, graphql)
        assert resolver.cache_ttl == DEFAULT_SKU_CACHE_TTL_SECONDS

    def test_cached_token_provider_uses_refresh_margin_constant(self) -> None:
        """CachedTokenProvider uses DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS."""
        from unittest.mock import MagicMock

        from lib_shopify_graphql.adapters import CachedTokenProvider
        from lib_shopify_graphql.adapters.constants import DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS

        cache = MagicMock()
        delegate = MagicMock()
        provider = CachedTokenProvider(cache, delegate)
        assert provider.refresh_margin == DEFAULT_TOKEN_REFRESH_MARGIN_SECONDS


@pytest.mark.os_agnostic
class TestCachePathFunctions:
    """Cache path functions work on all platforms."""

    def test_get_default_cache_dir_returns_path(self) -> None:
        """get_default_cache_dir returns a Path object."""
        from pathlib import Path

        from lib_shopify_graphql.adapters.constants import get_default_cache_dir

        result = get_default_cache_dir()
        assert isinstance(result, Path)
        assert "lib-shopify-graphql" in str(result)

    def test_get_default_token_cache_path(self) -> None:
        """get_default_token_cache_path returns token_cache.json path."""
        from lib_shopify_graphql.adapters.constants import get_default_token_cache_path

        result = get_default_token_cache_path()
        assert result.name == "token_cache.json"
        assert "lib-shopify-graphql" in str(result)

    def test_get_default_sku_cache_path(self) -> None:
        """get_default_sku_cache_path returns sku_cache.json path."""
        from lib_shopify_graphql.adapters.constants import get_default_sku_cache_path

        result = get_default_sku_cache_path()
        assert result.name == "sku_cache.json"
        assert "lib-shopify-graphql" in str(result)

    def test_get_default_cache_dir_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """macOS uses ~/Library/Caches."""
        import sys

        monkeypatch.setattr(sys, "platform", "darwin")
        # Need to reload to get fresh platform check
        import importlib

        from lib_shopify_graphql.adapters import constants

        importlib.reload(constants)

        result = constants.get_default_cache_dir()
        assert "Library" in str(result)
        assert "Caches" in str(result)
        assert "lib-shopify-graphql" in str(result)

    def test_get_default_cache_dir_windows_with_localappdata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows uses LOCALAPPDATA."""
        import sys

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\Test\\AppData\\Local")

        import importlib

        from lib_shopify_graphql.adapters import constants

        importlib.reload(constants)

        result = constants.get_default_cache_dir()
        assert "Local" in str(result) or "AppData" in str(result)
        assert "lib-shopify-graphql" in str(result)

    def test_get_default_cache_dir_windows_without_localappdata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows fallback when LOCALAPPDATA not set."""
        import sys

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("LOCALAPPDATA", raising=False)

        import importlib

        from lib_shopify_graphql.adapters import constants

        importlib.reload(constants)

        result = constants.get_default_cache_dir()
        assert "AppData" in str(result)
        assert "Local" in str(result)
        assert "lib-shopify-graphql" in str(result)

    def test_get_default_cache_dir_linux_with_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Linux uses XDG_CACHE_HOME when set."""
        import sys

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CACHE_HOME", "/custom/cache")

        import importlib

        from lib_shopify_graphql.adapters import constants

        importlib.reload(constants)

        result = constants.get_default_cache_dir()
        # Convert to posix path for cross-platform comparison
        assert result.as_posix() == "/custom/cache/lib-shopify-graphql"

    def test_get_default_cache_dir_linux_without_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Linux uses ~/.cache when XDG_CACHE_HOME not set."""
        import sys

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

        import importlib

        from lib_shopify_graphql.adapters import constants

        importlib.reload(constants)

        result = constants.get_default_cache_dir()
        posix_path = result.as_posix()
        assert ".cache" in posix_path
        assert "lib-shopify-graphql" in posix_path
