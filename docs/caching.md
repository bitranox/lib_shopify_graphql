# Caching

The library supports caching for OAuth tokens and SKU-to-GID mappings using JSON file or MySQL backends.

## Default Cache Locations

When using the JSON backend without specifying a path, the library uses OS-appropriate default locations:

| OS | Cache Directory |
|----|-----------------|
| Linux | `~/.cache/lib-shopify-graphql/` |
| macOS | `~/Library/Caches/lib-shopify-graphql/` |
| Windows | `%LOCALAPPDATA%\lib-shopify-graphql\` |

Cache files:
- `token_cache.json` - OAuth access tokens
- `sku_cache.json` - SKU-to-GID mappings

The directory is created automatically if it doesn't exist.

## Token Caching

Cache OAuth access tokens to avoid repeated authentication requests. Tokens are valid for 24 hours.

```bash
# .env - Enable token caching with JSON backend (uses default path)
SHOPIFY__TOKEN_CACHE__ENABLED=true
SHOPIFY__TOKEN_CACHE__BACKEND=json

# Or specify a custom path
SHOPIFY__TOKEN_CACHE__JSON_PATH=/var/cache/shopify/token_cache.json
```

```python
from pathlib import Path
from lib_shopify_graphql import (
    login, ShopifyCredentials,
    create_cached_token_provider, JsonFileCacheAdapter,
)

# Create cached token provider
cache = JsonFileCacheAdapter(Path("/var/cache/shopify/token_cache.json"))
token_provider = create_cached_token_provider(cache=cache)

# Login with cached tokens
session = login(credentials, token_provider=token_provider)
# First call obtains token from Shopify and caches it
# Subsequent calls reuse cached token until near expiration
```

## SKU Caching

Cache SKU-to-variant-GID mappings to reduce API calls when updating by SKU.

> **Important:** The SKU resolver detects ambiguous SKUs (those matching multiple
> variants) and raises `AmbiguousSKUError`. Only unique SKUs are cached. This
> ensures that cached lookups never silently return the wrong variant.

```bash
# .env - SKU cache with MySQL backend
SHOPIFY__SKU_CACHE__BACKEND=mysql
SHOPIFY__MYSQL__CONNECTION=mysql://user:password@localhost:3306/shopify_cache
SHOPIFY__SKU_CACHE__TTL=86400  # 24 hours
```

## Cache Backend Selection

**Important:** The cache backend must be explicitly configured using the `backend` parameter. The library does NOT auto-detect based on other parameters.

| Backend | Config | Description |
|---------|--------|-------------|
| `json` | `backend = "json"` | File-based with filelock (single machine or network shares) |
| `mysql` | `backend = "mysql"` | Database-backed (distributed/multi-machine setups) |

## TOML Configuration

Complete cache configuration in `config.toml`:

```toml
# ==============================================================================
# Shared MySQL settings (used by both caches when backend="mysql")
# ==============================================================================
[shopify.mysql]
# Option 1: Connection string (takes precedence)
connection = "mysql://shopify_app:secret@localhost:3306/shopify_cache"

# Option 2: Individual parameters (used when connection is empty)
# host = "localhost"
# port = 3306
# user = "shopify_app"
# password = "secret"
# database = "shopify_cache"

# Common settings
auto_create_database = true
connect_timeout = 10

# ==============================================================================
# Token Cache Configuration
# ==============================================================================
[shopify.token_cache]
enabled = true
backend = "json"  # "json" or "mysql"

# JSON backend settings
json_path = ""  # Empty = platform default (~/.cache/lib-shopify-graphql/)
lock_timeout = 10.0

# MySQL backend settings (uses [shopify.mysql.connection] if mysql_connection empty)
mysql_connection = ""  # Override shared connection
mysql_table = "token_cache"

# ==============================================================================
# SKU Cache Configuration
# ==============================================================================
[shopify.sku_cache]
enabled = true
backend = "json"  # "json" or "mysql"
ttl = 2592000  # 30 days in seconds

# JSON backend settings
json_path = ""  # Empty = platform default
lock_timeout = 10.0

# MySQL backend settings
mysql_connection = ""  # Override shared connection
mysql_table = "sku_cache"
```

## MySQL Backend

Both token and SKU caches can use MySQL for distributed/multi-machine environments.
The database and tables are created automatically on first use.

**Environment variables:**

```bash
# .env - Shared MySQL configuration (connection string)
SHOPIFY__MYSQL__CONNECTION=mysql://shopify_app:secret@localhost:3306/shopify_cache
SHOPIFY__MYSQL__AUTO_CREATE_DATABASE=true
SHOPIFY__MYSQL__CONNECT_TIMEOUT=10

# Or use individual parameters (when CONNECTION is not set)
SHOPIFY__MYSQL__HOST=localhost
SHOPIFY__MYSQL__PORT=3306
SHOPIFY__MYSQL__USER=shopify_app
SHOPIFY__MYSQL__PASSWORD=secret
SHOPIFY__MYSQL__DATABASE=shopify_cache
SHOPIFY__MYSQL__AUTO_CREATE_DATABASE=true
SHOPIFY__MYSQL__CONNECT_TIMEOUT=10

