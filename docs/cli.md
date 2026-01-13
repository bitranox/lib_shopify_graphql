# CLI Usage

The CLI leverages [rich-click](https://github.com/ewels/rich-click) so help output, validation errors, and prompts render with Rich styling while keeping the familiar click ergonomics.

## Available Commands

```bash
# Display package information
lib-shopify-graphql info

# Shopify connectivity check
lib-shopify-graphql health                    # Check API connectivity and credentials
lib-shopify-graphql health --profile prod     # Check with specific profile

# Product operations
lib-shopify-graphql get-product 123456789              # Get product by ID
lib-shopify-graphql get-product 123456789 --format json
lib-shopify-graphql create-product --title "New Product" --status DRAFT
lib-shopify-graphql create-product --json product.json  # Create from JSON file
lib-shopify-graphql update-product 123456789 --title "Updated Title"
lib-shopify-graphql duplicate-product 123456789 --new-title "Copy of Product"
lib-shopify-graphql delete-product 123456789           # Delete permanently

# Image management
lib-shopify-graphql add-image 123456789 --url https://example.com/image.jpg
lib-shopify-graphql add-image 123456789 --file ./local-image.jpg --alt "Product front"
lib-shopify-graphql delete-image 123456789 gid://shopify/ProductImage/111
lib-shopify-graphql update-image 123456789 111 --alt "Updated alt text"
lib-shopify-graphql reorder-images 123456789 --order 333,111,222

# Cache management
lib-shopify-graphql tokencache-clear         # Clear OAuth token cache
lib-shopify-graphql skucache-clear           # Clear SKU-to-GID mapping cache
lib-shopify-graphql cache-clear-all          # Clear all caches
lib-shopify-graphql skucache-rebuild         # Rebuild SKU cache from Shopify
lib-shopify-graphql skucache-rebuild --query "status:active"  # Rebuild with filter
lib-shopify-graphql skucache-check           # Check cache consistency with Shopify

# GraphQL limit testing
lib-shopify-graphql test-limits               # Test ALL products for truncation
lib-shopify-graphql test-limits -n 100        # Limit to 100 products
lib-shopify-graphql test-limits --query "status:active"  # Test only active products

# Configuration management
lib-shopify-graphql config                    # Show current configuration
lib-shopify-graphql config --format json      # Show as JSON
lib-shopify-graphql config --section lib_log_rich  # Show specific section
lib-shopify-graphql config --profile production    # Show config from a profile
lib-shopify-graphql config-deploy --target user    # Deploy config to user directory
lib-shopify-graphql config-deploy --target user --target host  # Deploy to multiple locations
lib-shopify-graphql config-deploy --target user --profile staging  # Deploy to profile directory

# All commands work with any entry point
python -m lib_shopify_graphql info
uvx lib_shopify_graphql info
```

## Health Check

Verify Shopify API connectivity and credentials before running operations:

```bash
lib-shopify-graphql health
```

**On success**, displays:
- Connected shop name
- API version in use
- Token expiration time

**On failure**, displays:
- Error type and message
- Actionable steps to resolve the issue

This is useful for:
- Validating credentials after initial setup
- Troubleshooting connection issues
- Verifying configuration in CI/CD pipelines

## Global CLI Flags

All commands support these global flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--traceback/--no-traceback` | `--no-traceback` | Show full Python traceback on errors |
| `--profile` | `None` | Load configuration from a named profile |

```bash
# Show full traceback for debugging
lib-shopify-graphql --traceback health

# Use production profile for all commands
lib-shopify-graphql --profile production health
lib-shopify-graphql --profile production get-product 123456789
```

## Exit Codes

All CLI commands follow consistent exit code conventions for scripting and CI/CD integration:

| Exit Code | Meaning |
|-----------|---------|
| `0` | Success |
| `1` | Failure (error occurred or check failed) |

### Exit Code Behavior by Command

| Command             | On Success | On Failure | Notes                                         |
|---------------------|------------|------------|-----------------------------------------------|
| `info`              | 0          | -          | Always succeeds                               |
| `config`            | 0          | -          | Always succeeds                               |
| `config-deploy`     | 0          | 1          | Permission errors, deploy failures            |
| `health`            | 0          | 1          | Auth failures, connection errors              |
| `get-product`       | 0          | 1          | Product not found, auth errors                |
| `create-product`    | 0          | 1          | Validation errors, GraphQL errors             |
| `update-product`    | 0          | 1          | Product not found, JSON/GraphQL errors        |
| `duplicate-product` | 0          | 1          | Product not found, GraphQL errors             |
| `delete-product`    | 0          | 1          | Product not found, auth errors                |
| `add-image`         | 0          | 1          | Upload failures, GraphQL errors               |
| `delete-image`      | 0          | 1          | Image not found, auth errors                  |
| `update-image`      | 0          | 1          | Image not found, GraphQL errors               |
| `reorder-images`    | 0          | 1          | Invalid order, GraphQL errors                 |
| `tokencache-clear`  | 0          | 1          | Returns 0 if not configured (info only)       |
| `skucache-clear`    | 0          | 1          | Returns 0 if not configured (info only)       |
| `cache-clear-all`   | 0          | 1          | Returns 0 if no caches configured (info only) |
| `skucache-rebuild`  | 0          | 1          | Cache not configured, auth errors             |
| `skucache-check`    | 0          | 1          | Cache inconsistencies detected, auth errors   |
| `test-limits`       | 0          | 1          | Truncation detected, auth errors              |

### CI/CD Integration Examples

```bash
# Fail pipeline if health check fails
lib-shopify-graphql health || exit 1

# Fail if cache has inconsistencies
lib-shopify-graphql skucache-check || echo "Cache needs rebuild!"

# Fail if data is being truncated
lib-shopify-graphql test-limits || echo "Increase GraphQL limits!"

# Check exit code explicitly
lib-shopify-graphql skucache-check
if [ $? -ne 0 ]; then
    lib-shopify-graphql skucache-rebuild
fi
```

## Test Limits

Test if current GraphQL query limits are causing data truncation. This command iterates through products and uses `pageInfo.hasNextPage` to detect if nested collections (images, media, variants, metafields) are being truncated.

```bash
# Test ALL products
lib-shopify-graphql test-limits

# Limit to 100 products for faster testing
lib-shopify-graphql test-limits -n 100

# Test only active products
lib-shopify-graphql test-limits --query "status:active"
```

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `-n, --limit` | `None` (all) | Maximum products to analyze |
| `-q, --query` | `None` | Shopify search query filter |
| `-p, --profile` | `None` | Named configuration profile |

**Output includes:**
- Current configured GraphQL limits
- Products with truncated data
- Maximum counts found for each field
- Recommendations for which limits to increase

## Configuration Management

The application uses [lib_layered_config](https://github.com/bitranox/lib_layered_config) for hierarchical configuration with the following precedence (lowest to highest):

**defaults -> app -> host -> user -> .env -> environment variables**

### Configuration Locations

Platform-specific paths:
- **Linux (user)**: `~/.config/lib-shopify-graphql/config.toml`
- **Linux (app)**: `/etc/xdg/lib-shopify-graphql/config.toml`
- **Linux (host)**: `/etc/lib-shopify-graphql/hosts/{hostname}.toml`
- **macOS (user)**: `~/Library/Application Support/bitranox/Lib Shopify GraphQL/config.toml`
- **Windows (user)**: `%APPDATA%\bitranox\Lib Shopify GraphQL\config.toml`

### Profile-specific Paths

Profiles enable environment isolation by creating dedicated subdirectories for each profile name. Use `--profile <name>` with `config` or `config-deploy` commands.

- **Linux (user, profile=production)**: `~/.config/lib-shopify-graphql/profile/production/config.toml`
- **Linux (user, profile=staging)**: `~/.config/lib-shopify-graphql/profile/staging/config.toml`

Valid profile names: alphanumeric characters, hyphens, and underscores (e.g., `test`, `production`, `staging-v2`).

### View Configuration

```bash
# Show merged configuration from all sources
lib-shopify-graphql config

# Show as JSON for scripting
lib-shopify-graphql config --format json

# Show specific section only
lib-shopify-graphql config --section lib_log_rich

# Show configuration from a specific profile
lib-shopify-graphql config --profile production
lib-shopify-graphql config --profile staging --format json
```

### Deploy Configuration Files

```bash
# Create user configuration file
lib-shopify-graphql config-deploy --target user

# Deploy to system-wide location (requires privileges)
sudo lib-shopify-graphql config-deploy --target app

# Deploy to multiple locations at once
lib-shopify-graphql config-deploy --target user --target host

# Overwrite existing configuration
lib-shopify-graphql config-deploy --target user --force

# Deploy to a profile-specific directory
lib-shopify-graphql config-deploy --target user --profile production
lib-shopify-graphql config-deploy --target user --profile staging --force
```

### Environment Variable Overrides

Configuration can be overridden via environment variables using two methods:

**Method 1: Native lib_log_rich variables (highest precedence)**
```bash
LOG_CONSOLE_LEVEL=DEBUG lib-shopify-graphql hello
LOG_ENABLE_GRAYLOG=true LOG_GRAYLOG_ENDPOINT="logs.example.com:12201" lib-shopify-graphql hello
```

**Method 2: Application-prefixed variables**
```bash
# Format: <SLUG>___<SECTION>__<KEY>=<VALUE>
LIB_SHOPIFY_GRAPHQL___LIB_LOG_RICH__CONSOLE_LEVEL=DEBUG lib-shopify-graphql hello
```

### .env File Support

Create a `.env` file in your project directory for local development:

```bash
# .env
LOG_CONSOLE_LEVEL=DEBUG
LOG_CONSOLE_FORMAT_PRESET=short
LOG_ENABLE_GRAYLOG=false
```

The application automatically discovers and loads `.env` files from the current directory or parent directories.
