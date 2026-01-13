"""Internal utilities for partial update support.

This module provides the UNSET sentinel and type utilities for distinguishing
between "don't update" and "set to null" in partial update operations.
"""

from __future__ import annotations

import ipaddress
from typing import TypeVar, Union


class UnsetType:
    """Sentinel indicating a field should not be updated.

    Used in partial update models to distinguish between:
    - UNSET: Don't update this field (skip in mutation)
    - None: Clear this field (set to null on Shopify)
    - value: Update to this value

    Example:
        >>> from lib_shopify_graphql import UNSET, VariantUpdate
        >>> # Update price only, leave other fields unchanged
        >>> update = VariantUpdate(price=Decimal("29.99"))
        >>> update.barcode is UNSET
        True
    """

    _instance: UnsetType | None = None

    def __new__(cls) -> UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False

    def __copy__(self) -> UnsetType:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> UnsetType:
        return self


UNSET = UnsetType()
"""Singleton sentinel indicating a field should not be updated."""

# Type variable for generic Updatable type
_T = TypeVar("_T")

# Type alias for optional update fields
# Usage: Updatable[Decimal] can be Decimal | None | UnsetType
Updatable = Union[_T, None, UnsetType]
"""Type alias for fields in partial update models.

- ``value``: Update the field to this value
- ``None``: Clear the field (set to null on Shopify)
- ``UNSET``: Skip this field (don't send in mutation)
"""


def _normalize_shop_url(url: str) -> str:
    """Normalize Shopify store URL by stripping protocol and trailing slash."""
    url = url.strip().lower()
    url = url.removeprefix("https://").removeprefix("http://")
    return url.removesuffix("/")


def _check_domain_format(url: str) -> None:
    """Validate basic domain format."""
    if "." not in url or " " in url:
        msg = "shop_url must be a valid domain (e.g., 'mystore.myshopify.com' or 'shop.example.com')"
        raise ValueError(msg)


def _check_localhost(hostname: str) -> None:
    """Reject localhost hostnames."""
    if hostname in ("localhost", "localhost.localdomain"):
        msg = "shop_url cannot be localhost (SSRF protection)"
        raise ValueError(msg)


def _check_private_ip(hostname: str) -> None:
    """Reject private/loopback/reserved IP addresses."""
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return  # Not an IP address, domain name is fine

    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        msg = f"shop_url cannot be a private, loopback, or reserved IP address: {hostname}"
        raise ValueError(msg)


def _validate_shopify_domain(url: str) -> str:
    """Validate URL is a valid domain with SSRF protection."""
    _check_domain_format(url)
    hostname = url.split(":")[0]
    _check_localhost(hostname)
    _check_private_ip(hostname)
    return url


__all__ = [
    "UNSET",
    "UnsetType",
    "Updatable",
    "_normalize_shop_url",
    "_validate_shopify_domain",
]
