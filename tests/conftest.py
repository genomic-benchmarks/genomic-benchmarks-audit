"""One run and one built site, shared across the suite.

`audit.run()` reads a dozen CSVs and `site.build()` writes 522 pages; done per
test that is a slow suite, and a slow suite is one that stops being run. Both are
session-scoped and neither is mutated by a test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from gb_audit import audit, catalogue, site  # noqa: E402


@pytest.fixture(scope="session")
def run():
    return audit.run()


@pytest.fixture(scope="session")
def document(run):
    return catalogue.build(run)


@pytest.fixture(scope="session")
def committed():
    return site.load_document()


@pytest.fixture(scope="session")
def built(run, tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    result = site.build(out / "site", run=run)
    return result


@pytest.fixture(scope="session")
def copy(committed):
    return site.site_copy(site.counts(committed))
