"""GraphQL error parsing and formatting.

Converts raw GraphQL error responses into structured models
and provides formatting utilities.
"""

from __future__ import annotations

from typing import Any

from ...exceptions import GraphQLErrorEntry, GraphQLErrorLocation


def _parse_graphql_error_location(loc_data: dict[str, Any]) -> GraphQLErrorLocation:
    """Parse a single error location from raw data."""
    return GraphQLErrorLocation(
        line=loc_data.get("line", 0),
        column=loc_data.get("column", 0),
    )


def _parse_single_graphql_error(error_data: dict[str, Any]) -> GraphQLErrorEntry:
    """Parse a single GraphQL error from raw API data."""
    locations_raw = error_data.get("locations")
    locations: tuple[GraphQLErrorLocation, ...] | None = None
    if locations_raw:
        locations = tuple(_parse_graphql_error_location(loc) for loc in locations_raw)

    path_raw = error_data.get("path")
    path: tuple[str | int, ...] | None = None
    if path_raw:
        path = tuple(path_raw)

    return GraphQLErrorEntry(
        message=error_data.get("message", "Unknown error"),
        locations=locations,
        path=path,
        extensions=error_data.get("extensions"),
    )


def parse_graphql_errors(errors_data: list[dict[str, Any]]) -> list[GraphQLErrorEntry]:
    """Parse GraphQL errors from API response into structured models."""
    return [_parse_single_graphql_error(error) for error in errors_data]


def format_graphql_error(error: GraphQLErrorEntry) -> str:
    """Format a single GraphQL error with its extension code if available.

    Args:
        error: Parsed GraphQL error entry.

    Returns:
        Formatted error string including code if present.

    Example:
        >>> error = GraphQLErrorEntry(message="Rate limited", extensions={"code": "THROTTLED"})
        >>> format_graphql_error(error)
        '[THROTTLED] Rate limited'
    """
    code = None
    if error.extensions:
        code = error.extensions.get("code")

    if code:
        return f"[{code}] {error.message}"
    return error.message


def format_graphql_errors(errors: list[GraphQLErrorEntry]) -> str:
    """Format multiple GraphQL errors into a single string.

    Includes error codes from extensions and path information.

    Args:
        errors: List of parsed GraphQL error entries.

    Returns:
        Semicolon-separated formatted error messages.

    Example:
        >>> errors = parse_graphql_errors([{"message": "Not found", "path": ["product"]}])
        >>> format_graphql_errors(errors)
        'Not found (at product)'
    """
    formatted: list[str] = []
    for error in errors:
        msg = format_graphql_error(error)
        if error.path:
            path_str = ".".join(str(p) for p in error.path)
            msg = f"{msg} (at {path_str})"
        formatted.append(msg)
    return "; ".join(formatted)


__all__ = [
    "format_graphql_error",
    "format_graphql_errors",
    "parse_graphql_errors",
]
