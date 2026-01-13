"""Cache adapter tests: verifying file-based cache behavior.

Tests for the JSON file cache adapter covering:
- Basic CRUD operations (get, set, delete, clear)
- TTL-based expiration
- File locking behavior
- Error handling for corrupted files
- Cleanup of expired entries
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from lib_shopify_graphql.adapters.cache_json import JsonFileCacheAdapter

if TYPE_CHECKING:
    pass


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def tmp_cache_path(tmp_path: Path) -> Path:
    """Provide a temporary path for cache file."""
    return tmp_path / "test_cache.json"


@pytest.fixture
def cache(tmp_cache_path: Path) -> JsonFileCacheAdapter:
    """Provide a fresh JsonFileCacheAdapter instance."""
    return JsonFileCacheAdapter(tmp_cache_path)


@pytest.fixture
def populated_cache(cache: JsonFileCacheAdapter) -> JsonFileCacheAdapter:
    """Provide a cache with some pre-populated entries."""
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.set("key3", "value3")
    return cache


# =============================================================================
# Basic CRUD Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestJsonFileCacheGet:
    """JsonFileCacheAdapter.get retrieves cached values."""

    def test_returns_none_for_missing_key(self, cache: JsonFileCacheAdapter) -> None:
        """Missing key returns None."""
        result = cache.get("nonexistent")

        assert result is None

    def test_returns_cached_value(self, cache: JsonFileCacheAdapter) -> None:
        """Existing key returns its value."""
        cache.set("mykey", "myvalue")

        result = cache.get("mykey")

        assert result == "myvalue"

    def test_returns_none_for_empty_cache_file(self, tmp_cache_path: Path) -> None:
        """Empty cache returns None for any key."""
        cache = JsonFileCacheAdapter(tmp_cache_path)

        result = cache.get("anykey")

        assert result is None


@pytest.mark.os_agnostic
class TestJsonFileCacheSet:
    """JsonFileCacheAdapter.set stores values."""

    def test_creates_cache_file(self, cache: JsonFileCacheAdapter, tmp_cache_path: Path) -> None:
        """Set creates the cache file if it doesn't exist."""
        cache.set("key", "value")

        assert tmp_cache_path.exists()

    def test_stores_value_in_file(self, cache: JsonFileCacheAdapter, tmp_cache_path: Path) -> None:
        """Set writes value to the cache file."""
        cache.set("key", "value")

        data = json.loads(tmp_cache_path.read_text())
        assert data["key"]["value"] == "value"

    def test_overwrites_existing_value(self, cache: JsonFileCacheAdapter) -> None:
        """Set overwrites existing value for same key."""
        cache.set("key", "original")
        cache.set("key", "updated")

        result = cache.get("key")
        assert result == "updated"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Set creates parent directories if needed."""
        nested_path = tmp_path / "nested" / "dir" / "cache.json"
        cache = JsonFileCacheAdapter(nested_path)

        cache.set("key", "value")

        assert nested_path.exists()


@pytest.mark.os_agnostic
class TestJsonFileCacheDelete:
    """JsonFileCacheAdapter.delete removes entries."""

    def test_removes_existing_key(self, populated_cache: JsonFileCacheAdapter) -> None:
        """Delete removes an existing key."""
        populated_cache.delete("key1")

        result = populated_cache.get("key1")
        assert result is None

    def test_preserves_other_keys(self, populated_cache: JsonFileCacheAdapter) -> None:
        """Delete only removes the specified key."""
        populated_cache.delete("key1")

        assert populated_cache.get("key2") == "value2"
        assert populated_cache.get("key3") == "value3"

    def test_succeeds_for_missing_key(self, cache: JsonFileCacheAdapter) -> None:
        """Delete on missing key doesn't raise error."""
        # Should not raise
        cache.delete("nonexistent")


