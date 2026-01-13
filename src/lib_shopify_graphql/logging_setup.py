"""Centralized logging initialization for all entry points.

Provides a single source of truth for lib_log_rich runtime configuration,
eliminating duplication between module entry (__main__.py) and console script
(cli.py) while ensuring initialization happens exactly once.

Contents:
    * :func:`init_logging` – idempotent logging initialization with layered config.
    * :func:`_build_runtime_config` – constructs RuntimeConfig from layered sources.

System Role:
    Lives in the adapters/platform layer. All entry points (module execution,
    console scripts, tests) delegate to this module for logging setup, ensuring
    consistent runtime behavior across invocation paths.
"""

from __future__ import annotations

from typing import Any

import lib_log_rich.config
import lib_log_rich.runtime
from lib_layered_config import Config

from . import __init__conf__


def _build_runtime_config(config: Config) -> lib_log_rich.runtime.RuntimeConfig:
    """Build RuntimeConfig from a Config object.

    Centralizes the mapping from lib_layered_config to lib_log_rich
    RuntimeConfig. Extracts the [lib_log_rich] section from the provided
    configuration and applies defaults for required parameters.

    Args:
        config: Already-loaded layered configuration object.

    Returns:
        Fully configured runtime settings ready for lib_log_rich.init().

    Note:
        Configuration is read from the [lib_log_rich] section. All parameters
        documented in defaultconfig.toml can be specified. Unspecified values
        use lib_log_rich's built-in defaults. The service and environment
        parameters default to package metadata when not configured.
    """
    log_config_raw: Any = config.get("lib_log_rich", default={})
    log_config: dict[str, Any] = dict(log_config_raw) if log_config_raw else {}

    # Apply defaults for required fields
    if "service" not in log_config:
        log_config["service"] = __init__conf__.name
    if "environment" not in log_config:
        log_config["environment"] = "prod"

    return lib_log_rich.runtime.RuntimeConfig(**log_config)


def init_logging(config: Config) -> None:
    """Initialize lib_log_rich runtime with the provided configuration.

    All entry points need logging configured, but the runtime should only
    be initialized once regardless of how many times this function is called.
    Loads .env files (to make LOG_* variables available), checks if lib_log_rich
    is already initialized, and configures it with settings from the provided
    Config object. Bridges standard Python logging to lib_log_rich for domain
    code compatibility.

    Args:
        config: Already-loaded layered configuration object containing logging
            settings in the [lib_log_rich] section.

    Side Effects:
        Loads .env files into the process environment on first invocation.
        May initialize the global lib_log_rich runtime on first invocation.
        Subsequent calls have no effect.

    Note:
        This function is safe to call multiple times. The first call loads .env
        and initializes the runtime; subsequent calls check the initialization
        state and return immediately if already initialized.

        The .env loading enables lib_log_rich to read LOG_* environment variables
        from .env files in the current directory or parent directories. This
        provides the highest precedence override mechanism for logging configuration.
    """
    if not lib_log_rich.runtime.is_initialised():
        lib_log_rich.config.enable_dotenv()
        runtime_config = _build_runtime_config(config)
        lib_log_rich.runtime.init(runtime_config)
        lib_log_rich.runtime.attach_std_logging()


__all__ = [
    "init_logging",
]
