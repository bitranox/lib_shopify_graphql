"""The suite never reads the app, host or user configuration layer of the machine it runs on.

A host with the CLI deployed system-wide (``/etc/xdg/<slug>/`` on Linux, ``/Library/Application
Support/<vendor>/<app>/`` on macOS, ``C:\\ProgramData\\<vendor>\\<app>\\`` on Windows) would
otherwise decide test results: a ``config.d/99-*.toml`` setting a value there makes tests fail on
that machine while a clean CI runner stays green. These tests ask lib_layered_config where those
layers live, with the code its deploy and its reader share, rather than inspecting the
environment variables the conftest sets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from collected_doctests import collect_src_doctests
from lib_layered_config import deploy_config_paths

from lib_shopify_graphql import __init__conf__
from lib_shopify_graphql.config import get_config, get_default_config_path

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


#: The fixtures that keep the machine's configuration layers out of a test.
_LAYER_REDIRECTS = frozenset({"system_layers_in_tmp_path", "user_layer_in_tmp_path"})


@pytest.fixture
def fresh_config_cache() -> Iterator[None]:
    """Clear ``get_config``'s cache before and after, so the probe value cannot reach another test."""
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.mark.os_agnostic
@pytest.mark.parametrize("target", ["app", "host", "user"])
def test_every_config_layer_resolves_inside_the_test_s_own_directory(target: str, tmp_path: Path) -> None:
    paths = deploy_config_paths(
        get_default_config_path(),
        vendor=__init__conf__.LAYEREDCONF_VENDOR,
        app=__init__conf__.LAYEREDCONF_APP,
        slug=__init__conf__.LAYEREDCONF_SLUG,
        targets=[target],
    )
    outside = sorted(path for path in paths if not path.is_relative_to(tmp_path.resolve()))

    assert outside == [], f"the {target} layer resolves outside this test's directory: {outside}"


@pytest.mark.os_agnostic
def test_a_file_in_the_redirected_app_layer_is_what_the_loader_reads(app_layer_config_file: Path, fresh_config_cache: None) -> None:
    app_layer_config_file.write_text('[layer_isolation_probe]\nread_from = "redirected app layer"\n', encoding="utf-8")

    config = get_config()

    assert config.get("layer_isolation_probe.read_from") == "redirected app layer"


@pytest.mark.os_agnostic
def test_a_file_in_the_redirected_user_layer_is_what_the_loader_reads(user_layer_config_file: Path, fresh_config_cache: None) -> None:
    user_layer_config_file.write_text('[layer_isolation_probe]\nread_from = "redirected user layer"\n', encoding="utf-8")

    config = get_config()

    assert config.get("layer_isolation_probe.read_from") == "redirected user layer"


@pytest.mark.os_agnostic
def test_every_doctest_collected_from_src_gets_the_layer_redirects(tmp_path: Path) -> None:
    """``--doctest-modules`` collects ``src/`` too; a fixture in ``tests/conftest.py`` would not reach it."""
    report = {node: doctest["fixtures"] for node, doctest in collect_src_doctests(tmp_path).items()}
    assert report, "no doctest was collected from src/, so this test checks nothing"

    unredirected = {node: names for node, names in report.items() if not set(names) >= _LAYER_REDIRECTS}

    assert unredirected == {}, f"{len(unredirected)} of {len(report)} doctests run against the machine's layers"