@pytest.mark.os_agnostic
class TestJsonFileCacheClear:
    """JsonFileCacheAdapter.clear removes all entries."""

    def test_removes_all_entries(self, populated_cache: JsonFileCacheAdapter) -> None:
        """Clear removes all cached entries."""
        populated_cache.clear()

        assert populated_cache.get("key1") is None
        assert populated_cache.get("key2") is None
        assert populated_cache.get("key3") is None

    def test_leaves_empty_cache_file(self, populated_cache: JsonFileCacheAdapter, tmp_cache_path: Path) -> None:
        """Clear leaves an empty JSON object in the file."""
        # Get path from the cache
        cache_path = populated_cache.cache_path
        populated_cache.clear()

        data = json.loads(cache_path.read_text())
        assert data == {}


# =============================================================================
# TTL Expiration Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestJsonFileCacheTTL:
    """JsonFileCacheAdapter handles TTL-based expiration."""

    def test_stores_expiration_with_ttl(self, cache: JsonFileCacheAdapter, tmp_cache_path: Path) -> None:
        """Set with TTL stores expiration timestamp."""
        cache.set("key", "value", ttl=3600)

        data = json.loads(tmp_cache_path.read_text())
        assert data["key"]["expires"] is not None
        assert data["key"]["expires"] > time.time()

    def test_no_expiration_without_ttl(self, cache: JsonFileCacheAdapter, tmp_cache_path: Path) -> None:
        """Set without TTL stores None for expires."""
        cache.set("key", "value")

        data = json.loads(tmp_cache_path.read_text())
        assert data["key"]["expires"] is None

    def test_returns_none_for_expired_entry(self, cache: JsonFileCacheAdapter) -> None:
        """Get returns None for expired entries."""
        # Set entry with very short TTL
        cache.set("key", "value", ttl=1)

        # Mock time.time to return future time (simulating expiration)
        original_entry_time = time.time()
        with patch("lib_shopify_graphql.adapters.cache_json.time") as mock_time:
            # Make time appear 2 seconds later (past TTL)
            mock_time.time.return_value = original_entry_time + 2
            result = cache.get("key")

        assert result is None

    def test_returns_value_for_unexpired_entry(self, cache: JsonFileCacheAdapter) -> None:
        """Get returns value for entries that haven't expired."""
        cache.set("key", "value", ttl=3600)

        result = cache.get("key")
        assert result == "value"

    def test_removes_expired_entry_on_access(self, cache: JsonFileCacheAdapter, tmp_cache_path: Path) -> None:
        """Get removes expired entries from the cache file."""
        cache.set("key", "value", ttl=1)
        original_entry_time = time.time()

        # Mock time to simulate expiration
        with patch("lib_shopify_graphql.adapters.cache_json.time") as mock_time:
            mock_time.time.return_value = original_entry_time + 2
            cache.get("key")

        # Verify it was removed from the file
        data = json.loads(tmp_cache_path.read_text())
        assert "key" not in data


@pytest.mark.os_agnostic
class TestJsonFileCacheCleanup:
    """JsonFileCacheAdapter.cleanup_expired removes stale entries."""

    def test_removes_expired_entries(self, cache: JsonFileCacheAdapter) -> None:
        """cleanup_expired removes all expired entries."""
        cache.set("expired1", "value1", ttl=1)
        cache.set("expired2", "value2", ttl=1)
        cache.set("valid", "value3", ttl=3600)
        original_time = time.time()

        # Mock time to simulate expiration of short TTL entries
        with patch("lib_shopify_graphql.adapters.cache_json.time") as mock_time:
            mock_time.time.return_value = original_time + 2
            removed = cache.cleanup_expired()

        assert removed == 2
        assert cache.get("valid") == "value3"
        assert cache.get("expired1") is None
        assert cache.get("expired2") is None

    def test_returns_zero_for_no_expired(self, cache: JsonFileCacheAdapter) -> None:
        """cleanup_expired returns 0 when nothing is expired."""
        cache.set("key1", "value1", ttl=3600)
        cache.set("key2", "value2")  # No TTL

        removed = cache.cleanup_expired()

        assert removed == 0

    def test_returns_zero_for_empty_cache(self, cache: JsonFileCacheAdapter) -> None:
        """cleanup_expired returns 0 for empty cache."""
        removed = cache.cleanup_expired()

        assert removed == 0


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestJsonFileCacheCorruptedFile:
    """JsonFileCacheAdapter handles corrupted cache files."""

    def test_get_returns_none_for_invalid_json(self, tmp_cache_path: Path) -> None:
        """Get returns None when cache file contains invalid JSON."""
        tmp_cache_path.write_text("not valid json {{{")
        cache = JsonFileCacheAdapter(tmp_cache_path)

        result = cache.get("anykey")

        assert result is None

    def test_set_overwrites_invalid_json(self, tmp_cache_path: Path) -> None:
        """Set overwrites corrupted cache file with valid data."""
        tmp_cache_path.write_text("not valid json {{{")
        cache = JsonFileCacheAdapter(tmp_cache_path)

        cache.set("key", "value")

        result = cache.get("key")
        assert result == "value"


