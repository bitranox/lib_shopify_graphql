"""What ``pytest --doctest-modules`` collects from ``src/``, asked of pytest itself.

``tests/conftest.py`` cannot see the doctests in ``src/``, and a hand-rolled ``doctest.DocTestFinder``
walk would not honour the ``--ignore`` entries in pyproject's ``addopts``. So this runs pytest's own
collection in a subprocess with a small plugin that writes, for each collected doctest, the
fixtures it gets and the source of each example. Imported by bare name, like ``layer_roots``:
``pythonpath`` in pyproject puts ``tests/`` on ``sys.path``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

__all__ = ["CollectedDoctest", "collect_src_doctests"]

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: A pytest plugin writing what each collected doctest gets and runs. ``--fixtures-per-test`` would
#: answer the fixture half directly, but it crashes on doctest items (pytest 9.1: DoctestItem has
#: no ``function``).
_DOCTEST_REPORT_PLUGIN = """\
import json
import os

import pytest


def pytest_collection_modifyitems(items):
    report = {
        item.nodeid: {
            "fixtures": sorted(item.fixturenames),
            "examples": [example.source for example in item.dtest.examples],
        }
        for item in items
        if isinstance(item, pytest.DoctestItem)
    }
    with open(os.environ["DOCTEST_REPORT"], "w", encoding="utf-8") as report_file:
        json.dump(report, report_file)
"""


class CollectedDoctest(TypedDict):
    """One collected doctest: the fixtures pytest gives it and the source of each example."""

    fixtures: list[str]
    examples: list[str]


def collect_src_doctests(scratch: Path) -> dict[str, CollectedDoctest]:
    """Collect ``src/`` the way the suite does and return each doctest by node id.

    Args:
        scratch: An empty directory of the caller's own for the plugin and the report.

    Returns:
        The collected doctests, keyed by pytest node id.

    Raises:
        AssertionError: When the collection itself fails.
    """
    (scratch / "_doctest_report.py").write_text(_DOCTEST_REPORT_PLUGIN, encoding="utf-8")
    report_file = scratch / "doctests.json"
    python_path = os.pathsep.join(filter(None, [str(scratch), os.environ.get("PYTHONPATH", "")]))
    env = {**os.environ, "PYTHONPATH": python_path, "DOCTEST_REPORT": str(report_file)}
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
    completed = subprocess.run(  # noqa: S603 - fixed argv: this interpreter running pytest on this repo
        [*command, "-p", "_doctest_report", "src"],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report: dict[str, CollectedDoctest] = json.loads(report_file.read_text(encoding="utf-8"))
    return report
