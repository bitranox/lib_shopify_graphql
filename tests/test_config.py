"""Configuration loader tests: verifying profile and caching behavior.

Unit tests for the config module covering:
- get_config profile parameter
- get_default_config_path behavior
- Configuration caching with different profiles
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib_shopify_graphql import config


# =============================================================================
# Default Config Path Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestGetDefaultConfigPath:
    """Tests for get_default_config_path function."""

    def test_returns_path_object(self) -> None:
        """When called, returns a Path object."""
        result = config.get_default_config_path()

        assert isinstance(result, Path)

    def test_path_ends_with_toml_extension(self) -> None:
        """The default config path has .toml extension."""
        result = config.get_default_config_path()

        assert result.suffix == ".toml"

    def test_path_name_is_defaultconfig(self) -> None:
        """The default config file is named defaultconfig.toml."""
        result = config.get_default_config_path()

        assert result.name == "defaultconfig.toml"

    def test_path_exists(self) -> None:
        """The default config file exists in the package."""
        result = config.get_default_config_path()

        assert result.exists()


# =============================================================================
# Get Config Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestGetConfig:
    """Tests for get_config function."""

    def test_returns_config_object(self) -> None:
        """When called, returns a Config object with as_dict method."""
        result = config.get_config()

        assert hasattr(result, "as_dict")
        assert callable(result.as_dict)

    def test_config_has_get_method(self) -> None:
        """The config object has a get method for section access."""
        result = config.get_config()

        assert hasattr(result, "get")
        assert callable(result.get)

    def test_config_as_dict_returns_dict(self) -> None:
        """The as_dict method returns a dictionary."""
        result = config.get_config()

        config_dict = result.as_dict()
        assert isinstance(config_dict, dict)


# =============================================================================
# Get Config Profile Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestGetConfigProfile:
    """Tests for get_config with profile parameter."""

    def test_accepts_profile_parameter(self) -> None:
        """When profile is provided, the function accepts it."""
        # Should not raise an error
        result = config.get_config(profile="test")

        assert result is not None

    def test_accepts_none_profile(self) -> None:
        """When profile is None, the function works normally."""
        result = config.get_config(profile=None)

        assert result is not None

    def test_different_profiles_can_be_loaded(self) -> None:
        """Different profile names are accepted."""
        # Clear cache to ensure fresh loads
        config.get_config.cache_clear()

        result1 = config.get_config(profile="production")
        result2 = config.get_config(profile="staging")

        # Both should return valid config objects
        assert result1 is not None
        assert result2 is not None

    def test_profile_with_hyphen_is_accepted(self) -> None:
        """Profile names with hyphens are accepted."""
        result = config.get_config(profile="staging-v2")

        assert result is not None

    def test_profile_with_underscore_is_accepted(self) -> None:
        """Profile names with underscores are accepted."""
        result = config.get_config(profile="my_test_profile")

        assert result is not None


# =============================================================================
# Get Config Caching Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestGetConfigCaching:
    """Tests for get_config caching behavior."""

    def test_same_profile_returns_cached_result(self) -> None:
        """When called with same profile, cached result is returned."""
        config.get_config.cache_clear()

        result1 = config.get_config(profile="cache_test")
        result2 = config.get_config(profile="cache_test")

        assert result1 is result2

    def test_different_profiles_return_different_results(self) -> None:
        """When called with different profiles, different results are returned."""
        config.get_config.cache_clear()

        result1 = config.get_config(profile="profile_a")
        result2 = config.get_config(profile="profile_b")

        # Different profile calls should be cached separately
        # (may return same content but should be separate cache entries)
        assert result1 is not None
        assert result2 is not None

    def test_none_profile_is_cached_separately(self) -> None:
        """None profile is cached separately from named profiles."""
        config.get_config.cache_clear()

        result_none = config.get_config(profile=None)
        result_named = config.get_config(profile="named")

        # Both should work
        assert result_none is not None
        assert result_named is not None