@pytest.mark.os_agnostic
class TestJsonFileCacheLockTimeout:
    """JsonFileCacheAdapter handles lock timeout gracefully."""

    def test_get_returns_none_on_exception(self, tmp_cache_path: Path) -> None:
        """Get returns None when an exception occurs during file read."""
        cache = JsonFileCacheAdapter(tmp_cache_path)
        cache.set("key", "value")

        # Simulate file read error by making file unreadable
        with patch.object(cache, "_read_cache", side_effect=Exception("Read error")):
            result = cache.get("key")

        assert result is None

    def test_set_handles_write_exception(self, tmp_cache_path: Path) -> None:
        """Set handles exceptions gracefully."""
        cache = JsonFileCacheAdapter(tmp_cache_path)

        # Simulate write error
        with patch.object(cache, "_write_cache", side_effect=Exception("Write error")):
            # Should not raise
            cache.set("key", "value")

        # Verify no value was written
        result = cache.get("key")
        assert result is None


# =============================================================================
# Initialization Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestJsonFileCacheInitialization:
    """JsonFileCacheAdapter initializes correctly."""

    def test_creates_lock_path_from_cache_path(self, tmp_cache_path: Path) -> None:
        """Lock file path is derived from cache path."""
        cache = JsonFileCacheAdapter(tmp_cache_path)

        assert cache.lock_path == tmp_cache_path.with_suffix(".lock")

    def test_accepts_custom_lock_timeout(self, tmp_cache_path: Path) -> None:
        """Custom lock timeout is stored."""
        cache = JsonFileCacheAdapter(tmp_cache_path, lock_timeout=30.0)

        assert cache.lock_timeout == 30.0

    def test_defaults_lock_timeout_to_ten_seconds(self, tmp_cache_path: Path) -> None:
        """Lock timeout defaults to 10 seconds."""
        cache = JsonFileCacheAdapter(tmp_cache_path)

        assert cache.lock_timeout == 10.0

    def test_accepts_custom_max_retries(self, tmp_cache_path: Path) -> None:
        """Custom max_retries is stored."""
        cache = JsonFileCacheAdapter(tmp_cache_path, max_retries=5)

        assert cache.max_retries == 5

    def test_defaults_max_retries_to_three(self, tmp_cache_path: Path) -> None:
        """max_retries defaults to 3."""
        cache = JsonFileCacheAdapter(tmp_cache_path)

        assert cache.max_retries == 3


# =============================================================================
# Cache Corruption Backup Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestJsonFileCacheCorruptionBackup:
    """JsonFileCacheAdapter backs up corrupted files."""

    def test_corrupted_file_is_backed_up(self, tmp_cache_path: Path) -> None:
        """Corrupted cache file is renamed with .corrupted extension."""
        tmp_cache_path.write_text("not valid json {{{")
        cache = JsonFileCacheAdapter(tmp_cache_path)

        # Access the cache to trigger corruption detection
        cache.get("anykey")

        backup_path = tmp_cache_path.with_suffix(".corrupted")
        assert backup_path.exists()
        assert backup_path.read_text() == "not valid json {{{"

    def test_original_file_is_removed_after_backup(self, tmp_cache_path: Path) -> None:
        """Original corrupted file is removed after backup."""
        tmp_cache_path.write_text("invalid json")
        cache = JsonFileCacheAdapter(tmp_cache_path)

        cache.get("anykey")

        # Original file should not exist anymore (was renamed)
        assert not tmp_cache_path.exists()


