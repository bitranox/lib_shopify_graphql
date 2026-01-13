"""Health check CLI command.

This module provides the health check command for verifying
Shopify API connectivity and credentials.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.error import URLError

import lib_log_rich.runtime
import rich_click as click
from lib_layered_config import Config

from ..exceptions import AuthenticationError, GraphQLError
from ..models import ShopifyCredentials
from ..shopify_client import login, logout
from ._common import CLICK_CONTEXT_SETTINGS, get_effective_config_and_profile

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Health Check Result
# =============================================================================


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    """Result of a Shopify health check operation.

    Attributes:
        success: Whether the health check passed.
        shop_name: Connected shop name (on success).
        shop_url: Shopify store URL.
        api_version: API version used.
        token_expiration: When the token expires (on success).
        error_type: Exception type name (on failure).
        error_message: Human-readable error message (on failure).
        fix_suggestion: Actionable steps to resolve the issue (on failure).
    """

    success: bool
    shop_name: str | None = None
    shop_url: str | None = None
    api_version: str | None = None
    token_expiration: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    fix_suggestion: str | None = None


# =============================================================================
# Credentials Helpers
# =============================================================================


def extract_shopify_credentials_from_config(config: Config) -> ShopifyCredentials:
    """Extract and validate Shopify credentials from configuration.

    Args:
        config: Loaded layered configuration.

    Returns:
        Valid ShopifyCredentials object.

    Raises:
        ValueError: If required credentials are missing or incomplete.
    """
    shop_url = config.get("shopify.shop_url", default="")
    client_id = config.get("shopify.client_id", default="")
    client_secret = config.get("shopify.client_secret", default="")
    api_version = config.get("shopify.api_version", default="2026-01")

    missing: list[str] = []
    if not shop_url:
        missing.append("shopify.shop_url")
    if not client_id:
        missing.append("shopify.client_id")
    if not client_secret:
        missing.append("shopify.client_secret")

    if missing:
        raise ValueError(f"Missing required credentials: {', '.join(missing)}")

    return ShopifyCredentials(
        shop_url=shop_url,
        client_id=client_id,
        client_secret=client_secret,
        api_version=api_version,
    )


def get_fix_suggestion(error: Exception, credentials: ShopifyCredentials | None) -> str:
    """Generate actionable fix suggestion based on error type.

    Args:
        error: The caught exception.
        credentials: Credentials that failed (for context in messages).

    Returns:
        User-friendly suggestion for fixing the issue.
    """
    shop_url = credentials.shop_url if credentials else "your-store.myshopify.com"

    if isinstance(error, ValueError) and "Missing required credentials" in str(error):
        return (
            "Configure credentials via:\n"
            "  1. .env file:\n"
            "     SHOPIFY__SHOP_URL=yourstore.myshopify.com\n"
            "     SHOPIFY__CLIENT_ID=your_client_id\n"
            "     SHOPIFY__CLIENT_SECRET=your_client_secret\n\n"
            "  2. Or config file (~/.config/lib-shopify-graphql/config.toml):\n"
            "     [shopify]\n"
            '     shop_url = "yourstore.myshopify.com"\n'
            '     client_id = "your_client_id"\n'
            '     client_secret = "your_client_secret"'
        )

    if isinstance(error, AuthenticationError):
        return (
            f"  1. Verify client_id and client_secret are correct\n"
            f"  2. Check the app is installed on {shop_url}\n"
            f"  3. Ensure the app has not been revoked or disabled\n"
            f"  4. Get credentials from: https://dev.shopify.com/dashboard"
        )

    if isinstance(error, GraphQLError):
        return "  1. Check your API version is valid\n  2. Verify the app has required API scopes\n  3. Check Shopify status: https://status.shopify.com"

    if isinstance(error, (URLError, TimeoutError, OSError)):
        return (
            f"  1. Check your network connection\n"
            f"  2. Verify the shop URL is correct: {shop_url}\n"
            f"  3. Ensure https://{shop_url} is accessible\n"
            "  4. Check Shopify status: https://status.shopify.com"
        )

    return "  1. Check your configuration and credentials\n  2. Ensure network connectivity\n  3. Check Shopify status: https://status.shopify.com"


def get_credentials_or_exit(config: Config) -> ShopifyCredentials:
    """Extract credentials from config or exit with error message.

    Convenience wrapper that handles the common pattern of extracting
    credentials and displaying a user-friendly error on failure.
    """
    try:
        return extract_shopify_credentials_from_config(config)
    except ValueError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        click.echo(get_fix_suggestion(exc, None), err=True)
        raise SystemExit(1)


# =============================================================================
# Health Check Logic
# =============================================================================


def execute_health_check(credentials: ShopifyCredentials) -> HealthCheckResult:
    """Execute health check: login, get shop info, logout.

    Args:
        credentials: Valid ShopifyCredentials to test.

    Returns:
        HealthCheckResult with success/failure details.
    """
    session = None
    try:
        session = login(credentials)

        # Get shop name via query (login already verified, but we need the name)
        data = session.execute_graphql("{ shop { name } }")
        shop_name = data.get("data", {}).get("shop", {}).get("name", "Unknown")

        logout(session)

        return HealthCheckResult(
            success=True,
            shop_name=shop_name,
            shop_url=credentials.shop_url,
            api_version=credentials.api_version,
            token_expiration=session.info.token_expiration,
        )

    except Exception as exc:
        # Ensure session is cleaned up on failure
        if session is not None and session.is_active:
            try:
                logout(session)
            except Exception as logout_exc:  # noqa: BLE001
                # Cleanup errors are secondary; log but don't mask original error
                logger.debug("Cleanup logout failed: %s", logout_exc)

        return HealthCheckResult(
            success=False,
            shop_url=credentials.shop_url,
            api_version=credentials.api_version,
            error_type=type(exc).__name__,
            error_message=str(exc),
            fix_suggestion=get_fix_suggestion(exc, credentials),
        )


def format_health_output(result: HealthCheckResult) -> None:
    """Print health check result with formatting.

    Args:
        result: HealthCheckResult to display.
    """
    click.echo("\nShopify Health Check")
    click.echo("─" * 40)

    if result.success:
        click.echo(f"  Shop:           {result.shop_name}")
        click.echo(f"  Shop URL:       {result.shop_url}")
        click.echo(f"  API Version:    {result.api_version}")
        if result.token_expiration:
            expiry_str = result.token_expiration.strftime("%Y-%m-%d %H:%M:%S UTC")
            click.echo(f"  Token Expires:  {expiry_str}")
        click.echo("")
        click.echo("✓ Connection successful.")
    else:
        click.echo(f"✗ ERROR: {result.error_type}", err=True)
        click.echo("", err=True)
        click.echo(f"  Error: {result.error_message}", err=True)
        if result.shop_url:
            click.echo(f"  Shop:  {result.shop_url}", err=True)
        click.echo("", err=True)
        click.echo("To fix:", err=True)
        click.echo(result.fix_suggestion, err=True)


# =============================================================================
# CLI Command
# =============================================================================


def register_health_command(cli_group: click.Group) -> None:
    """Register the health command on the CLI group.

    Args:
        cli_group: The Click group to register the command on.
    """

    @cli_group.command("health", context_settings=CLICK_CONTEXT_SETTINGS)
    @click.option(
        "--profile",
        type=str,
        default=None,
        help="Override profile from root command (e.g., 'production', 'test')",
    )
    @click.pass_context
    def cli_health(ctx: click.Context, profile: str | None) -> None:
        r"""Check Shopify API connectivity and credentials.

        Attempts to connect to Shopify using configured credentials,
        verifies the connection works, then cleanly disconnects.

        On success, displays:
        - Connected shop name
        - API version in use
        - Token expiration time

        On failure, displays:
        - Error type and message
        - Actionable steps to resolve the issue

        \b
        Configuration sources (precedence order):
        - .env file: SHOPIFY__SHOP_URL, SHOPIFY__CLIENT_ID, SHOPIFY__CLIENT_SECRET
        - Environment: LIB_SHOPIFY_GRAPHQL___SHOPIFY__SHOP_URL, etc.
        - Config files: ~/.config/lib-shopify-graphql/config.toml

        Examples:
            \b
            # Check default profile connectivity
            $ lib-shopify-graphql health

            \b
            # Check production profile
            $ lib-shopify-graphql health --profile production
        """
        config, effective_profile = get_effective_config_and_profile(ctx, profile)
        extra = {"command": "health", "profile": effective_profile}

        with lib_log_rich.runtime.bind(job_id="cli-health", extra=extra):
            logger.info(f"Starting Shopify health check for profile '{effective_profile}'")

            # Extract and validate credentials
            credentials: ShopifyCredentials | None = None
            try:
                credentials = extract_shopify_credentials_from_config(config)
            except ValueError as exc:
                result = HealthCheckResult(
                    success=False,
                    error_type="ConfigurationError",
                    error_message=str(exc),
                    fix_suggestion=get_fix_suggestion(exc, None),
                )
                format_health_output(result)
                raise SystemExit(1)

            # Execute health check
            result = execute_health_check(credentials)
            format_health_output(result)

            if result.success:
                logger.info(f"Health check passed for shop '{result.shop_name}'")
            else:
                logger.warning(f"Health check failed: {result.error_type} - {result.error_message}")
                raise SystemExit(1)


__all__ = [
    "HealthCheckResult",
    "extract_shopify_credentials_from_config",
    "get_fix_suggestion",
    "get_credentials_or_exit",
    "execute_health_check",
    "format_health_output",
    "register_health_command",
]
