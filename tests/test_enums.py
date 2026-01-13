"""Tests for infrastructure enums module.

Tests covering:
- StrEnum compatibility shim for Python 3.10
- OutputFormat enum
- DeployTarget enum
- CacheBackend enum
"""

from __future__ import annotations

import pytest


# =============================================================================
# StrEnum Compatibility Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestStrEnumCompatibility:
    """Tests for StrEnum compatibility shim."""

    def test_output_format_is_string_subclass(self) -> None:
        """OutputFormat members are string instances."""
        from lib_shopify_graphql.enums import OutputFormat

        assert isinstance(OutputFormat.HUMAN, str)
        assert isinstance(OutputFormat.JSON, str)

    def test_deploy_target_is_string_subclass(self) -> None:
        """DeployTarget members are string instances."""
        from lib_shopify_graphql.enums import DeployTarget

        assert isinstance(DeployTarget.APP, str)
        assert isinstance(DeployTarget.USER, str)

    def test_cache_backend_is_string_subclass(self) -> None:
        """CacheBackend members are string instances."""
        from lib_shopify_graphql.enums import CacheBackend

        assert isinstance(CacheBackend.JSON, str)
        assert isinstance(CacheBackend.MYSQL, str)

    def test_output_format_str_returns_value(self) -> None:
        """str(OutputFormat.X) returns the value."""
        from lib_shopify_graphql.enums import OutputFormat

        assert str(OutputFormat.HUMAN) == "human"
        assert str(OutputFormat.JSON) == "json"

    def test_deploy_target_str_returns_value(self) -> None:
        """str(DeployTarget.X) returns the value."""
        from lib_shopify_graphql.enums import DeployTarget

        assert str(DeployTarget.APP) == "app"
        assert str(DeployTarget.HOST) == "host"
        assert str(DeployTarget.USER) == "user"

    def test_cache_backend_str_returns_value(self) -> None:
        """str(CacheBackend.X) returns the value."""
        from lib_shopify_graphql.enums import CacheBackend

        assert str(CacheBackend.JSON) == "json"
        assert str(CacheBackend.MYSQL) == "mysql"

    def test_enum_equality_with_string(self) -> None:
        """Enum members are equal to their string values."""
        from lib_shopify_graphql.enums import CacheBackend, DeployTarget, OutputFormat

        assert OutputFormat.HUMAN == "human"
        assert DeployTarget.USER == "user"
        assert CacheBackend.MYSQL == "mysql"

    def test_enum_can_be_used_as_dict_key(self) -> None:
        """Enum members work as dictionary keys."""
        from lib_shopify_graphql.enums import CacheBackend

        mapping = {CacheBackend.JSON: "file", CacheBackend.MYSQL: "database"}

        assert mapping[CacheBackend.JSON] == "file"
        assert mapping["json"] == "file"  # type: ignore[index]

    def test_enum_iteration(self) -> None:
        """Enums can be iterated."""
        from lib_shopify_graphql.enums import OutputFormat

        values = list(OutputFormat)

        assert len(values) == 2
        assert OutputFormat.HUMAN in values
        assert OutputFormat.JSON in values


# =============================================================================
# OutputFormat Enum Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_human_format_value(self) -> None:
        """HUMAN has expected value."""
        from lib_shopify_graphql.enums import OutputFormat

        assert OutputFormat.HUMAN.value == "human"

    def test_json_format_value(self) -> None:
        """JSON has expected value."""
        from lib_shopify_graphql.enums import OutputFormat

        assert OutputFormat.JSON.value == "json"

    def test_construct_from_value(self) -> None:
        """Can construct enum from string value."""
        from lib_shopify_graphql.enums import OutputFormat

        assert OutputFormat("human") is OutputFormat.HUMAN
        assert OutputFormat("json") is OutputFormat.JSON


# =============================================================================
# DeployTarget Enum Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDeployTarget:
    """Tests for DeployTarget enum."""

    def test_app_target_value(self) -> None:
        """APP has expected value."""
        from lib_shopify_graphql.enums import DeployTarget

        assert DeployTarget.APP.value == "app"

    def test_host_target_value(self) -> None:
        """HOST has expected value."""
        from lib_shopify_graphql.enums import DeployTarget

        assert DeployTarget.HOST.value == "host"

    def test_user_target_value(self) -> None:
        """USER has expected value."""
        from lib_shopify_graphql.enums import DeployTarget

        assert DeployTarget.USER.value == "user"

    def test_construct_from_value(self) -> None:
        """Can construct enum from string value."""
        from lib_shopify_graphql.enums import DeployTarget

        assert DeployTarget("app") is DeployTarget.APP
        assert DeployTarget("host") is DeployTarget.HOST
        assert DeployTarget("user") is DeployTarget.USER


# =============================================================================
# CacheBackend Enum Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestCacheBackend:
    """Tests for CacheBackend enum."""

    def test_json_backend_value(self) -> None:
        """JSON has expected value."""
        from lib_shopify_graphql.enums import CacheBackend

        assert CacheBackend.JSON.value == "json"

    def test_mysql_backend_value(self) -> None:
        """MYSQL has expected value."""
        from lib_shopify_graphql.enums import CacheBackend

        assert CacheBackend.MYSQL.value == "mysql"

    def test_construct_from_value(self) -> None:
        """Can construct enum from string value."""
        from lib_shopify_graphql.enums import CacheBackend

        assert CacheBackend("json") is CacheBackend.JSON
        assert CacheBackend("mysql") is CacheBackend.MYSQL

    def test_invalid_value_raises(self) -> None:
        """Invalid value raises ValueError."""
        from lib_shopify_graphql.enums import CacheBackend

        with pytest.raises(ValueError):
            CacheBackend("invalid")