# =============================================================================
# MySQL Connection String Parsing Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestMySQLConnectionStringParsing:
    """MySQL connection string parser handles various formats."""

    def test_standard_connection_string(self) -> None:
        """Parses standard mysql://user:pass@host:port/db format."""
        from lib_shopify_graphql.adapters.cache_mysql import parse_mysql_connection_string

        result = parse_mysql_connection_string("mysql://myuser:mypass@localhost:3306/mydb")

        assert result.host == "localhost"
        assert result.port == 3306
        assert result.user == "myuser"
        assert result.password == "mypass"
        assert result.database == "mydb"

    def test_default_port(self) -> None:
        """Uses default port 3306 when not specified."""
        from lib_shopify_graphql.adapters.cache_mysql import parse_mysql_connection_string

        result = parse_mysql_connection_string("mysql://user:pass@host/db")

        assert result.port == 3306

    def test_url_encoded_password_with_at_symbol(self) -> None:
        """Handles URL-encoded @ symbol in password."""
        from lib_shopify_graphql.adapters.cache_mysql import parse_mysql_connection_string

        # Password is "p@ssword" URL-encoded as "p%40ssword"
        result = parse_mysql_connection_string("mysql://user:p%40ssword@host/db")

        assert result.password == "p@ssword"
        assert result.host == "host"

    def test_url_encoded_special_characters_in_password(self) -> None:
        """Handles various URL-encoded special characters in password."""
        from lib_shopify_graphql.adapters.cache_mysql import parse_mysql_connection_string

        # Password is "p@ss:word/test" URL-encoded
        result = parse_mysql_connection_string("mysql://user:p%40ss%3Aword%2Ftest@host/db")

        assert result.password == "p@ss:word/test"

    def test_no_password(self) -> None:
        """Handles connection string without password."""
        from lib_shopify_graphql.adapters.cache_mysql import parse_mysql_connection_string

        result = parse_mysql_connection_string("mysql://user@host/db")

        assert result.user == "user"
        assert result.password == ""

    def test_invalid_scheme_raises_error(self) -> None:
        """Non-mysql scheme raises ValueError."""
        from lib_shopify_graphql.adapters.cache_mysql import parse_mysql_connection_string

        with pytest.raises(ValueError, match="expected 'mysql'"):
            parse_mysql_connection_string("postgresql://user:pass@host/db")

    def test_missing_hostname_raises_error(self) -> None:
        """Missing hostname raises ValueError."""
        from lib_shopify_graphql.adapters.cache_mysql import parse_mysql_connection_string

        with pytest.raises(ValueError, match="missing hostname"):
            parse_mysql_connection_string("mysql:///db")

    def test_missing_database_raises_error(self) -> None:
        """Missing database name raises ValueError."""
        from lib_shopify_graphql.adapters.cache_mysql import parse_mysql_connection_string

        with pytest.raises(ValueError, match="missing database"):
            parse_mysql_connection_string("mysql://user:pass@host/")


