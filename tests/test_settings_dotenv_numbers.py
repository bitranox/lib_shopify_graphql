"""Digit-only .env values reach every text setting as the text the operator wrote.

lib_layered_config's dotenv and environment layers turn an unquoted value into an int whenever
that number reads back as the same text (``123456`` stays ``123456``). A text setting must
therefore accept such a number and keep its digits; otherwise a numeric password, user or
client secret in an ordinary ``.env`` line stops the program.

These tests load a real ``.env`` through the real loader, so a change in the library's coercion
shows up here rather than on a deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, ValidationError

from lib_shopify_graphql.cli._common import MySQLConfig, SKUCacheConfig, TokenCacheConfig
from lib_shopify_graphql.cli._health import (
    extract_shopify_credentials_from_config,
)
from lib_shopify_graphql.config import get_config
from lib_shopify_graphql.logging_setup import (
    _build_runtime_config,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from pathlib import Path

    from lib_layered_config import Config


@dataclass(frozen=True)
class _DigitCase:
    """One text setting of a section model fed a digit-only ``.env`` value."""

    model: type[BaseModel]
    section: str
    env_key: str
    attr: str


_DIGIT_CASES = [
    _DigitCase(MySQLConfig, "shopify.mysql", "SHOPIFY__MYSQL__USER", "user"),
    _DigitCase(MySQLConfig, "shopify.mysql", "SHOPIFY__MYSQL__PASSWORD", "password"),
    _DigitCase(MySQLConfig, "shopify.mysql", "SHOPIFY__MYSQL__DATABASE", "database"),
    _DigitCase(MySQLConfig, "shopify.mysql", "SHOPIFY__MYSQL__HOST", "host"),
    _DigitCase(TokenCacheConfig, "shopify.token_cache", "SHOPIFY__TOKEN_CACHE__JSON_PATH", "json_path"),
    _DigitCase(TokenCacheConfig, "shopify.token_cache", "SHOPIFY__TOKEN_CACHE__MYSQL_TABLE", "mysql_table"),
    _DigitCase(SKUCacheConfig, "shopify.sku_cache", "SHOPIFY__SKU_CACHE__JSON_PATH", "json_path"),
    _DigitCase(SKUCacheConfig, "shopify.sku_cache", "SHOPIFY__SKU_CACHE__MYSQL_TABLE", "mysql_table"),
]


def _load_dotenv(tmp_path: Path, *lines: str) -> Config:
    (tmp_path / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    get_config.cache_clear()
    return get_config(start_dir=str(tmp_path))


@pytest.mark.os_agnostic
@pytest.mark.parametrize("case", _DIGIT_CASES, ids=lambda case: f"{case.section}.{case.attr}")
def test_digit_only_dotenv_value_reaches_a_text_setting_as_its_text(tmp_path: Path, case: _DigitCase) -> None:
    loaded = _load_dotenv(tmp_path, f"{case.env_key}=123456").get(case.section, {})
    # Premise: the library hands the value over as a number. Without it the test proves nothing.
    assert isinstance(loaded[case.attr], int)

    settings = case.model.model_validate(loaded)

    assert getattr(settings, case.attr) == "123456"


@pytest.mark.os_agnostic
def test_digit_only_client_credentials_reach_shopify_credentials_as_their_text(tmp_path: Path) -> None:
    config = _load_dotenv(
        tmp_path,
        "SHOPIFY__SHOP_URL=shop.example.com",
        "SHOPIFY__CLIENT_ID=424242",
        "SHOPIFY__CLIENT_SECRET=123456",
    )
    shopify = config.get("shopify", {})
    # Premise: the library hands both values over as numbers.
    assert isinstance(shopify["client_id"], int)
    assert isinstance(shopify["client_secret"], int)

    credentials = extract_shopify_credentials_from_config(config)

    assert (credentials.client_id, credentials.client_secret) == ("424242", "123456")


@pytest.mark.os_agnostic
@pytest.mark.parametrize("attr", ["service", "environment"])
def test_digit_only_logging_value_reaches_the_runtime_config_as_its_text(tmp_path: Path, attr: str) -> None:
    config = _load_dotenv(tmp_path, f"LIB_LOG_RICH__{attr.upper()}=4711")
    # Premise: the library hands the value over as a number.
    assert isinstance(config.get("lib_log_rich", {})[attr], int)

    runtime = _build_runtime_config(config)

    assert getattr(runtime, attr) == "4711"


@pytest.mark.os_agnostic
def test_a_numeric_setting_still_reads_as_a_number(tmp_path: Path) -> None:
    config = _load_dotenv(tmp_path, "SHOPIFY__MYSQL__PORT=3307")

    assert MySQLConfig.model_validate(config.get("shopify.mysql", {})).port == 3307


@pytest.mark.os_agnostic
def test_a_non_numeric_value_for_a_numeric_setting_is_still_refused(tmp_path: Path) -> None:
    config = _load_dotenv(tmp_path, "SHOPIFY__MYSQL__PORT=abc")

    with pytest.raises(ValidationError):
        MySQLConfig.model_validate(config.get("shopify.mysql", {}))
