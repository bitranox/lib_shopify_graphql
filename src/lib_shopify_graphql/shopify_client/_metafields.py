"""Metafield deletion operations for Shopify API.

This module provides metafield deletion functionality.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..adapters.mutations import METAFIELDS_DELETE_MUTATION
from ..adapters.parsers import (
    format_graphql_errors,
    parse_graphql_errors,
)
from ..exceptions import GraphQLError, SessionNotActiveError
from ..models import MetafieldDeleteFailure, MetafieldDeleteResult, MetafieldIdentifier
from ..models._operations import UserErrorData
from ._common import _normalize_owner_gid
from ._session import ShopifySession

logger = logging.getLogger(__name__)


# =============================================================================
# Internal Response Models
# =============================================================================


class _DeletedMetafieldData(BaseModel):
    """Parsed deleted metafield entry from GraphQL response.

    Internal model for typed parsing of deletedMetafields response.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    owner_id: str = Field(alias="ownerId")
    namespace: str
    key: str


class _MetafieldsDeleteMutationData(BaseModel):
    """Parsed metafieldsDelete mutation result.

    Internal model for typed parsing of the mutation response.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    deleted_metafields: list[_DeletedMetafieldData] = Field(default_factory=list[_DeletedMetafieldData], alias="deletedMetafields")
    user_errors: list[UserErrorData] = Field(default_factory=list[UserErrorData], alias="userErrors")


class _MetafieldsDeleteResponse(BaseModel):
    """Full response from metafieldsDelete mutation.

    Internal model for typed parsing of the full GraphQL response.
    """

    model_config = ConfigDict(frozen=True)

    data: dict[str, _MetafieldsDeleteMutationData] | None = None

    @property
    def mutation_data(self) -> _MetafieldsDeleteMutationData | None:
        """Get metafieldsDelete mutation data."""
        if self.data is None:
            return None
        return self.data.get("metafieldsDelete")


def _build_metafield_delete_input(
    metafields: list[MetafieldIdentifier],
) -> list[dict[str, str]]:
    """Build GraphQL input for metafield deletion."""
    return [
        {
            "ownerId": _normalize_owner_gid(mf.owner_id),
            "namespace": mf.namespace,
            "key": mf.key,
        }
        for mf in metafields
    ]


def _parse_deleted_metafields(
    deleted_data: list[_DeletedMetafieldData],
) -> list[MetafieldIdentifier]:
    """Parse deletedMetafields response into MetafieldIdentifier list."""
    return [
        MetafieldIdentifier(
            owner_id=item.owner_id,
            namespace=item.namespace,
            key=item.key,
        )
        for item in deleted_data
    ]


def _find_identifier_for_error(
    field_path: list[str],
    metafields: list[MetafieldIdentifier],
) -> MetafieldIdentifier | None:
    """Find the MetafieldIdentifier associated with a user error.

    Args:
        field_path: Error field path from Shopify (e.g., ["metafields", "0", "key"]).
            Array indices are normalized to strings by UserErrorData.
        metafields: Original list of metafield identifiers.

    Returns:
        The matching MetafieldIdentifier, or None if not found.
    """
    if len(field_path) >= 2 and field_path[0] == "metafields":
        idx_str = field_path[1]
        # Array indices are normalized to strings, try parsing as int
        try:
            idx = int(idx_str)
        except ValueError:
            return None
        if 0 <= idx < len(metafields):
            return metafields[idx]
    return None


def _check_metafields_graphql_errors(data: dict[str, Any]) -> None:
    """Check for GraphQL-level errors in metafield deletion response."""
    if "errors" not in data:
        return
    parsed_errors = parse_graphql_errors(data["errors"])
    raise GraphQLError(
        f"GraphQL errors: {format_graphql_errors(parsed_errors)}",
        errors=parsed_errors,
        query=METAFIELDS_DELETE_MUTATION,
    )


def _create_unknown_identifier() -> MetafieldIdentifier:
    """Create a placeholder identifier for unmatched errors."""
    return MetafieldIdentifier(owner_id="unknown", namespace="unknown", key="unknown")


def _process_delete_user_errors(
    user_errors: list[UserErrorData],
    metafields: list[MetafieldIdentifier],
) -> list[MetafieldDeleteFailure]:
    """Process user errors from deletion mutation into failures."""
    failed: list[MetafieldDeleteFailure] = []
    for error in user_errors:
        identifier = _find_identifier_for_error(error.field, metafields)
        if identifier is None:
            identifier = _create_unknown_identifier()
        failed.append(
            MetafieldDeleteFailure(
                identifier=identifier,
                error=error.message,
                error_code=error.code,
            )
        )
    return failed


def delete_metafield(
    session: ShopifySession,
    owner_id: str,
    namespace: str,
    key: str,
) -> bool:
    """Delete a single metafield by owner + namespace + key.

    This is a convenience wrapper around :func:`delete_metafields` for
    single deletions. The operation is idempotent - deleting a non-existent
    metafield returns False (not an error).

    Args:
        session: An active ShopifySession.
        owner_id: Owner GID (e.g., 'gid://shopify/Product/123' or
            'gid://shopify/ProductVariant/456'). Numeric IDs are
            assumed to be Product IDs.
        namespace: Metafield namespace (e.g., 'custom').
        key: Metafield key within the namespace.

    Returns:
        True if the metafield was deleted, False if it didn't exist.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the deletion fails with an error.

    Example:
        >>> from lib_shopify_graphql import login, delete_metafield
        >>> session = login(credentials)  # doctest: +SKIP
        >>> deleted = delete_metafield(
        ...     session,
        ...     owner_id="gid://shopify/Product/123",
        ...     namespace="custom",
        ...     key="warranty_months",
        ... )  # doctest: +SKIP
        >>> if deleted:  # doctest: +SKIP
        ...     logger.info("Metafield deleted")  # doctest: +SKIP
    """
    identifier = MetafieldIdentifier(
        owner_id=owner_id,
        namespace=namespace,
        key=key,
    )
    result = delete_metafields(session, [identifier])

    if result.failed:
        # Raise the first error as a GraphQLError
        failure = result.failed[0]
        raise GraphQLError(
            f"Failed to delete metafield: {failure.error}",
            query=METAFIELDS_DELETE_MUTATION,
        )

    return result.deleted_count > 0


def delete_metafields(
    session: ShopifySession,
    metafields: list[MetafieldIdentifier],
) -> MetafieldDeleteResult:
    """Delete multiple metafields in one API call.

    Deletes metafields identified by owner + namespace + key. The operation
    is partially idempotent - deleting non-existent metafields is not an
    error (they simply won't appear in the deleted list).

    Args:
        session: An active ShopifySession.
        metafields: List of MetafieldIdentifier objects specifying which
            metafields to delete.

    Returns:
        MetafieldDeleteResult containing lists of successfully deleted
        metafields and any failures.

    Raises:
        SessionNotActiveError: If the session is not active.
        GraphQLError: If the entire mutation fails (e.g., auth error).

    Example:
        >>> from lib_shopify_graphql import (
        ...     login, delete_metafields, MetafieldIdentifier
        ... )
        >>> session = login(credentials)  # doctest: +SKIP
        >>> result = delete_metafields(session, [
        ...     MetafieldIdentifier(
        ...         owner_id="gid://shopify/Product/123",
        ...         namespace="custom",
        ...         key="old_field_1",
        ...     ),
        ...     MetafieldIdentifier(
        ...         owner_id="gid://shopify/Product/123",
        ...         namespace="custom",
        ...         key="old_field_2",
        ...     ),
        ... ])  # doctest: +SKIP
        >>> logger.info(
        ...     "Deletion complete",
        ...     extra={"deleted": result.deleted_count, "failed": result.failed_count},
        ... )  # doctest: +SKIP
    """
    if not session.is_active:
        raise SessionNotActiveError("Session is not active. Please login first.")

    if not metafields:
        return MetafieldDeleteResult(deleted=[], failed=[])

    logger.info(f"Deleting {len(metafields)} metafield(s) on shop '{session.get_credentials().shop_url}'")

    try:
        mutation_input = _build_metafield_delete_input(metafields)
        raw_data = session.execute_graphql(
            METAFIELDS_DELETE_MUTATION,
            variables={"metafields": mutation_input},
        )

        _check_metafields_graphql_errors(raw_data)

        # Parse response with Pydantic model for typed access
        response = _MetafieldsDeleteResponse.model_validate(raw_data)
        mutation_data = response.mutation_data
        if mutation_data is None:
            # Should not happen after GraphQL error check, but handle defensively
            return MetafieldDeleteResult(deleted=[], failed=[])

        deleted = _parse_deleted_metafields(mutation_data.deleted_metafields)
        failed = _process_delete_user_errors(mutation_data.user_errors, metafields)

        logger.info(f"Metafield deletion complete: {len(deleted)} deleted, {len(failed)} failed")
        return MetafieldDeleteResult(deleted=deleted, failed=failed)

    except GraphQLError:
        raise
    except Exception as exc:
        logger.error("Failed to delete metafields", extra={"error": str(exc)})
        raise GraphQLError(f"Failed to delete metafields: {exc}", query=METAFIELDS_DELETE_MUTATION) from exc


__all__ = [
    "delete_metafield",
    "delete_metafields",
]