# =============================================================================
# Lock Timeout Retry Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestJsonFileCacheLockTimeoutRetries:
    """JsonFileCacheAdapter retries on lock timeout."""

    def test_get_returns_none_after_max_retries(self, tmp_cache_path: Path) -> None:
        """Get returns None when all retries exhausted."""
        from filelock import Timeout

        cache = JsonFileCacheAdapter(tmp_cache_path, max_retries=2)
        # Write directly to file so we don't need lock for setup
        tmp_cache_path.write_text('{"key": {"value": "test", "expires": null}}')

        # Count retries
        retry_count = [0]

        def always_timeout() -> None:
            retry_count[0] += 1
            raise Timeout(str(cache.lock_path))

        with patch.object(cache._lock, "acquire", side_effect=always_timeout):
            with patch("lib_shopify_graphql.adapters.cache_json.time.sleep"):
                result = cache.get("key")

        assert result is None
        assert retry_count[0] == 2  # max_retries attempts

    def test_set_gives_up_after_max_retries(self, tmp_cache_path: Path) -> None:
        """Set gives up after max retries without raising."""
        from filelock import Timeout

        cache = JsonFileCacheAdapter(tmp_cache_path, max_retries=2)

        retry_count = [0]

        def always_timeout() -> None:
            retry_count[0] += 1
            raise Timeout(str(cache.lock_path))

        with patch.object(cache._lock, "acquire", side_effect=always_timeout):
            with patch("lib_shopify_graphql.adapters.cache_json.time.sleep"):
                # Should not raise
                cache.set("key", "value")

        # Retries should have been exhausted
        assert retry_count[0] == 2

    def test_delete_handles_timeout(self, tmp_cache_path: Path) -> None:
        """Delete handles lock timeout gracefully."""
        from filelock import Timeout

        cache = JsonFileCacheAdapter(tmp_cache_path)
        # Write directly to file
        tmp_cache_path.write_text('{"key": {"value": "test", "expires": null}}')

        timeout_raised = [False]

        def raise_once() -> None:
            timeout_raised[0] = True
            raise Timeout(str(cache.lock_path))

        with patch.object(cache._lock, "acquire", side_effect=raise_once):
            # Should not raise
            cache.delete("key")

        assert timeout_raised[0]

    def test_clear_handles_timeout(self, tmp_cache_path: Path) -> None:
        """Clear handles lock timeout gracefully."""
        from filelock import Timeout

        cache = JsonFileCacheAdapter(tmp_cache_path)
        # Write directly to file
        tmp_cache_path.write_text('{"key1": {"value": "v1", "expires": null}}')

        timeout_raised = [False]

        def raise_once() -> None:
            timeout_raised[0] = True
            raise Timeout(str(cache.lock_path))

        with patch.object(cache._lock, "acquire", side_effect=raise_once):
            # Should not raise
            cache.clear()

        assert timeout_raised[0]

    def test_get_retries_with_backoff(self, tmp_cache_path: Path) -> None:
        """Get uses exponential backoff between retries."""
        from filelock import Timeout

        cache = JsonFileCacheAdapter(tmp_cache_path, max_retries=3)
        tmp_cache_path.write_text('{"key": {"value": "test", "expires": null}}')

        sleep_times: list[float] = []

        def always_timeout() -> None:
            raise Timeout(str(cache.lock_path))

        def track_sleep(seconds: float) -> None:
            sleep_times.append(seconds)

        with patch.object(cache._lock, "acquire", side_effect=always_timeout):
            with patch("lib_shopify_graphql.adapters.cache_json.time.sleep", side_effect=track_sleep):
                cache.get("key")

        # Should have slept twice (not on final attempt)
        assert len(sleep_times) == 2
        # Exponential backoff: 0.1s, 0.2s
        assert sleep_times[0] == pytest.approx(0.1)  # type: ignore[comparison-overlap]
        assert sleep_times[1] == pytest.approx(0.2)  # type: ignore[comparison-overlap]

    def test_set_retries_with_backoff(self, tmp_cache_path: Path) -> None:
        """Set uses exponential backoff between retries."""
        from filelock import Timeout

        cache = JsonFileCacheAdapter(tmp_cache_path, max_retries=3)

        sleep_times: list[float] = []

        def always_timeout() -> None:
            raise Timeout(str(cache.lock_path))

        def track_sleep(seconds: float) -> None:
            sleep_times.append(seconds)

        with patch.object(cache._lock, "acquire", side_effect=always_timeout):
            with patch("lib_shopify_graphql.adapters.cache_json.time.sleep", side_effect=track_sleep):
                cache.set("key", "value")

        # Should have slept twice (not on final attempt)
        assert len(sleep_times) == 2


# =============================================================================
# Error Handling Edge Cases
# =============================================================================