# Token cache using MySQL
SHOPIFY__TOKEN_CACHE__ENABLED=true
SHOPIFY__TOKEN_CACHE__BACKEND=mysql
SHOPIFY__TOKEN_CACHE__MYSQL_TABLE=token_cache

# SKU cache using MySQL
SHOPIFY__SKU_CACHE__BACKEND=mysql
SHOPIFY__SKU_CACHE__MYSQL_TABLE=sku_cache
```

**Parameter precedence:** Connection string takes precedence over individual parameters. If `SHOPIFY__MYSQL__CONNECTION` is set, the individual host/port/user/password/database values are ignored.

**Programmatic usage:**

```python
from lib_shopify_graphql import MySQLCacheAdapter

# From connection URL (recommended)
cache = MySQLCacheAdapter.from_url(
    "mysql://shopify_app:secret@localhost:3306/shopify_cache",
    table_name="token_cache",
    auto_create_database=True,
)

# From individual parameters
cache = MySQLCacheAdapter(
    host="localhost",
    port=3306,
    user="shopify_app",
    password="secret",
    database="shopify_cache",
    table_name="sku_cache",
    connect_timeout=10,
    auto_create_database=True,
)

# Use with token provider or SKU resolver
token_provider = create_cached_token_provider(cache=cache)
```

**Required MySQL privileges:**
- `CREATE` - for database and table creation
- `SELECT`, `INSERT`, `UPDATE`, `DELETE` - for cache operations

**Requires:** `pip install lib_shopify_graphql[mysql]` for MySQL support.

## Cache Management

Use CLI commands to manage caches:

```bash
# Clear OAuth token cache (forces re-authentication)
lib-shopify-graphql tokencache-clear

# Clear SKU-to-GID mapping cache
lib-shopify-graphql skucache-clear

# Clear all caches at once
lib-shopify-graphql cache-clear-all

# Rebuild SKU cache from Shopify (fetches all products)
lib-shopify-graphql skucache-rebuild

# Rebuild with filter (only active products)
lib-shopify-graphql skucache-rebuild --query "status:active"

# Check cache consistency against Shopify
lib-shopify-graphql skucache-check
lib-shopify-graphql skucache-check --query "status:active"
```

### Cache Consistency Check

The `skucache-check` command compares your local SKU cache with actual Shopify data to detect inconsistencies:

```bash
lib-shopify-graphql skucache-check
```

**Reports:**
- **Stale entries**: SKUs in cache but no longer in Shopify (deleted products)
- **Missing entries**: SKUs in Shopify but not in cache
- **Mismatched entries**: SKUs with different variant/product GIDs

**Programmatic usage:**

```python
from lib_shopify_graphql import login, skucache_check, JsonFileCacheAdapter

session = login(credentials)
cache = JsonFileCacheAdapter(Path("/var/cache/shopify/sku_cache.json"))

result = skucache_check(session, cache)
if result.is_consistent:
    print("Cache is consistent with Shopify")
else:
    print(f"Stale: {len(result.stale)}, Missing: {len(result.missing)}, Mismatched: {len(result.mismatched)}")
```

### When to Rebuild SKU Cache

- After initial setup to pre-populate the cache
- To verify cache consistency after bulk operations
- When you want fresh mappings without clearing first

### When to Clear SKU Cache

- After bulk import that changed variant GIDs
- After reassigning SKUs to different variants
- After deleting and recreating products
- When SKU lookups return incorrect variants

### When to Clear Token Cache

- After rotating client credentials
- To troubleshoot authentication issues
- When tokens appear stuck or invalid

## Programmatic API

```python
from pathlib import Path
from lib_shopify_graphql import (
    tokencache_clear,
    skucache_clear,
    cache_clear_all,
    skucache_rebuild,
    skucache_check,
    login,
    CachedSKUResolver,
    JsonFileCacheAdapter,
)

# Clear specific cache
cache = JsonFileCacheAdapter(Path("/var/cache/shopify/sku_cache.json"))
skucache_clear(cache)

# Clear both caches
token_cache = JsonFileCacheAdapter(Path("/var/cache/shopify/token_cache.json"))
sku_cache = JsonFileCacheAdapter(Path("/var/cache/shopify/sku_cache.json"))
cache_clear_all(token_cache, sku_cache)

# Rebuild SKU cache from Shopify
session = login(credentials)
sku_resolver = CachedSKUResolver(sku_cache, session._graphql_client)
count = skucache_rebuild(session, sku_resolver=sku_resolver)
print(f"Cached {count} variant SKUs")

# Check cache consistency
result = skucache_check(session, sku_cache)
print(f"Valid: {result.valid}, Stale: {len(result.stale)}, Missing: {len(result.missing)}")
```
