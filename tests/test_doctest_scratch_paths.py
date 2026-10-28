"""No doctest collected from ``src/`` writes to a fixed path in ``/tmp``.

A doctest that names ``/tmp/<file>`` shares that file with every other doctest naming it and with
every concurrent run of the suite (pytest-xdist workers, a second checkout's gate on the same
host): one run's ``clear`` lands between another's ``set`` and ``get``. Doctests create their own
directory with ``tempfile.mkdtemp()`` and remove it at the end instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from collected_doctests import collect_src_doctests

if TYPE_CHECKING:
    from pathlib import Path

#: A literal path under the POSIX temp directory, which every run on the host shares.
_SHARED_TEMP_PREFIX = "/tmp/"

#: A doctest known to write a cache file; it must be among those examined, or the check is blind.
_KNOWN_CACHE_DOCTEST = "src/lib_shopify_graphql/adapters/cache_json.py::lib_shopify_graphql.adapters.cache_json.JsonFileCacheAdapter"


@pytest.mark.os_agnostic
def test_no_collected_doctest_example_names_a_path_under_tmp(tmp_path: Path) -> None:
    doctests = collect_src_doctests(tmp_path)
    assert _KNOWN_CACHE_DOCTEST in doctests, f"{_KNOWN_CACHE_DOCTEST} was not collected among {len(doctests)} doctests"

    offending = {node: [source.strip() for source in doctest["examples"] if _SHARED_TEMP_PREFIX in source] for node, doctest in doctests.items()}
    offending = {node: sources for node, sources in offending.items() if sources}

    assert offending == {}, f"{len(offending)} of {len(doctests)} doctests name a shared /tmp path: {offending}"