@pytest.mark.os_agnostic
class TestJsonFileCacheErrorEdgeCases:
    """JsonFileCacheAdapter handles edge case errors."""

    def test_backup_failure_is_handled(self, tmp_cache_path: Path) -> None:
        """Backup of corrupted file handles OSError."""
        tmp_cache_path.write_text("invalid json {{{")
        cache = JsonFileCacheAdapter(tmp_cache_path)

        # Mock rename to fail
        with patch("pathlib.Path.rename", side_effect=OSError("Permission denied")):
            # Should not raise, just log warning
            result = cache.get("anykey")

        assert result is None

    def test_read_oserror_is_handled(self, tmp_cache_path: Path) -> None:
        """OSError during file read is handled."""
        cache = JsonFileCacheAdapter(tmp_cache_path)
        tmp_cache_path.write_text('{"key": {"value": "test", "expires": null}}')

        with patch("pathlib.Path.read_bytes", side_effect=OSError("I/O error")):
            result = cache.get("key")

        assert result is None

    def test_chmod_failure_is_handled(self, tmp_cache_path: Path) -> None:
        """Chmod failure is logged but doesn't raise."""
        cache = JsonFileCacheAdapter(tmp_cache_path)

        with patch("os.chmod", side_effect=OSError("Operation not permitted")):
            # Should not raise
            cache.set("key", "value")

        # Value should still be written
        result = cache.get("key")
        assert result == "value"

    def test_cleanup_expired_handles_exception(self, tmp_cache_path: Path) -> None:
        """cleanup_expired returns 0 on exception."""
        cache = JsonFileCacheAdapter(tmp_cache_path)
        cache.set("key", "value", ttl=1)

        with patch.object(cache, "_read_cache", side_effect=Exception("Read error")):
            result = cache.cleanup_expired()

        assert result == 0

    def test_delete_handles_general_exception(self, tmp_cache_path: Path) -> None:
        """Delete handles general exception gracefully."""
        cache = JsonFileCacheAdapter(tmp_cache_path)
        cache.set("key", "value")

        with patch.object(cache, "_read_cache", side_effect=Exception("Unexpected error")):
            # Should not raise
            cache.delete("key")

    def test_clear_handles_general_exception(self, tmp_cache_path: Path) -> None:
        """Clear handles general exception gracefully."""
        cache = JsonFileCacheAdapter(tmp_cache_path)
        cache.set("key", "value")

        with patch.object(cache, "_write_cache", side_effect=Exception("Write failed")):
            # Should not raise
            cache.clear()


# =============================================================================
# Keys() Method Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestJsonFileCacheKeys:
    """JsonFileCacheAdapter.keys lists cache keys."""

    def test_returns_empty_list_for_empty_cache(self, cache: JsonFileCacheAdapter) -> None:
        """Empty cache returns empty list."""
        result = cache.keys()
        assert result == []

    def test_returns_all_keys(self, populated_cache: JsonFileCacheAdapter) -> None:
        """Returns all keys from populated cache."""
        result = populated_cache.keys()
        assert sorted(result) == ["key1", "key2", "key3"]

    def test_filters_by_prefix(self, cache: JsonFileCacheAdapter) -> None:
        """Returns only keys matching prefix."""
        cache.set("sku:shop1:ABC", "value1")
        cache.set("sku:shop1:DEF", "value2")
        cache.set("sku:shop2:ABC", "value3")
        cache.set("token:shop1", "value4")

        result = cache.keys(prefix="sku:shop1:")
        assert sorted(result) == ["sku:shop1:ABC", "sku:shop1:DEF"]

    def test_excludes_expired_entries(self, cache: JsonFileCacheAdapter) -> None:
        """Excludes expired entries from keys list."""
        cache.set("valid", "value1", ttl=3600)
        cache.set("expired", "value2", ttl=1)
        original_time = time.time()

        # Mock time to expire the short TTL entry
        with patch("lib_shopify_graphql.adapters.cache_json.time") as mock_time:
            mock_time.time.return_value = original_time + 2
            result = cache.keys()

        assert result == ["valid"]

    def test_handles_timeout_gracefully(self, tmp_cache_path: Path) -> None:
        """Returns empty list on lock timeout."""
        from filelock import Timeout

        cache = JsonFileCacheAdapter(tmp_cache_path, max_retries=2)
        cache.set("key", "value")

        def always_timeout() -> None:
            raise Timeout(str(cache.lock_path))

        with patch.object(cache._lock, "acquire", side_effect=always_timeout):
            with patch("lib_shopify_graphql.adapters.cache_json.time.sleep"):
                result = cache.keys()

        assert result == []

    def test_handles_exception_gracefully(self, cache: JsonFileCacheAdapter) -> None:
        """Returns empty list on exception."""
        cache.set("key", "value")

        with patch.object(cache, "_read_cache", side_effect=Exception("Read error")):
            result = cache.keys()

        assert result == []


