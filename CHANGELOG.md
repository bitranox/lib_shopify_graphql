# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.


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
