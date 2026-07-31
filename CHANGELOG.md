# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.


## [2.0.8] - 2026-07-24

### Fixed
- Latest ruff (0.16) widened its default rule set from ~0 (no explicit `select`) to ~920 rules, turning CI red with hundreds of newly-enforced violations across unrelated families. Pinned the project's actual lint policy with an explicit curated `[tool.ruff.lint].select` (mirroring the bitranox CLI template) plus targeted per-file-ignores, then fixed the real violations at the root: converted ~120 f-string logging calls to lazy `%`-style formatting (`G004`), added `from err`/`from None` to every bare `raise` inside an `except` block (`B904`), moved trivial deferred imports to module top and kept genuine circular-import/test-monkeypatch deferrals with a documented `# noqa: PLC0415`, made internal helpers and Click callbacks keyword-only to fix `PLR0917` without breaking call sites, replaced blind `pytest.raises(Exception)` with the concrete `pydantic.ValidationError` (and `dataclasses.FrozenInstanceError` where the tested type is a plain frozen dataclass, not a Pydantic model) for `B017`, and decomposed `config_show.display_config` into smaller helpers to clear `PLR0912`/`PLC0206`.
- `PLW0603` (module-level singleton caches in `composition.py` / `shopify_client/_common.py`), `PLR0913` on public adapter/API constructors with independent config or DI-seam parameters, and `S608`/`S310` (parametrized MySQL queries with a validated table name; `urlopen` against a validated `.myshopify.com` shop URL) are genuine, already-accepted designs - documented with narrow `# noqa` comments (kept as a separate `#` comment from any existing bandit `# nosec`, since a merged comment stops bandit's own suppression from matching) rather than loosening the ruff rule set.

### Changed
- Bumped internal dependency floors and `ruff>=0.16.0` (dev pin, to match the version now enforced by the curated select).

### Changed
- Added a `cli/typed_click.py` facade wrapping rich-click's `option` / `version_option` / `argument` decorators behind explicit, fully-known signatures, keeping the CLI strict-clean under pyright (`reportUnknownMemberType`) without disabling the rule (ignore isolated to the facade).
- Bumped internal dependency floors: `lib_cli_exit_tools>=2.3.2`, `lib_log_rich>=6.3.5`, `lib_layered_config>=5.5.2`.

## [2.0.6] - 2026-06-01

### Changed
- Replaced the `httpx` runtime dependency with `httpx2` (the Pydantic-stewarded continuation of HTTPX) for staged image uploads in `shopify_client/_images.py`; `httpx2` is an API-compatible drop-in, so only the import name changed (`httpx.put`/`httpx.post`/`httpx.HTTPError` → `httpx2.*`). The integration test helper was updated to `httpx2.Client` accordingly
- Refreshed `[tool.pip-audit].ignore-vulns`: removed entries no longer flagged (pip symlink, pillow FITS, authlib, cryptography, lxml, python-multipart, prior uv wheel-RECORD) and added `paramiko` CVE-2026-44405 and `uv` GHSA-4gg8-gxpx-9rph (both developer-toolchain-only, not runtime dependencies)
- Bumped runtime and dev dependency floors (`rich-click`, `lib_cli_exit_tools`, `orjson`, `pydantic`, `ruff`, `build`, `textual`, `pymysql`)

### Fixed
- Restored pyright's built-in default excludes (`**/node_modules`, `**/__pycache__`, `**/.*`) in `[tool.pyright]`, which were silently overridden once an explicit `exclude` list was set. A populated local `.venv` no longer causes the `make test` pyright stage to crawl `site-packages` and hang

## [2.0.5] - 2026-04-24

### Fixed
- Replaced `Iterator[ShopifySession]` with `Generator[ShopifySession]` as the return annotation of `cli._common.shopify_session` to clear a pyright 1.1.409 `reportDeprecated` error on `@contextmanager`

### Changed
- Refreshed `[tool.pip-audit].ignore-vulns` in `pyproject.toml`: removed entries no longer flagged (setuptools, pynacl, urllib3, virtualenv, pygments, CVE-2026-25645/CVE-2026-26007) and added current environment-only vulnerabilities (authlib, cryptography, lxml, pillow FITS, pip symlink, python-multipart, uv wheel RECORD)
- Bumped dev and runtime dependency floors (`lib_log_rich`, `lib_layered_config`, `filelock`, `orjson`, `pydantic`, `pytest`, `pytest-cov`, `ruff`, `pyright`, `build`, `codecov-cli`, `textual`)
- Updated CI/CD workflow matrix (codecov-action v6, pip-audit warning-only), removed Snyk badge from `README.md`

## [2.0.4] - 2026-03-09

### Changed
- Extracted `_check_graphql_errors()` helper to `shopify_client/_common.py`, replacing duplicate error-checking across 6 modules
- Inlined 6 trivial wrapper functions that only delegated to `_check_graphql_errors()`
- Added `shopify_session()` context manager to `cli/_common.py`, consolidating login/logout boilerplate across 4 CLI modules
- Split `adapters/parsers.py` (1112 lines) into 5 focused submodules: `_errors`, `_truncation`, `_products`, `_input_builders`, `_mutations`
- Added `@lru_cache` to `get_default_cache_dir()` to avoid redundant platform detection
- Updated CLAUDE.md: removed stale `scripts/` references, updated CLI package structure, replaced `test-slow` with `testintegration`

### Removed
- Removed stale `tests/zpool_list_ok_sample.json` fixture from unrelated project

### Fixed
- README CI badge now points to correct workflow (`default_cicd_public.yml`)

## [2.0.3] - 2026-03-09

### Changed
- Migrated build tooling from `scripts/` to `bmk` (persistent uv tool)
- Updated CI integration test workflow to use `make testintegration`
- Bumped dependency minimum versions (filelock, orjson, ruff, bandit, textual, import-linter, hatchling)
- Fixed shell script formatting in `reset_git_history.sh` (4-space indent, shellcheck compliance)

### Removed
- Removed legacy `scripts/` directory (replaced by bmk)
- Removed obsolete `test_scripts.py`

### Fixed
- Registered `local_only` pytest marker in `pyproject.toml` to suppress warnings
- Updated CI/CD runner and action versions

## [2.0.2] - 2026-02-13

### Changed
- Updated CI/CD workflows (GitHub Actions metadata extraction, macOS bash 4+ support)
- Restored devcontainer configuration

### Fixed
- Added CVE ignore entries for CVE-2026-1703, CVE-2026-25990, CVE-2026-26007 in pip-audit
- Updated .gitignore to not exclude .devcontainer directory

## [2.0.1] - 2026-02-01

### Added
- `local_only` pytest marker to skip integration tests in CI environments (when `CI=true` or `CI=1`)
- All integration test classes now marked with both `@pytest.mark.integration` and `@pytest.mark.local_only`

## [2.0.0] - 2026-01-13

### Changed
- **Data Architecture Enforcement** - Replaced `dict[str, Any]` with typed Pydantic models throughout:
  - `GraphQLErrorLocation` - Typed model for error locations
  - `GraphQLErrorExtensions` - Typed model for error metadata with `extra="allow"`
  - `VariantMutationResult` - Typed variant mutation response
  - `VariantsBulkUpdateResponse` - Typed bulk update response wrapper
  - `TruncationInfo`, `TruncationFields`, `FieldTruncationInfo` - Truncation analysis models
  - `StagedUploadParameter` - Typed staged upload parameters
  - `_AdaptersCache` TypedDict for type-safe adapter storage

- **Consolidated StrEnum compatibility** to single `_compat.py` module for Python 3.10 support

- **Updated parsers to return typed models**:
  - `parse_variant_from_mutation()` accepts `VariantMutationResult` model
  - `parse_staged_upload_target()` returns `StagedUploadTarget` model
  - `get_truncation_info()` returns `TruncationInfo` model

- **StagedUploadTarget.parameters** changed from `dict[str, str]` to `list[StagedUploadParameter]`
  - Added `get_parameters_dict()` method for boundary conversion

### Removed
- Removed `cast()` calls in adapter cache - TypedDict provides proper typing
- Removed duplicate StrEnum compatibility shims (consolidated to `_compat.py`)

## [Unreleased]

## [2.0.9] 2026-08-01 00:43:58
### Fixed
- **Console output no longer crashes on a legacy codepage.** A Windows console at codepage 1252
  hands Python an `errors="strict"` stream, so writing a non-ASCII character such as a check mark
  raised `UnicodeEncodeError: 'charmap' codec can't encode character` and the command exited
  non-zero *after* its work had already succeeded. Click does not protect against this, and Rich
  raises the same way through its own writer. The new `safe_console` module degrades at the sink:
  a UTF-8 terminal still receives the character, and only a stream that cannot encode it sees
  `[OK]` / `[X]` / `[!]`. Every `click.echo` call site routes through it, and a test fails if a
  module reaches for `click.echo` or builds an unwrapped `Console(file=sys.stdout)` again.


## [2.0.8] 2026-07-24 17:56:44

## [2.0.7] 2026-06-14 21:48:55

## [2.0.6] 2026-06-01 14:06:00

## [2.0.5] 2026-04-24 12:02:07

## [2.0.4] 2026-03-09 13:03:28

## [2.0.3] 2026-03-09 11:52:50

### Added
- `test-slow` target added to interactive TUI menu for running integration tests


## [1.0.0] - 2026-01-13

### Added
- **Clean Architecture refactoring** with layered separation:
  - `domain/` - Core domain layer (pure Python, no external dependencies)
  - `application/` - Application layer with Protocol-based port interfaces
  - `adapters/` - Adapter implementations for Shopify SDK
  - `composition.py` - Composition root for dependency injection

- **Port interfaces (Protocols)** for testability and DI:
  - `TokenProviderPort` - OAuth token provider interface
  - `GraphQLClientPort` - GraphQL query execution interface
  - `SessionManagerPort` - Session lifecycle management interface

- **Adapter implementations** in `adapters/shopify_sdk.py`:
  - `ShopifyTokenProvider` - OAuth client credentials grant implementation
  - `ShopifyGraphQLClient` - GraphQL query executor using Shopify SDK
  - `ShopifySessionManager` - Session activation/deactivation

- **Dependency injection support**:
  - `create_adapters()` - Factory for adapter bundles
  - `get_default_adapters()` - Singleton default adapters
  - `AdapterBundle` - TypedDict for all adapters
  - `login()` now accepts optional adapter parameters for custom implementations

- **import-linter contracts** to enforce architecture boundaries:
  - Clean Architecture layers (adapters -> application -> domain)
  - Domain has no framework dependencies (no shopify, pydantic)
  - Application ports have no adapter dependencies

- **Comprehensive API documentation** in README.md:
  - Full parameter tables for all functions and models
  - Default values documented for all attributes
  - Code examples for all major use cases
  - Architecture overview with layer diagram


## [0.0.1] - 2026-01-08
- Initial project setup from template
- OAuth 2.0 Client Credentials Grant authentication
- GraphQL product queries with typed Pydantic models
- CLI with rich-click styling
- Layered configuration with lib_layered_config
- Rich structured logging with lib_log_rich
