"""The 423 browsable reports: what each one is, and where it can be read.

`genomic-benchmarks-qc` renders a self-contained HTML report for every unit it
measures. There are two kinds and the difference is the difference between the two
combined tables:

`class/<split>/<seq_col>.html`
    What the nine class-distribution checks found on one split, for one sequence
    column: the distributions per class, the probe fits, the per-position profiles.
    A dataset with two sequence columns -- `GUE_v2`'s enhancer-promoter pairs,
    miRBench's guide and target -- gets one per column plus a `merged` report.

`split/<a>_<b>.html`
    The leakage scan over one pair of splits: the MMseqs2 hits, and the individual
    sequences of `<b>` that were found in `<a>`. This is the report that makes a
    leaked held-out sequence identifiable rather than merely countable.

**They are fetched, not committed.** 91 MB of archives holding 423 files; a
repository that carried them would be one where every clone pays for the whole
audit to read one page, and where the reports could drift from the tables that
summarise them without a diff saying so. `data/reports.csv` carries the manifest --
name, size, digest and every path inside -- so the site knows exactly what exists
before anything is downloaded, and `scripts/fetch_reports.py` verifies each archive
against its digest before unpacking it.

**A page renders whether or not they are there, and says which.** The build must
work with no network: CI has none, and a contributor should be able to see the site
before spending 91 MB. So `Availability` is resolved per dataset at render time and
the report page has two honest states -- the reader is either given the report or
told where it is and why it is not here. What it is never given is a link that
404s, which is also why `zenodo.registered()` is consulted rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import audit, zenodo

REPO = Path(__file__).resolve().parents[2]

# Where `fetch_reports.py` unpacks, and what `build_site.py` copies from. Inside
# `docs/` because that is the site's source directory, and gitignored because it
# is 91 MB of fetched bytes rather than anything this repository authored.
UNPACKED = REPO / "docs" / "reports"

# Where they land in the built site. One directory per archive, named the way the
# archive names itself, so a reader can read the dataset off the URL and the path
# inside the site is the path inside the record.
SITE_DIR = "qc-reports"


@dataclass(frozen=True)
class Report:
    """One rendered report, and the sentence that says what it shows."""

    kind: str  # "class" or "leakage scan"
    path: str  # relative to the archive's own directory
    split: str | None
    seq_col: str | None
    pair: tuple[str, str] | None

    @property
    def title(self) -> str:
        if self.kind == "class":
            return f"{self.split} · {self.seq_col}"
        return f"{self.pair[0]} vs {self.pair[1]}"

    @property
    def description(self) -> str:
        """What the report holds, in the vocabulary the rest of the site uses."""
        if self.kind == "class":
            return (
                f"The nine class-distribution checks on the {self.split} split, "
                f"measured on the {self.seq_col} column: the distribution of each "
                f"feature by class, and the fit of each probe."
            )
        return (
            f"The leakage scan between {self.pair[0]} and {self.pair[1]}: the "
            f"sequences of one split that were also found in the other, listed "
            f"individually rather than only counted."
        )


def reports_for(dataset: audit.Dataset) -> tuple[Report, ...]:
    """Every report the run rendered for one dataset, class reports first.

    Built from the manifest rather than from the split list, because the manifest
    was read off the archives: a dataset whose second sequence column was measured
    and whose report was not written would otherwise be linked to a file that does
    not exist.
    """
    if dataset.reports is None:
        return ()
    found = [
        Report(kind="class", path=path, split=split, seq_col=seq_col, pair=None)
        for split, seq_col, path in dataset.reports.class_reports
    ]
    for pair, path in dataset.reports.split_reports:
        found.append(
            Report(
                kind="leakage scan",
                path=path,
                split=None,
                seq_col=None,
                pair=_pair(pair, dataset),
            )
        )
    return tuple(found)


def _pair(stem: str, dataset: audit.Dataset) -> tuple[str, str]:
    """`train_test_leftout` -> `("train", "test_leftout")`.

    Split names contain underscores, so the filename is ambiguous on its own and
    is resolved against the splits this dataset actually has. Longest match first,
    so `train_test_leftout` does not resolve to `train` + `test` and leave
    `_leftout` behind.
    """
    names = sorted(dataset.split_names, key=len, reverse=True)
    for first in names:
        if stem.startswith(f"{first}_"):
            second = stem[len(first) + 1 :]
            if second in dataset.split_names:
                return (first, second)
    # Not raised: a pair this cannot resolve is still a report worth linking to,
    # and refusing to render the page over a filename would lose the reader the
    # file as well as the label. The stem stands in as its own title.
    return (stem, "")


@dataclass(frozen=True)
class Availability:
    """Whether one dataset's reports can actually be read from this build."""

    unpacked: bool
    archive_url: str | None
    record_url: str | None

    @property
    def state(self) -> str:
        """`unpacked`, `linked` or `unpublished` -- three pages, not two.

        `linked` is a build that did not fetch the reports but can send a reader
        to the record. `unpublished` is a build that cannot do even that, because
        the record does not exist yet. Collapsing them would either promise a
        download that is not there or hide one that is.
        """
        if self.unpacked:
            return "unpacked"
        return "linked" if self.archive_url else "unpublished"


def availability(dataset: audit.Dataset, root: Path | None = None) -> Availability:
    """Where this dataset's reports can be read from, for this build."""
    root = UNPACKED if root is None else root
    if dataset.reports is None:
        return Availability(unpacked=False, archive_url=None, record_url=None)
    directory = root / archive_stem(dataset)
    present = directory.is_dir() and any(directory.rglob("*.html"))
    published = zenodo.registered()
    return Availability(
        unpacked=present,
        archive_url=zenodo.file_url(dataset.reports.archive) if published else None,
        record_url=zenodo.public_record_url() if published else None,
    )


def archive_stem(dataset: audit.Dataset) -> str:
    """The directory an archive unpacks to: its own name, without `.zip`."""
    if dataset.reports is not None:
        return dataset.reports.archive.removesuffix(".zip")
    return f"{dataset.collection}-{dataset.dataset_name}"


def site_path(dataset: audit.Dataset, report: Report) -> str:
    """Where one report sits in the built site, relative to its root."""
    return f"{SITE_DIR}/{archive_stem(dataset)}/{report.path}"


def unpacked_datasets(root: Path | None = None) -> set[str]:
    """Which archives have been unpacked, by directory name.

    Cheap enough to call once per build and answer 93 questions from, which is
    what `build_site.py` does -- `availability()` per dataset would stat the same
    tree 93 times.
    """
    root = UNPACKED if root is None else root
    if not root.is_dir():
        return set()
    return {
        directory.name
        for directory in root.iterdir()
        if directory.is_dir() and any(directory.rglob("*.html"))
    }
