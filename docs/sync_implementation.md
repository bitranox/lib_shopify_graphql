# Sync Subpackage Implementation Plan

This document contains the implementation plan for the `lib_shopify_graphql.sync` subpackage, which provides bidirectional data sync (export + import) functionality.

## Status

**Pending** - Prerequisites (Phase 1) must be completed first:
- `list_products()` with cursor-based pagination
- `create_product()` mutation

## Installation

```bash
pip install lib_shopify_graphql[sync]
```

---

## Directory Structure

```
src/lib_shopify_graphql/
├── ... (existing files)
└── sync/                     # NEW subpackage
    ├── __init__.py           # Public API
    ├── export/
    │   ├── __init__.py
    │   ├── json_exporter.py
    │   ├── csv_exporter.py
    │   └── mysql_exporter.py
    ├── import_/              # 'import' is reserved keyword
    │   ├── __init__.py
    │   ├── json_importer.py
    │   ├── csv_importer.py
    │   └── mysql_importer.py
    ├── manager.py            # SyncManager
    ├── state.py              # SyncState tracking
    └── models.py             # ExportResult, ImportResult, etc.

tests/
├── ... (existing tests)
└── test_sync/                # NEW test directory
    ├── test_export_json.py
    ├── test_export_csv.py
    ├── test_import_json.py
    └── test_sync_manager.py
```

---

## pyproject.toml Changes

```toml
[project.optional-dependencies]
sync = [
    "pandas>=2.0",      # CSV handling
    # MySQL already optional via [mysql]
]
dev = [
    "...",
    "lib_shopify_graphql[sync]",  # Include sync deps in dev
]
```

---

## Public API

```python
# After: pip install lib_shopify_graphql[sync]
from lib_shopify_graphql.sync import (
    # Export
    export_products_to_json,
    export_products_to_csv,
    export_products_to_mysql,
    # Import
    import_products_from_json,
    import_products_from_csv,
    import_products_from_mysql,
    # Sync
    SyncManager,
    SyncConfig,
    # Results
    ExportResult,
    ImportResult,
    SyncResult,
)
```

---

## Usage Examples

### Export to JSON

```python
from lib_shopify_graphql import login, ShopifyCredentials
from lib_shopify_graphql.sync import export_products_to_json
from pathlib import Path

session = login(credentials)

# Full export
result = export_products_to_json(
    session,
    output_path=Path("products.json"),
)
print(f"Exported {result.count} products")

# Incremental export (only changed since date)
result = export_products_to_json(
    session,
    output_path=Path("products_delta.json"),
    query="updated_at:>2024-01-01",
)
```

### Export to CSV

```python
from lib_shopify_graphql.sync import export_products_to_csv

result = export_products_to_csv(
    session,
    output_path=Path("products.csv"),
    include_variants=True,  # Flatten variants into rows
)
```

### Export to MySQL

```python
from lib_shopify_graphql.sync import export_products_to_mysql

result = export_products_to_mysql(
    session,
    connection="mysql://user:pass@localhost/shopify_data",
    table_prefix="shopify_",  # Creates shopify_products, shopify_variants tables
)
```

### Import from CSV

```python
from lib_shopify_graphql.sync import import_products_from_csv

result = import_products_from_csv(
    session,
    input_path=Path("products.csv"),
    on_conflict="update",  # or "skip", "error"
)
print(f"Created: {result.created}, Updated: {result.updated}, Skipped: {result.skipped}")
```

### Import from JSON

```python
from lib_shopify_graphql.sync import import_products_from_json

result = import_products_from_json(
    session,
    input_path=Path("products.json"),
    on_conflict="update",
    dry_run=True,  # Preview changes without applying
)
```

### Bidirectional Sync

```python
from lib_shopify_graphql.sync import SyncManager, JsonSyncState

sync = SyncManager(
    session=session,
    state_store=JsonSyncState(Path(".sync_state.json")),
)

# Pull changes from Shopify to local
sync.pull()

# Push local changes to Shopify
sync.push()

# Full bidirectional sync
sync.sync()
```

---

## Models

### ExportResult

```python
class ExportResult(BaseModel):
    """Result of an export operation."""
    model_config = ConfigDict(frozen=True)

    count: int                    # Number of products exported
    output_path: Path | None      # File path (if file export)
    duration_seconds: float       # Time taken
    errors: list[ExportError]     # Any non-fatal errors
```

### ImportResult

```python
class ImportResult(BaseModel):
    """Result of an import operation."""
    model_config = ConfigDict(frozen=True)

    created: int                  # Products created
    updated: int                  # Products updated
    skipped: int                  # Products skipped (on_conflict="skip")
    failed: int                   # Products that failed
    errors: list[ImportError]     # Detailed error info
    duration_seconds: float
```

### SyncConfig

```python
class SyncConfig(BaseModel):
    """Configuration for sync operations."""
    model_config = ConfigDict(frozen=True)

    batch_size: int = 50          # Products per API call
    on_conflict: Literal["update", "skip", "error"] = "update"
    include_variants: bool = True
    include_images: bool = True
    include_metafields: bool = False
```

---

## Implementation Order

1. Create `sync/` directory structure
2. Add `[sync]` optional dependency to pyproject.toml
3. Implement JSON export (simplest, no extra deps)
4. Implement JSON import
5. Add CSV export/import (uses pandas)
6. Add MySQL export/import (reuses existing MySQLCacheAdapter pattern)
7. Implement SyncManager for incremental sync
8. Add CLI commands: `lib-shopify-graphql export`, `lib-shopify-graphql import`

---

## CLI Commands

```bash
# Export commands
lib-shopify-graphql export --format json --output products.json
lib-shopify-graphql export --format csv --output products.csv --include-variants
lib-shopify-graphql export --format mysql --connection "mysql://..." --table-prefix shopify_

# Import commands
lib-shopify-graphql import --format json --input products.json --on-conflict update
lib-shopify-graphql import --format csv --input products.csv --dry-run

# Sync commands
lib-shopify-graphql sync pull --state .sync_state.json
lib-shopify-graphql sync push --state .sync_state.json
```

---

## Features

1. **Streaming/chunked processing** - Handle 50K products without memory issues
2. **Progress callbacks** - Report progress for long exports
3. **Resume on failure** - Track cursor position for restartability
4. **Schema management** - Auto-create/migrate MySQL tables
5. **Dry run mode** - Preview changes without applying
6. **Conflict resolution** - Configurable behavior for existing products

---

## Testing

```bash
# Install with sync extras
pip install -e .[sync]

# Run all tests including sync
make test

# Manual verification
python -c "
from lib_shopify_graphql import login
from lib_shopify_graphql.sync import export_products_to_json
from pathlib import Path

session = login(credentials)
result = export_products_to_json(session, Path('test_export.json'))
print(f'Exported {result.count} products')
"
```
