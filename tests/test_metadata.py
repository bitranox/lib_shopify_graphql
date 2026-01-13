"""Metadata synchronization tests: pyproject.toml mirrors __init__conf__.py.

Tests for verifying that package metadata constants stay synchronized with
the canonical source of truth in pyproject.toml. Ensures version, author,
and project info remain consistent across releases.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import rtoml
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
TARGET_FIELDS = ("name", "title", "version", "homepage", "author", "author_email", "shell_command")


# =============================================================================
# Helper Functions
# =============================================================================


def _load_pyproject() -> dict[str, Any]:
    """Load and parse the pyproject.toml file."""
    return rtoml.load(PYPROJECT_PATH)


def _resolve_init_conf_path(pyproject: dict[str, Any]) -> Path:
    """Find the __init__conf__.py path from pyproject.toml configuration."""
    project_table = cast(dict[str, Any], pyproject["project"])
    tool_table = cast(dict[str, Any], pyproject.get("tool", {}))
    hatch_table = cast(dict[str, Any], tool_table.get("hatch", {}))
    targets_table = cast(dict[str, Any], cast(dict[str, Any], hatch_table.get("build", {})).get("targets", {}))
    wheel_table = cast(dict[str, Any], targets_table.get("wheel", {}))
    packages = cast(list[Any], wheel_table.get("packages", []))

    for package_entry in packages:
        if isinstance(package_entry, str):
            candidate = PROJECT_ROOT / package_entry / "__init__conf__.py"
            if candidate.is_file():
                return candidate

    fallback = PROJECT_ROOT / "src" / project_table["name"].replace("-", "_") / "__init__conf__.py"
    if fallback.is_file():
        return fallback

    raise AssertionError("Unable to locate __init__conf__.py")


def _load_init_conf_metadata(init_conf_path: Path) -> dict[str, str]:
    """Extract metadata assignments from __init__conf__.py as a dictionary."""
    fragments: list[str] = []
    for raw_line in init_conf_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        for key in TARGET_FIELDS:
            prefix = f"{key} = "
            if stripped.startswith(prefix):
                fragments.append(stripped)
                break
    if not fragments:
        raise AssertionError("No metadata assignments found in __init__conf__.py")
    metadata_text = "[metadata]\n" + "\n".join(fragments)
    parsed = rtoml.loads(metadata_text)
    metadata_table = cast(dict[str, str], parsed["metadata"])
    return metadata_table


def _load_init_conf_module(init_conf_path: Path) -> dict[str, Any]:
    """Execute __init__conf__.py and return its namespace."""
    return runpy.run_path(str(init_conf_path))


# =============================================================================
# Print Info Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestPrintInfoFunction:
    """Tests for the print_info utility function."""

    def test_lists_every_metadata_field(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When print_info runs, every target field appears in the output."""
        pyproject = _load_pyproject()
        init_conf_path = _resolve_init_conf_path(pyproject)
        init_conf_module = _load_init_conf_module(init_conf_path)

        print_info = init_conf_module["print_info"]
        assert callable(print_info)

        print_info()

        captured = capsys.readouterr().out

        for label in TARGET_FIELDS:
            assert f"{label}" in captured


# =============================================================================
# Metadata Synchronization Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestMetadataSynchronization:
    """Tests ensuring __init__conf__.py stays synchronized with pyproject.toml."""

    @pytest.fixture
    def pyproject(self) -> dict[str, Any]:
        """Load pyproject.toml for test assertions."""
        return _load_pyproject()

    @pytest.fixture
    def metadata(self, pyproject: dict[str, Any]) -> dict[str, str]:
        """Load metadata from __init__conf__.py."""
        init_conf_path = _resolve_init_conf_path(pyproject)
        return _load_init_conf_metadata(init_conf_path)

    @pytest.fixture
    def project_table(self, pyproject: dict[str, Any]) -> dict[str, Any]:
        """Extract the project table from pyproject.toml."""
        return cast(dict[str, Any], pyproject["project"])

    def test_name_matches_project(
        self,
        metadata: dict[str, str],
        project_table: dict[str, Any],
    ) -> None:
        """The name constant matches the project name."""
        assert metadata["name"] == project_table["name"]

    def test_title_matches_description(
        self,
        metadata: dict[str, str],
        project_table: dict[str, Any],
    ) -> None:
        """The title constant matches the project description."""
        assert metadata["title"] == project_table["description"]

    def test_version_matches_project(
        self,
        metadata: dict[str, str],
        project_table: dict[str, Any],
    ) -> None:
        """The version constant matches the project version."""
        assert metadata["version"] == project_table["version"]

    def test_homepage_matches_urls(
        self,
        metadata: dict[str, str],
        project_table: dict[str, Any],
    ) -> None:
        """The homepage constant matches the project homepage URL."""
        urls = cast(dict[str, str], project_table.get("urls", {}))
        assert "Homepage" in urls, "pyproject.toml must define project.urls.Homepage"
        assert metadata["homepage"] == urls["Homepage"]

    def test_author_matches_first_author(
        self,
        metadata: dict[str, str],
        project_table: dict[str, Any],
    ) -> None:
        """The author constant matches the first author name."""
        authors = cast(list[dict[str, str]], project_table.get("authors", []))
        assert authors, "pyproject.toml must declare at least one author entry"
        assert metadata["author"] == authors[0]["name"]

    def test_author_email_matches_first_author(
        self,
        metadata: dict[str, str],
        project_table: dict[str, Any],
    ) -> None:
        """The author_email constant matches the first author email."""
        authors = cast(list[dict[str, str]], project_table.get("authors", []))
        assert authors, "pyproject.toml must declare at least one author entry"
        assert metadata["author_email"] == authors[0]["email"]

    def test_shell_command_exists_in_scripts(
        self,
        metadata: dict[str, str],
        project_table: dict[str, Any],
    ) -> None:
        """The shell_command constant exists in project scripts."""
        scripts = cast(dict[str, Any], project_table.get("scripts", {}))
        assert metadata["shell_command"] in scripts
