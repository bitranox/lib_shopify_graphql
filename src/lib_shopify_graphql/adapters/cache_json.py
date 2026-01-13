"""JSON file cache adapter with file locking.

This module provides a file-based cache implementation suitable for
network shares where multiple processes may access the cache concurrently.

Classes:
    - :class:`JsonFileCacheAdapter`: Thread-safe JSON file cache.

Note:
    File locking may not work reliably on NFS/SMB network shares.
    For distributed environments, consider using MySQLCacheAdapter instead.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson
from filelock import FileLock, Timeout

from .constants import DEFAULT_CACHE_RETRY_COUNT, DEFAULT_LOCK_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheEntry:
    """A single cache entry with value and optional expiration.

    Attributes:
        value: The cached string value.
        expires: Unix timestamp when entry expires, or None for no expiration.
    """

    value: str
    expires: float | None = None

    def is_expired(self) -> bool:
        """Check if the cache entry has expired.

        Returns:
            True if entry has expired, False otherwise.
        """
        return self.expires is not None and self.expires < time.time()

    def to_dict(self) -> dict[str, str | float | None]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation for JSON storage.
        """
        return {"value": self.value, "expires": self.expires}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Create CacheEntry from dictionary.

        Args:
            data: Dictionary with 'value' and optional 'expires' keys.

        Returns:
            CacheEntry instance.
        """
        return cls(
            value=data.get("value", ""),
            expires=data.get("expires"),
        )


class JsonFileCacheAdapter:
    """File-based cache with file locking for network share safety.

    Uses filelock to ensure thread-safe and process-safe access to
    the cache file. Suitable for use on network shares where multiple
    processes may access the same cache file.

    Implements :class:`~lib_shopify_graphql.application.ports.CachePort`.

    Attributes:
        cache_path: Path to the JSON cache file.
        lock_path: Path to the lock file (auto-generated).
        lock_timeout: Maximum time to wait for lock acquisition.

    Example:
        >>> from pathlib import Path
        >>> cache = JsonFileCacheAdapter(Path("/tmp/sku_cache.json"))
        >>> cache.set("sku:myshop:ABC-123", "gid://shopify/ProductVariant/123")
        >>> cache.get("sku:myshop:ABC-123")
        'gid://shopify/ProductVariant/123'
    """

    def __init__(
        self,
        cache_path: Path,
        lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_CACHE_RETRY_COUNT,
    ) -> None:
        """Initialize the JSON file cache.

        Args:
            cache_path: Path to the JSON cache file. Created if not exists.
            lock_timeout: Maximum seconds to wait for lock acquisition.
                Defaults to DEFAULT_LOCK_TIMEOUT_SECONDS.
            max_retries: Maximum number of retries on lock timeout.
                Defaults to DEFAULT_CACHE_RETRY_COUNT.
        """
        self.cache_path = cache_path
        self.lock_path = cache_path.with_suffix(".lock")
        self.lock_timeout = lock_timeout
        self.max_retries = max_retries
        self._lock = FileLock(self.lock_path, timeout=lock_timeout)

    def get(self, key: str) -> str | None:
        """Get a value from the cache.

        Retries with exponential backoff if lock cannot be acquired.

        Args:
            key: Cache key to look up.

        Returns:
            The cached value, or None if not found or expired.
        """
        for attempt in range(self.max_retries):
            try:
                with self._lock:
                    cache_data = self._read_cache()
                    entry = cache_data.get(key)
                    if entry is None:
                        return None
                    if entry.is_expired():
                        # Entry expired, remove it
                        del cache_data[key]
                        self._write_cache(cache_data)
                        return None
                    return entry.value
            except Timeout:
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s, ...
                    backoff = 0.1 * (2**attempt)
                    logger.debug(
                        "Cache lock timeout, retrying",
                        extra={"key": key, "attempt": attempt + 1, "backoff": backoff},
                    )
                    time.sleep(backoff)
                else:
                    logger.warning(f"Cache lock timeout after {self.max_retries} retries for key '{key}'")
                    return None
            except Exception as exc:
                logger.warning(f"Cache read error for key '{key}': {exc}")
                return None
        return None

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Store a value in the cache.

        Retries with exponential backoff if lock cannot be acquired.

        Args:
            key: Cache key.
            value: Value to store.
            ttl: Time-to-live in seconds. None for no expiration.
        """
        for attempt in range(self.max_retries):
            try:
                with self._lock:
                    cache_data = self._read_cache()
                    cache_data[key] = CacheEntry(
                        value=value,
                        expires=time.time() + ttl if ttl else None,
                    )
                    self._write_cache(cache_data)
                    return
            except Timeout:
                if attempt < self.max_retries - 1:
                    backoff = 0.1 * (2**attempt)
                    logger.debug(
                        "Cache lock timeout on set, retrying",
                        extra={"key": key, "attempt": attempt + 1, "backoff": backoff},
                    )
                    time.sleep(backoff)
                else:
                    logger.warning(f"Cache lock timeout on set after {self.max_retries} retries for key '{key}'")
            except Exception as exc:
                logger.warning(f"Cache write error for key '{key}': {exc}")
                return

    def delete(self, key: str) -> None:
        """Remove a key from the cache.

        Args:
            key: Cache key to remove.
        """
        try:
            with self._lock:
                cache_data = self._read_cache()
                if key in cache_data:
                    del cache_data[key]
                    self._write_cache(cache_data)
        except Timeout:
            logger.warning(f"Cache lock timeout on delete for key '{key}'")
        except Exception as exc:
            logger.warning(f"Cache delete error for key '{key}': {exc}")

    def clear(self) -> None:
        """Clear all cached entries."""
        try:
            with self._lock:
                self._write_cache({})
        except Timeout:
            logger.warning("Cache lock timeout on clear")
        except Exception as exc:
            logger.warning(f"Cache clear error: {exc}")

    def _read_cache(self) -> dict[str, CacheEntry]:
        """Read and parse the cache file.

        Returns:
            Cache data as dictionary of CacheEntry objects, or empty dict if file doesn't exist.

        Note:
            If the cache file is corrupted (invalid JSON), it is logged,
            backed up with .corrupted extension, and the cache is reset.
        """
        if not self.cache_path.exists():
            return {}
        try:
            raw_data = orjson.loads(self.cache_path.read_bytes())
            return {key: CacheEntry.from_dict(entry) for key, entry in raw_data.items()}
        except orjson.JSONDecodeError as exc:
            logger.error(f"Cache file corrupted at '{self.cache_path}', resetting cache: {exc}")
            # Backup corrupted file for debugging
            backup_path = self.cache_path.with_suffix(".corrupted")
            try:
                self.cache_path.rename(backup_path)
                logger.info(f"Corrupted cache backed up to '{backup_path}'")
            except OSError as backup_exc:
                logger.warning(f"Failed to backup corrupted cache: {backup_exc}")
            return {}
        except OSError as exc:
            logger.warning(f"Cache read error for '{self.cache_path}': {exc}")
            return {}

    def _write_cache(self, cache_data: dict[str, CacheEntry]) -> None:
        """Write cache data to file with restrictive permissions.

        Creates parent directories with mode 0o700 (owner rwx only) and
        writes the cache file with mode 0o600 (owner rw only) to prevent
        unauthorized access to cached tokens or sensitive data.

        Args:
            cache_data: Cache data to write (dictionary of CacheEntry objects).
        """
        import os
        import stat

        # Create parent directory with restrictive permissions (owner only)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        raw_data = {key: entry.to_dict() for key, entry in cache_data.items()}
        self.cache_path.write_bytes(orjson.dumps(raw_data, option=orjson.OPT_INDENT_2))

        # Set file permissions to owner read-write only (0o600)
        # This prevents other users from reading cached tokens
        try:
            os.chmod(self.cache_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # On Windows or restricted filesystems, chmod may fail - log but continue
            logger.debug("Could not set restrictive file permissions on cache file")

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed.
        """
        try:
            with self._lock:
                cache_data = self._read_cache()
                expired_keys = [key for key, entry in cache_data.items() if entry.is_expired()]
                for key in expired_keys:
                    del cache_data[key]
                if expired_keys:
                    self._write_cache(cache_data)
                return len(expired_keys)
        except Exception as exc:
            logger.warning(f"Cache cleanup error: {exc}")
            return 0

    def keys(self, prefix: str | None = None) -> list[str]:
        """List all cache keys, optionally filtered by prefix.

        Retries with exponential backoff if lock cannot be acquired.

        Args:
            prefix: If provided, only return keys starting with this prefix.

        Returns:
            List of cache keys (excluding expired entries).
        """
        for attempt in range(self.max_retries):
            try:
                with self._lock:
                    cache_data = self._read_cache()
                    # Filter out expired entries
                    valid_keys = [key for key, entry in cache_data.items() if not entry.is_expired()]
                    if prefix:
                        return [k for k in valid_keys if k.startswith(prefix)]
                    return valid_keys
            except Timeout:
                if attempt < self.max_retries - 1:
                    backoff = 0.1 * (2**attempt)
                    logger.debug(
                        "Cache lock timeout on keys, retrying",
                        extra={"attempt": attempt + 1, "backoff": backoff},
                    )
                    time.sleep(backoff)
                else:
                    logger.warning(f"Cache lock timeout on keys after {self.max_retries} retries")
                    return []
            except Exception as exc:
                logger.warning(f"Cache keys error: {exc}")
                return []
        return []


__all__ = ["CacheEntry", "JsonFileCacheAdapter"]
