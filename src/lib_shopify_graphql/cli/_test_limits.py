"""Test limits CLI command.

This module provides the test-limits command for analyzing
GraphQL query limits and detecting data truncation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import lib_log_rich.runtime
import rich_click as click

from ..adapters.parsers import get_truncation_info
from ..adapters.queries import PRODUCTS_LIST_QUERY, get_limits_from_config
from ..exceptions import AuthenticationError, GraphQLError
from ..shopify_client import ShopifySession
from ._common import CLICK_CONTEXT_SETTINGS, get_effective_config_and_profile

if TYPE_CHECKING:
    from ..models._operations import TruncationInfo

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class _FieldMaxInfo:
    """Tracks maximum value info for a single field type."""

    count: int = 0
    product: str | None = None
    truncated: bool = False


def _empty_truncation_list() -> list[TruncationInfo]:
    """Create empty truncation issues list (typed factory for pyright)."""
    return []


def _empty_max_values_dict() -> dict[str, _FieldMaxInfo]:
    """Create empty max values dict (typed factory for pyright)."""
    return {}


@dataclass
class _TruncationAnalysis:
    """Results of analyzing products for truncation."""

    truncation_issues: list[TruncationInfo] = field(default_factory=_empty_truncation_list)
    max_values: dict[str, _FieldMaxInfo] = field(default_factory=_empty_max_values_dict)
    total_products: int = 0

    def __post_init__(self) -> None:
        """Initialize max_values with all tracked fields."""
        if not self.max_values:
            for field_name in ("images", "media", "metafields", "variants", "variant_metafields"):
                self.max_values[field_name] = _FieldMaxInfo()


# =============================================================================
# Display Helpers
# =============================================================================


def _display_current_limits(limits: Any) -> None:
    """Display current GraphQL limits configuration."""
    click.echo("Current Product GraphQL Limits:")
    click.echo("─" * 50)
    click.echo(f"  product_max_images:             {limits.product_max_images}")
    click.echo(f"  product_max_media:              {limits.product_max_media}")
    click.echo(f"  product_max_options:            {limits.product_max_options}")
    click.echo(f"  product_max_metafields:         {limits.product_max_metafields}")
    click.echo(f"  product_max_variants:           {limits.product_max_variants}")
    click.echo(f"  product_max_variant_metafields: {limits.product_max_variant_metafields}")
    click.echo(f"  product_iter_page_size:         {limits.product_iter_page_size}")
    click.echo()


def _display_max_values(analysis: _TruncationAnalysis, limits: Any) -> None:
    """Display maximum values found during analysis."""
    click.echo("Maximum Values Found:")
    click.echo("─" * 70)

    field_configs = [
        ("images", "images            ", limits.product_max_images),
        ("media", "media             ", limits.product_max_media),
        ("metafields", "metafields        ", limits.product_max_metafields),
        ("variants", "variants          ", limits.product_max_variants),
        ("variant_metafields", "variant_metafields", limits.product_max_variant_metafields),
    ]

    for field_name, display_name, field_limit in field_configs:
        info = analysis.max_values[field_name]
        product = info.product or "N/A"
        truncated_suffix = " (TRUNCATED!)" if info.truncated else ""
        status = "✗" if info.truncated else ("⚠" if info.count >= field_limit else "✓")
        click.echo(f"  {status} {display_name}: {info.count:4d}/{field_limit}{truncated_suffix}")
        click.echo(f"      Max on: {product}")

    click.echo()


def _display_truncation_issues(issues: list[TruncationInfo]) -> dict[str, list[tuple[str, str, int]]]:
    """Display individual truncation issues and return field summary."""
    click.echo(f"✗ TRUNCATION DETECTED in {len(issues)} product(s):")
    click.echo("  Data is being lost! Increase the affected limits.")
    click.echo()

    field_summary: dict[str, list[tuple[str, str, int]]] = {}

    for info in issues:
        product_id = info.product_id
        title = info.product_title
        short_id = product_id.split("/")[-1] if "/" in product_id else product_id

        # Iterate through fields using model attributes
        fields_data = [
            ("images", info.fields.images),
            ("media", info.fields.media),
            ("metafields", info.fields.metafields),
            ("variants", info.fields.variants),
            ("variant_metafields", info.fields.variant_metafields),
        ]

        for field_name, field_info in fields_data:
            if not field_info.truncated:
                continue
            field_summary.setdefault(field_name, []).append((title, short_id, field_info.count))
            click.echo(f"  Product: '{title}' (ID: {short_id})")
            click.echo(f"    {field_name}: {field_info.count}+ items (TRUNCATED)")
            if field_info.cost_warning:
                click.echo(f"    ⚠ {field_info.cost_warning}")
            click.echo()

    return field_summary


def _find_config_info(field_name: str, truncation_issues: list[TruncationInfo]) -> tuple[str | None, str | None]:
    """Find config key and env var for a truncated field."""
    for info in truncation_issues:
        field_info = getattr(info.fields, field_name, None)
        if field_info is not None and field_info.truncated:
            return field_info.config_key, field_info.env_var
    return None, None


def _display_recommendations(
    field_summary: dict[str, list[tuple[str, str, int]]],
    truncation_issues: list[TruncationInfo],
    limits: Any,
) -> None:
    """Display recommendations for fixing truncation issues."""
    click.echo("─" * 50)
    click.echo("REQUIRED CHANGES:")
    click.echo()

    for field_name, affected in field_summary.items():
        max_truncated = max(count for _, _, count in affected)
        config_key, env_var = _find_config_info(field_name, truncation_issues)
        suggested = max(max_truncated + 10, int(max_truncated * 1.5))

        click.echo(f"  {field_name.upper()}: {len(affected)} product(s) truncated")
        click.echo(f"    Current limit: {getattr(limits, config_key, '?') if config_key else '?'}")
        click.echo(f"    Max found: {max_truncated}+ (actual count unknown)")
        click.echo(f"    Suggested: {suggested}")
        click.echo(f"    → Set [graphql] {config_key} = {suggested}")
        click.echo(f"    → Or: {env_var}={suggested}")
        click.echo()

    click.echo("WARNING: When increasing limits for list operations (list_products,")
    click.echo("iter_products), monitor for MAX_COST_EXCEEDED errors. You may need to")
    click.echo("reduce page_size or use get_product_by_id for products with many items.")


# =============================================================================
# Analysis Logic
# =============================================================================


def _update_max_values(analysis: _TruncationAnalysis, info: TruncationInfo) -> None:
    """Update max values tracking from a single product's truncation info."""
    product_id = info.product_id
    title = info.product_title
    short_id = product_id.split("/")[-1] if "/" in product_id else product_id
    product_label = f"'{title}' (ID: {short_id})"

    # Iterate through fields using model attributes
    fields_data = [
        ("images", info.fields.images),
        ("media", info.fields.media),
        ("metafields", info.fields.metafields),
        ("variants", info.fields.variants),
        ("variant_metafields", info.fields.variant_metafields),
    ]

    for field_name, field_info in fields_data:
        current = analysis.max_values[field_name]
        if field_info.count > current.count:
            analysis.max_values[field_name] = _FieldMaxInfo(
                count=field_info.count,
                product=product_label,
                truncated=field_info.truncated,
            )
        elif field_info.count == current.count and field_info.truncated:
            current.truncated = True


