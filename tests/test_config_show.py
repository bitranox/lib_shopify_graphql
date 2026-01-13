"""Configuration display tests: each format tells a clear story.

Unit tests for the config_show module covering:
- JSON and human format output
- Section filtering
- Error handling for missing sections

Tests use controlled mock configs to verify formatting behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lib_shopify_graphql import config_show
from lib_shopify_graphql.enums import OutputFormat


def _make_mock_config() -> MagicMock:
    """Create a mock Config object for testing."""
    return MagicMock()


# =============================================================================
# Display Config Human Format Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDisplayConfigHumanFormat:
    """Tests for display_config with human format."""

    def test_displays_section_header(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When human format is used, section headers appear in brackets."""
        mock_config = _make_mock_config()
        mock_config.as_dict.return_value = {"my_section": {"key": "value"}}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN)

        captured = capsys.readouterr()
        assert "[my_section]" in captured.out

    def test_displays_string_value_quoted(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When a string value is displayed, it is quoted."""
        mock_config = _make_mock_config()
        mock_config.as_dict.return_value = {"section": {"name": "test"}}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN)

        captured = capsys.readouterr()
        assert 'name = "test"' in captured.out

    def test_displays_integer_value_unquoted(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When an integer value is displayed, it is not quoted."""
        mock_config = _make_mock_config()
        mock_config.as_dict.return_value = {"section": {"count": 42}}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN)

        captured = capsys.readouterr()
        assert "count = 42" in captured.out

    def test_displays_list_value_as_json(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When a list value is displayed, it appears as JSON."""
        mock_config = _make_mock_config()
        mock_config.as_dict.return_value = {"section": {"items": ["a", "b"]}}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN)

        captured = capsys.readouterr()
        # orjson produces compact JSON without spaces
        assert '["a","b"]' in captured.out

    def test_displays_dict_value_as_json(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When a nested dict value is displayed, it appears as JSON."""
        mock_config = _make_mock_config()
        mock_config.as_dict.return_value = {"section": {"nested": {"inner": "value"}}}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN)

        captured = capsys.readouterr()
        # orjson produces compact JSON without spaces
        assert '{"inner":"value"}' in captured.out

    def test_displays_non_mapping_section_directly(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When section data is not a mapping, it is displayed directly."""
        mock_config = _make_mock_config()
        mock_config.as_dict.return_value = {"simple": "just a string"}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN)

        captured = capsys.readouterr()
        assert "[simple]" in captured.out
        assert "just a string" in captured.out

    def test_displays_multiple_sections(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When multiple sections exist, all are displayed."""
        mock_config = _make_mock_config()
        mock_config.as_dict.return_value = {
            "section1": {"key1": "value1"},
            "section2": {"key2": "value2"},
        }

        config_show.display_config(mock_config, format=OutputFormat.HUMAN)

        captured = capsys.readouterr()
        assert "[section1]" in captured.out
        assert "[section2]" in captured.out


@pytest.mark.os_agnostic
class TestDisplayConfigHumanFormatWithSection:
    """Tests for display_config human format with section filter."""

    def test_displays_only_requested_section(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When a section is specified, only that section appears."""
        mock_config = _make_mock_config()
        mock_config.get.return_value = {"setting": "filtered"}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN, section="my_section")

        captured = capsys.readouterr()
        assert "[my_section]" in captured.out
        assert 'setting = "filtered"' in captured.out

    def test_section_filter_displays_list_value_as_json(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When section filtered, list values are shown as JSON."""
        mock_config = _make_mock_config()
        mock_config.get.return_value = {"items": ["a", "b", "c"]}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN, section="my_section")

        captured = capsys.readouterr()
        assert 'items = ["a","b","c"]' in captured.out

    def test_section_filter_displays_integer_value_unquoted(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When section filtered, integer values are shown unquoted."""
        mock_config = _make_mock_config()
        mock_config.get.return_value = {"count": 42}

        config_show.display_config(mock_config, format=OutputFormat.HUMAN, section="my_section")

        captured = capsys.readouterr()
        assert "count = 42" in captured.out


# =============================================================================
# Display Config JSON Format Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDisplayConfigJsonFormat:
    """Tests for display_config with JSON format."""

    def test_displays_json_output(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When JSON format is used, JSON is output."""
        mock_config = _make_mock_config()
        mock_config.to_json.return_value = '{"section": {"key": "value"}}'

        config_show.display_config(mock_config, format=OutputFormat.JSON)

        captured = capsys.readouterr()
        assert '{"section": {"key": "value"}}' in captured.out


@pytest.mark.os_agnostic
class TestDisplayConfigJsonFormatWithSection:
    """Tests for display_config JSON format with section filter."""

    def test_displays_filtered_json(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When JSON format with section is used, filtered JSON appears."""
        mock_config = _make_mock_config()
        mock_config.get.return_value = {"setting": "filtered"}

        config_show.display_config(mock_config, format=OutputFormat.JSON, section="my_section")

        captured = capsys.readouterr()
        assert "my_section" in captured.out
        assert "filtered" in captured.out


# =============================================================================
# Display Config Error Handling Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDisplayConfigSectionNotFound:
    """Tests for section not found error handling."""

    def test_human_format_missing_section_raises_exit(
        self,
    ) -> None:
        """When section is not found in human format, SystemExit is raised."""
        mock_config = _make_mock_config()
        mock_config.get.return_value = {}

        with pytest.raises(SystemExit) as exc:
            config_show.display_config(mock_config, format=OutputFormat.HUMAN, section="missing")

        assert exc.value.code == 1

    def test_json_format_missing_section_raises_exit(
        self,
    ) -> None:
        """When section is not found in JSON format, SystemExit is raised."""
        mock_config = _make_mock_config()
        mock_config.get.return_value = {}

        with pytest.raises(SystemExit) as exc:
            config_show.display_config(mock_config, format=OutputFormat.JSON, section="missing")

        assert exc.value.code == 1

    def test_missing_section_shows_error_message(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When section is not found, error message appears in stderr."""
        mock_config = _make_mock_config()
        mock_config.get.return_value = {}

        with pytest.raises(SystemExit):
            config_show.display_config(mock_config, section="nonexistent")

        captured = capsys.readouterr()
        assert "nonexistent" in captured.err
        assert "not found or empty" in captured.err
