# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.


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