def _analyze_products(
    session: ShopifySession,
    limits: Any,
    query: str | None,
    max_products: int | None,
) -> _TruncationAnalysis:
    """Analyze products for truncation issues."""
    analysis = _TruncationAnalysis()
    cursor: str | None = None

    while True:
        variables: dict[str, Any] = {"first": limits.product_iter_page_size, "after": cursor, "query": query}
        raw_response = session.execute_graphql(PRODUCTS_LIST_QUERY, variables=variables)

        products_data = raw_response.get("data", {}).get("products", {})
        product_nodes = products_data.get("nodes", [])
        page_info = products_data.get("pageInfo", {})

        if not product_nodes and analysis.total_products == 0:
            return analysis

        for product_data in product_nodes:
            info = get_truncation_info(product_data)
            _update_max_values(analysis, info)

            if info.truncated:
                analysis.truncation_issues.append(info)

            analysis.total_products += 1

            if max_products and analysis.total_products >= max_products:
                click.echo(f"\r  Analyzed {analysis.total_products} products...")
                return analysis

        click.echo(f"\r  Analyzed {analysis.total_products} products...", nl=False)

        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    click.echo()
    return analysis


# =============================================================================
# CLI Command
# =============================================================================


def register_test_limits_command(
    cli_group: click.Group,
    get_credentials_or_exit: Any,
    get_fix_suggestion: Any,
) -> None:
    """Register the test-limits command on the CLI group.

    Args:
        cli_group: The Click group to register the command on.
        get_credentials_or_exit: Function to get credentials from config.
        get_fix_suggestion: Function to get fix suggestions for errors.
    """

    @cli_group.command("test-limits", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.option("--profile", "-p", help="Named configuration profile to load")
    @click.option("--limit", "-n", type=int, default=None, help="Maximum products to analyze (default: all)")
    @click.option("--query", "-q", help="Optional Shopify search query to filter products")
    @click.pass_context
    def cli_test_limits(
        ctx: click.Context,
        profile: str | None,
        limit: int | None,
        query: str | None,
    ) -> None:
        """Test if current GraphQL limits are causing data truncation.

        Iterates through ALL products and uses pageInfo.hasNextPage to definitively
        detect if any nested collections (images, media, variants, metafields)
        are being truncated.

        Reports:
        - Which products have truncated data
        - Maximum counts found for each field across ALL products
        - Recommendations for which limits to increase
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "test-limits", "profile": effective_profile, "limit": limit}

        with lib_log_rich.runtime.bind(job_id="cli-test-limits", extra=extra):
            # Late import to allow tests to patch cli.login/logout
            from . import login, logout

            credentials = get_credentials_or_exit(config)
            limits = get_limits_from_config()

            _display_current_limits(limits)

            click.echo(f"Connecting to {credentials.shop_url}...")
            session = None
            try:
                session = login(credentials)
                click.echo("✓ Connected")
                click.echo()

                click.echo(f"Analyzing {'up to ' + str(limit) if limit else 'all'} products...")
                if query:
                    click.echo(f"  Filter: {query}")

                analysis = _analyze_products(session, limits, query, limit)

                if analysis.total_products == 0:
                    click.echo("No products found.")
                    return

                click.echo(f"✓ Analyzed {analysis.total_products} products")
                click.echo()

                _display_max_values(analysis, limits)

                if not analysis.truncation_issues:
                    click.echo("✓ No truncation detected!")
                    click.echo()
                    click.echo("All products returned complete data.")
                    click.echo("Your current configuration is sufficient for this catalog.")
                else:
                    field_summary = _display_truncation_issues(analysis.truncation_issues)
                    _display_recommendations(field_summary, analysis.truncation_issues, limits)
                    logger.warning(f"Truncation detected in {len(analysis.truncation_issues)} product(s)")
                    raise SystemExit(1)

            except (AuthenticationError, GraphQLError) as exc:
                click.echo(f"\n✗ Error: {exc}", err=True)
                click.echo(get_fix_suggestion(exc, credentials), err=True)
                raise SystemExit(1)
            finally:
                if session is not None and session.is_active:
                    logout(session)


__all__ = [
    "register_test_limits_command",
]
