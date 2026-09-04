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
def stand_in_reports(committed, tmp_path_factory):
    """A site directory holding one empty file per report the catalogue lists.

    The real ones are 450 MB downloaded from Zenodo. What the site does with them
    is link to them, and an empty file at the right path exercises that exactly as
    well -- on a machine that has never fetched, and in CI, which never will.
    """
    out = tmp_path_factory.mktemp("site") / "site"
    root = site.reports.report_root(out)
    for dataset in committed["datasets"]:
        entry = dataset["reports"]
        if not entry or not entry["archive"]:
            continue
        stem = entry["archive"].removesuffix(".zip")
        for report in entry["files"]:
            path = root / stem / report["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<!doctype html><title>stand-in</title>\n")
    return out


@pytest.fixture(scope="session")
def built(run, stand_in_reports):
    return site.build(stand_in_reports, run=run)


@pytest.fixture(scope="session")
def built_bare(run, tmp_path_factory):
    """The same build on a machine that has fetched nothing."""
    return site.build(tmp_path_factory.mktemp("bare") / "site", run=run)


@pytest.fixture(scope="session")
def copy(committed):
    return site.site_copy(site.counts(committed))
