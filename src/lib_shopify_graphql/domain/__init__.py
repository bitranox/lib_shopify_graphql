"""Domain layer - core business entities and rules.

This layer contains:
    - Domain exceptions (pure Python, no framework dependencies)
    - Value objects and entities (if needed)

The domain layer is the innermost layer and has no dependencies
on outer layers (adapters, frameworks, I/O).

Note:
    For this library, domain exceptions are exposed via the public
    API (exceptions module) where Pydantic models for error details
    are also defined. This keeps the public API simple while
    maintaining architectural boundaries for the core domain.

    Future domain entities and value objects can be added here
    as pure Python dataclasses.
"""

from __future__ import annotations

__all__: list[str] = []
