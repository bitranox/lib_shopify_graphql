"""Python version compatibility utilities.

This module provides backports for features not available in all supported
Python versions. The library supports Python 3.10+, but some standard library
features (like StrEnum) were added in Python 3.11.

Note:
    This is the ONLY place compatibility shims should be defined.
    All modules should import from here, not define their own shims.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):  # noqa: UP036 - intentional, we support Python 3.10
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of StrEnum for Python 3.10.

        StrEnum was added in Python 3.11. This provides equivalent
        functionality for Python 3.10 users.
        """

        def __str__(self) -> str:
            return str(self.value)


__all__ = ["StrEnum"]
