"""MySQL cache adapter for distributed caching.

This module provides a MySQL-based cache implementation for environments
where multiple processes or machines need to share a cache.

Classes:
    - :class:`MySQLCacheAdapter`: MySQL-backed key-value cache.

Note:
    Requires the optional ``mysql`` dependency group::

        pip install lib_shopify_graphql[mysql]
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from .constants import (
    DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MYSQL_PORT,
    DEFAULT_SKU_CACHE_TABLE,
)

if TYPE_CHECKING:
    from types import TracebackType

    import pymysql

    # Type alias for Connection when type checking
    MySQLConnection = pymysql.Connection[Any]
else:
    # Runtime type alias
    MySQLConnection = Any

logger = logging.getLogger(__name__)

# Try to import pymysql, but don't fail if not installed
_pymysql_module: Any = None
_pymysql_available = False
try:
    import pymysql as _pymysql_module  # type: ignore[import-untyped,no-redef]

    _pymysql_available = True
except ImportError:
    pass

PYMYSQL_AVAILABLE: bool = _pymysql_available


@dataclass(frozen=True, slots=True)
class MySQLConnectionParams:
    """Parsed MySQL connection parameters.

    Immutable dataclass containing all parameters needed to connect
    to a MySQL database, extracted from a connection URL.

    Attributes:
        host: MySQL server hostname.
        port: MySQL server port (default 3306).
        user: MySQL username.
        password: MySQL password (may be empty string).
        database: MySQL database name.
    """

    host: str
    port: int
    user: str
    password: str
    database: str


def parse_mysql_connection_string(connection_string: str) -> MySQLConnectionParams:
    """Parse a MySQL connection string into components.

    Supported formats:
        - mysql://user:password@host:port/database
        - mysql://user:password@host/database (default port 3306)
        - mysql://user@host/database (no password)

    Passwords may contain special characters if URL-encoded:
        - mysql://user:p%40ssword@host/db (password is "p@ssword")

    Args:
        connection_string: MySQL connection URL.

    Returns:
        MySQLConnectionParams dataclass with connection parameters.

    Raises:
        ValueError: If connection string format is invalid.
    """
    parsed = urlparse(connection_string)

    if parsed.scheme != "mysql":
        msg = f"Invalid MySQL connection string scheme: expected 'mysql', got '{parsed.scheme}'"
        raise ValueError(msg)

    if not parsed.hostname:
        msg = f"Invalid MySQL connection string: missing hostname in '{connection_string}'"
        raise ValueError(msg)

    database = parsed.path.lstrip("/")
    if not database:
        msg = f"Invalid MySQL connection string: missing database name in '{connection_string}'"
        raise ValueError(msg)

    return MySQLConnectionParams(
        host=parsed.hostname,
        port=parsed.port or DEFAULT_MYSQL_PORT,
        user=unquote(parsed.username) if parsed.username else "root",
        password=unquote(parsed.password) if parsed.password else "",
        database=database,
    )


class MySQLCacheAdapter:
    """MySQL-based cache for distributed/shared caching.

    Implements :class:`~lib_shopify_graphql.application.ports.CachePort`.

    Automatically creates the database and cache table if they don't exist.
    Uses INSERT ... ON DUPLICATE KEY UPDATE for atomic upserts.

    Uses a persistent connection that is reused across operations for better
    performance. The connection is automatically re-established if it drops.
    Use as a context manager or call :meth:`close` when done.

    Attributes:
        host: MySQL server hostname.
        port: MySQL server port.
        user: MySQL username.
        password: MySQL password.
        database: MySQL database name.
        table_name: Name of the cache table.

    Example:
        >>> # Using as context manager (recommended)
        >>> with MySQLCacheAdapter.from_url("mysql://app:secret@localhost:3306/myapp") as cache:
        ...     cache.set("sku:myshop:ABC-123", "gid://shopify/ProductVariant/123", ttl=86400)
        ...     cache.get("sku:myshop:ABC-123")
        'gid://shopify/ProductVariant/123'

        >>> # Without context manager (call close() when done)
        >>> cache = MySQLCacheAdapter.from_url("mysql://app:secret@localhost:3306/myapp")
        >>> try:
        ...     cache.set("key", "value")
        ... finally:
        ...     cache.close()

    Raises:
        ImportError: If pymysql is not installed.
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = DEFAULT_MYSQL_PORT,
        user: str,
        password: str,
        database: str,
        table_name: str = DEFAULT_SKU_CACHE_TABLE,
        connect_timeout: int = DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS,
        auto_create_database: bool = True,
    ) -> None:
        """Initialize the MySQL cache adapter.

        Args:
            host: MySQL server hostname. Defaults to 'localhost'.
            port: MySQL server port. Defaults to DEFAULT_MYSQL_PORT.
            user: MySQL username.
            password: MySQL password.
            database: MySQL database name (created if doesn't exist).
            table_name: Name of the cache table. Defaults to DEFAULT_SKU_CACHE_TABLE.
            connect_timeout: Connection timeout in seconds. Defaults to DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS.
            auto_create_database: Create database if not exists. Defaults to True.

        Raises:
            ImportError: If pymysql is not installed.
        """
        if not PYMYSQL_AVAILABLE:
            msg = "pymysql is required for MySQL cache. Install with: pip install lib_shopify_graphql[mysql]"
            raise ImportError(msg)

        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.table_name = table_name
        self.connect_timeout = connect_timeout

        # Thread-local storage for connections (thread-safe)
        self._local = threading.local()

        # Create database and table on init
        if auto_create_database:
            self._ensure_database_exists()
        self._ensure_table_exists()

    @classmethod
    def from_url(
        cls,
        connection_string: str,
        *,
        table_name: str = DEFAULT_SKU_CACHE_TABLE,
        connect_timeout: int = DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS,
        auto_create_database: bool = True,
    ) -> MySQLCacheAdapter:
        """Create adapter from a connection URL string.

        Args:
            connection_string: MySQL connection URL
                (e.g., 'mysql://user:password@host:port/database').
            table_name: Name of the cache table. Defaults to DEFAULT_SKU_CACHE_TABLE.
            connect_timeout: Connection timeout in seconds. Defaults to DEFAULT_MYSQL_CONNECT_TIMEOUT_SECONDS.
            auto_create_database: Create database if not exists. Defaults to True.

        Returns:
            Configured MySQLCacheAdapter instance.

        Example:
            >>> cache = MySQLCacheAdapter.from_url(
            ...     "mysql://shopify:secret@db.example.com:3306/shopify_cache",
            ...     table_name="token_cache",
            ... )
        """
        params = parse_mysql_connection_string(connection_string)
        return cls(
            host=params.host,
            port=params.port,
            user=params.user,
            password=params.password,
            database=params.database,
            table_name=table_name,
            connect_timeout=connect_timeout,
            auto_create_database=auto_create_database,
        )

    def _create_connection(self, *, use_database: bool = True) -> MySQLConnection:
        """Create a new database connection.

        Args:
            use_database: Whether to connect to the specific database.
                Set to False for database creation.

        Returns:
            pymysql Connection object.
        """
        return _pymysql_module.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database if use_database else None,
            connect_timeout=self.connect_timeout,
            autocommit=True,
            charset="utf8mb4",
        )

    def _get_connection(self) -> MySQLConnection:
        """Get a thread-local connection, creating or reconnecting if needed.

        Returns:
            pymysql Connection object.

        Note:
            Each thread gets its own connection for thread safety.
            Connections are reused within a thread for performance.
            If the connection is lost, it will be automatically re-established.
        """
        conn = getattr(self._local, "conn", None)

        if conn is None:
            self._local.conn = self._create_connection(use_database=True)
            logger.debug("Created new MySQL connection for thread")
            return self._local.conn

        if not conn.open:
            # Connection was closed, reconnect
            logger.debug("Reconnecting to MySQL (connection was closed)")
            self._local.conn = self._create_connection(use_database=True)
            return self._local.conn

        # Ping to check if connection is still alive
        try:
            conn.ping(reconnect=True)
        except Exception:
            # Connection lost, reconnect
            logger.debug("Reconnecting to MySQL (ping failed)")
            self._local.conn = self._create_connection(use_database=True)

        return self._local.conn

    def close(self) -> None:
        """Close the current thread's database connection.

        Call this when done with the cache adapter to release resources.
        The connection will be automatically re-established if needed.

        Note:
            This only closes the connection for the calling thread.
            Other threads' connections remain open.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
                logger.debug("Closed MySQL connection for thread")
            except Exception as exc:
                logger.warning(f"Error closing MySQL connection: {exc}")
            finally:
                self._local.conn = None

    def _ensure_database_exists(self) -> None:
        """Create the database if it doesn't exist.

        Uses a temporary connection without database selection.
        """
        create_sql = f"""
            CREATE DATABASE IF NOT EXISTS `{self.database}`
            CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
        """
        conn = None
        try:
            conn = self._create_connection(use_database=False)
            with conn.cursor() as cursor:
                cursor.execute(create_sql)
            logger.info(f"Ensured database '{self.database}' exists")
        except Exception as exc:
            logger.error(f"Failed to create database '{self.database}': {exc}")
            raise
        finally:
            if conn is not None:
                conn.close()

    def _ensure_table_exists(self) -> None:
        """Create the cache table if it doesn't exist."""
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS `{self.table_name}` (
                `cache_key` VARCHAR(512) NOT NULL PRIMARY KEY,
                `value` TEXT NOT NULL,
                `expires_at` BIGINT NULL,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_expires` (`expires_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(create_sql)
            logger.info(f"Ensured cache table '{self.table_name}' exists")
        except Exception as exc:
            logger.error(f"Failed to create cache table '{self.table_name}': {exc}")
            raise

    def get(self, key: str) -> str | None:
        """Get a value from the cache.

        Args:
            key: Cache key to look up.

        Returns:
            The cached value, or None if not found or expired.
        """
        now = int(time.time())
        select_sql = f"""
            SELECT `value` FROM `{self.table_name}`
            WHERE `cache_key` = %s
            AND (`expires_at` IS NULL OR `expires_at` > %s)
        """  # nosec B608 - table_name is class attribute, not user input
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(select_sql, (key, now))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as exc:
            logger.warning(f"Cache get error for key '{key}': {exc}")
            return None

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Store a value in the cache.

        Args:
            key: Cache key.
            value: Value to store.
            ttl: Time-to-live in seconds. None for no expiration.
        """
        expires_at = int(time.time()) + ttl if ttl else None
        upsert_sql = f"""
            INSERT INTO `{self.table_name}` (`cache_key`, `value`, `expires_at`)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `expires_at` = VALUES(`expires_at`)
        """  # nosec B608 - table_name is class attribute, not user input
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(upsert_sql, (key, value, expires_at))
        except Exception as exc:
            logger.warning(f"Cache set error for key '{key}': {exc}")

    def delete(self, key: str) -> None:
        """Remove a key from the cache.

        Args:
            key: Cache key to remove.
        """
        delete_sql = f"DELETE FROM `{self.table_name}` WHERE `cache_key` = %s"  # nosec B608
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(delete_sql, (key,))
        except Exception as exc:
            logger.warning(f"Cache delete error for key '{key}': {exc}")

    def clear(self) -> None:
        """Clear all cached entries."""
        truncate_sql = f"TRUNCATE TABLE `{self.table_name}`"
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(truncate_sql)
        except Exception as exc:
            logger.warning(f"Cache clear error: {exc}")

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed.
        """
        now = int(time.time())
        delete_sql = f"""
            DELETE FROM `{self.table_name}`
            WHERE `expires_at` IS NOT NULL AND `expires_at` <= %s
        """  # nosec B608 - table_name is class attribute, not user input
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(delete_sql, (now,))
                return cursor.rowcount
        except Exception as exc:
            logger.warning(f"Cache cleanup error: {exc}")
            return 0

    def keys(self, prefix: str | None = None) -> list[str]:
        """List all cache keys, optionally filtered by prefix.

        Args:
            prefix: If provided, only return keys starting with this prefix.

        Returns:
            List of cache keys (excluding expired entries).
        """
        now = int(time.time())
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                if prefix:
                    # Use LIKE with escaped prefix for prefix matching
                    # Escape % and _ which are LIKE wildcards
                    escaped_prefix = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    select_sql = f"""
                        SELECT `cache_key` FROM `{self.table_name}`
                        WHERE `cache_key` LIKE %s
                        AND (`expires_at` IS NULL OR `expires_at` > %s)
                    """  # nosec B608 - table_name is class attribute, not user input
                    cursor.execute(select_sql, (escaped_prefix + "%", now))
                else:
                    select_sql = f"""
                        SELECT `cache_key` FROM `{self.table_name}`
                        WHERE (`expires_at` IS NULL OR `expires_at` > %s)
                    """  # nosec B608 - table_name is class attribute, not user input
                    cursor.execute(select_sql, (now,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as exc:
            logger.warning(f"Cache keys error: {exc}")
            return []

    def __enter__(self) -> MySQLCacheAdapter:
        """Enter context manager, returning self.

        Example:
            >>> with MySQLCacheAdapter.from_url("mysql://...") as cache:
            ...     cache.set("key", "value")
            ...     cache.get("key")
            # Connection is automatically closed on exit
        """
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager, closing the connection."""
        self.close()

    def __repr__(self) -> str:
        """Return string representation with password redacted.

        Password is always shown as '***' to prevent accidental exposure
        in logs, exceptions, or debugging output.
        """
        return (
            f"MySQLCacheAdapter(host={self.host!r}, port={self.port}, "
            f"user={self.user!r}, password='***', database={self.database!r}, "
            f"table_name={self.table_name!r})"
        )

    def __str__(self) -> str:
        """Return user-friendly string with password redacted."""
        return f"MySQLCacheAdapter({self.user}@{self.host}:{self.port}/{self.database})"


__all__ = [
    "MySQLCacheAdapter",
    "MySQLConnectionParams",
    "PYMYSQL_AVAILABLE",
    "parse_mysql_connection_string",
]
