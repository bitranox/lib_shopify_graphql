# lib_shopify_graphql

<!-- Badges -->
[![CI](https://github.com/bitranox/lib_shopify_graphql/actions/workflows/ci.yml/badge.svg)](https://github.com/bitranox/lib_shopify_graphql/actions/workflows/ci.yml)
[![CodeQL](https://github.com/bitranox/lib_shopify_graphql/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/lib_shopify_graphql/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/lib_shopify_graphql?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/lib_shopify_graphql.svg)](https://pypi.org/project/lib_shopify_graphql/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/lib_shopify_graphql.svg)](https://pypi.org/project/lib_shopify_graphql/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/lib_shopify_graphql/graph/badge.svg?token=UFBaUDIgRk)](https://codecov.io/gh/bitranox/lib_shopify_graphql)
[![Maintainability](https://qlty.sh/badges/041ba2c1-37d6-40bb-85a0-ec5a8a0aca0c/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/lib_shopify_graphql)
[![Known Vulnerabilities](https://snyk.io/test/github/bitranox/lib_shopify_graphql/badge.svg)](https://snyk.io/test/github/bitranox/lib_shopify_graphql)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

`lib_shopify_graphql` is a Python library for interacting with the Shopify GraphQL Admin API.

**Features:**
- **Shopify GraphQL API** - Client Credentials Grant authentication (OAuth 2.0)
- **Product CRUD** - Create, read, update, delete, and duplicate products
- **Product Listing** - Cursor-based pagination for listing products with query filtering
- **Image Management** - Add, update, delete, and reorder product images (URL or file upload)
- **Partial Updates** - UNSET sentinel pattern for updating only specified fields
- **Bulk Operations** - Update multiple variants in a single API call
- **Inventory Management** - Set or adjust inventory with location fallback
- **Metafield Operations** - Delete metafields from products and variants
- **Token Caching** - Cache OAuth tokens to reduce authentication overhead
- **SKU Resolution** - Cached SKU-to-GID mapping with ambiguity detection
- **High Performance** - Uses orjson for fast JSON serialization (3-10x faster than stdlib)
- **Typed Pydantic models** - Full validation for credentials, products, variants, images
- **Clean Architecture** - Layered design with ports/adapters for testability
- **Dependency Injection** - Custom adapters for testing and customization
- **CLI entry point** styled with rich-click (rich output + click ergonomics)
- **Layered configuration** with lib_layered_config (defaults -> app -> host -> user -> .env -> env)
- **Rich structured logging** with lib_log_rich (console, journald, eventlog, Graylog/GELF)
- **Exit-code helpers** powered by lib_cli_exit_tools
- Wraps official `ShopifyAPI` package from PyPI

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Partial Updates](#partial-updates)
- [Architecture](#architecture)
- [Documentation](#documentation)
  - [CLI Usage](docs/cli.md)
  - [Caching](docs/caching.md)
  - [Shopify App Setup](docs/shopify_setup.md)
  - [API Reference](docs/api_reference.md)
- [Further Documentation](#further-documentation)

---

## Installation

**Recommended: Install via UV** (10-20x faster than pip/poetry):

```bash
pip install --upgrade uv
uv venv && source .venv/bin/activate  # Create and activate venv
uv pip install lib_shopify_graphql
```

### Optional Extras

The library supports optional features via extras:

| Extra | Description | Install Command |
|-------|-------------|-----------------|
| `mysql` | MySQL cache backend (pymysql) | `uv pip install lib_shopify_graphql[mysql]` |
| `dev` | Development tools (pytest, ruff, etc.) | `uv pip install lib_shopify_graphql[dev]` |

```bash
# Install with MySQL support
uv pip install lib_shopify_graphql[mysql]

# Install with pip
pip install lib_shopify_graphql[mysql]

# Install multiple extras
uv pip install "lib_shopify_graphql[mysql,dev]"
```

For alternative install paths (pip, pipx, uvx, source builds, etc.), see [INSTALL.md](INSTALL.md).

### Python 3.10+ Baseline

- The project targets **Python 3.10 and newer**.
- Runtime dependencies stay on current stable releases.
- CI workflows exercise GitHub's rolling runner images covering Python 3.10, 3.11, 3.12, and 3.13.

---

## Quick Start

```python
from lib_shopify_graphql import (
    login,
    logout,
    get_product_by_id,
    get_product_id_from_sku,
    list_products,
    list_products_paginated,
    ShopifyCredentials,
)

# Create credentials
credentials = ShopifyCredentials(
    shop_url="mystore.myshopify.com",
    client_id="your_client_id",
    client_secret="your_client_secret",
)

# Login (obtains access token via client credentials grant)
session = login(credentials)
print(f"Connected to: {session.info.shop_url}")

# Get product by ID
product = get_product_by_id(session, "123456789")  # or full GID
print(f"Product: {product.title}")
print(f"Status: {product.status}")
print(f"Variants: {len(product.variants)}")

# List all products (auto-pagination)
products = list_products(session)
for product in products:
    print(f"- {product.title} ({product.handle})")

# Or use manual pagination for large catalogs
result = list_products_paginated(session, first=50)
while result.page_info.has_next_page:
    result = list_products_paginated(session, first=50, after=result.page_info.end_cursor)
    for product in result.products:
        print(f"- {product.title}")

# Logout when done
logout(session)
```

---

## Partial Updates

The library uses a sentinel pattern for partial updates, allowing you to update only specific fields:

- `UNSET` (default) - Don't update this field
- `None` - Clear this field (set to null on Shopify)
- `value` - Update to this value

```python
from decimal import Decimal
from lib_shopify_graphql import (
    login, update_variant, update_variants_bulk,
    set_inventory, adjust_inventory,
    VariantUpdate, VariantUpdateRequest, UNSET,
)

session = login(credentials)

# Update price only (other fields unchanged)
update_variant(
    session,
    "SKU-12345",  # Can use SKU or GID
    VariantUpdate(price=Decimal("29.99")),
)

# Clear compare_at_price (remove sale)
update_variant(
    session,
    "gid://shopify/ProductVariant/123",
    VariantUpdate(compare_at_price=None),
)

# Bulk update multiple variants
result = update_variants_bulk(
    session,
    "gid://shopify/Product/456",
    [
        VariantUpdateRequest(
            sku="SKU-001",
            update=VariantUpdate(price=Decimal("19.99")),
        ),
        VariantUpdateRequest(
            sku="SKU-002",
            update=VariantUpdate(barcode="123456789012"),
        ),
    ],
)
print(f"Updated: {result.success_count}, Failed: {result.failure_count}")

# Set absolute inventory
set_inventory(session, "SKU-12345", quantity=100)

# Adjust inventory by delta
adjust_inventory(session, "SKU-12345", delta=-5)

logout(session)
```

---

## Architecture

The library follows **Clean Architecture** principles with distinct layers:

```
lib_shopify_graphql/
├── domain/             # Core business rules (pure Python, no dependencies)
├── application/        # Use cases and ports (Protocol interfaces)
│   └── ports.py        # TokenProviderPort, GraphQLClientPort, SessionManagerPort
├── adapters/           # External system implementations
│   ├── shopify_sdk.py  # Shopify SDK implementations
│   ├── parsers.py      # GraphQL response parsers
│   ├── queries.py      # GraphQL query definitions
│   ├── mutations.py    # GraphQL mutation definitions
│   └── cache_*.py      # Cache adapter implementations
├── composition.py      # Dependency injection wiring
├── shopify_client/     # Core API package (login, logout, product operations)
│   ├── _session.py     # Session management
│   ├── _products.py    # Product operations
│   ├── _variants.py    # Variant operations
│   ├── _inventory.py   # Inventory operations
│   ├── _images.py      # Image operations
│   └── _cache.py       # Cache management
├── models/             # Pydantic data models package
│   ├── _entities.py    # Read models (Product, Variant, etc.)
│   ├── _mutations.py   # Partial update models
│   └── _operations.py  # Operation results
└── exceptions.py       # Domain exceptions
```

**Layer dependencies point inward only:**
- Adapters -> Application -> Domain
- Domain has no framework dependencies
- Application ports have no adapter dependencies

**Enforced via import-linter:**
```toml
[tool.importlinter]
root_package = "lib_shopify_graphql"

[[tool.importlinter.contracts]]
name = "Clean Architecture layers"
type = "layers"
layers = [
  "lib_shopify_graphql.adapters",
  "lib_shopify_graphql.application",
  "lib_shopify_graphql.domain",
]
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [CLI Usage](docs/cli.md) | Command-line interface commands and configuration |
| [Caching](docs/caching.md) | Token and SKU caching with JSON or MySQL backends |
| [Shopify App Setup](docs/shopify_setup.md) | Setting up Shopify app credentials |
| [API Reference](docs/api_reference.md) | Complete API documentation for all functions and models |
| [Module Reference](docs/systemdesign/module_reference.md) | Internal module documentation |

---

## Further Documentation

- [Install Guide](INSTALL.md)
- [Development Handbook](DEVELOPMENT.md)
- [Contributor Guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [License](LICENSE)