# =============================================================================
# CacheCheckResult and CacheMismatch Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheCheckResult:
    """CacheCheckResult dataclass behavior."""

    def test_is_consistent_when_no_issues(self) -> None:
        """is_consistent returns True with no issues."""
        from lib_shopify_graphql import CacheCheckResult

        result = CacheCheckResult(
            total_cached=10,
            total_shopify=10,
            valid=10,
            stale=(),
            missing=(),
            mismatched=(),
        )

        assert result.is_consistent is True

    def test_is_not_consistent_with_stale(self) -> None:
        """is_consistent returns False with stale entries."""
        from lib_shopify_graphql import CacheCheckResult

        result = CacheCheckResult(
            total_cached=10,
            total_shopify=8,
            valid=8,
            stale=("OLD-SKU",),
            missing=(),
            mismatched=(),
        )

        assert result.is_consistent is False

    def test_is_not_consistent_with_missing(self) -> None:
        """is_consistent returns False with missing entries."""
        from lib_shopify_graphql import CacheCheckResult

        result = CacheCheckResult(
            total_cached=8,
            total_shopify=10,
            valid=8,
            stale=(),
            missing=("NEW-SKU",),
            mismatched=(),
        )

        assert result.is_consistent is False

    def test_is_not_consistent_with_mismatched(self) -> None:
        """is_consistent returns False with mismatched entries."""
        from lib_shopify_graphql import CacheMismatch, CacheCheckResult

        result = CacheCheckResult(
            total_cached=10,
            total_shopify=10,
            valid=9,
            stale=(),
            missing=(),
            mismatched=(
                CacheMismatch(
                    sku="SKU-1",
                    cached_variant_gid="gid://old/1",
                    actual_variant_gid="gid://new/1",
                    cached_product_gid="gid://product/1",
                    actual_product_gid="gid://product/1",
                ),
            ),
        )

        assert result.is_consistent is False


@pytest.mark.os_agnostic
class TestCacheMismatch:
    """CacheMismatch dataclass behavior."""

    def test_stores_all_fields(self) -> None:
        """CacheMismatch stores all provided fields."""
        from lib_shopify_graphql import CacheMismatch

        mismatch = CacheMismatch(
            sku="SKU-123",
            cached_variant_gid="gid://cached/variant",
            actual_variant_gid="gid://actual/variant",
            cached_product_gid="gid://cached/product",
            actual_product_gid="gid://actual/product",
        )

        assert mismatch.sku == "SKU-123"
        assert mismatch.cached_variant_gid == "gid://cached/variant"
        assert mismatch.actual_variant_gid == "gid://actual/variant"
        assert mismatch.cached_product_gid == "gid://cached/product"
        assert mismatch.actual_product_gid == "gid://actual/product"

    def test_is_frozen(self) -> None:
        """CacheMismatch is immutable."""
        from lib_shopify_graphql import CacheMismatch

        mismatch = CacheMismatch(
            sku="SKU-123",
            cached_variant_gid="gid://cached",
            actual_variant_gid="gid://actual",
            cached_product_gid="gid://product/cached",
            actual_product_gid="gid://product/actual",
        )

        with pytest.raises(AttributeError):
            mismatch.sku = "NEW-SKU"  # type: ignore[misc]
