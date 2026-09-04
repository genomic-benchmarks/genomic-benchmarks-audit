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

**Fetched, not committed, and fetched exactly once.** 91 MB of archives holding
423 files, downloaded straight into the built site at `site/qc-reports/` -- the URL
the pages link to -- so there is one copy on disk and one place it came from.
`data/reports.csv` is the manifest, and `scripts/fetch_reports.py` verifies each
archive against its digest before unpacking it.

**A page renders whether or not they are there, and says which.** The build must
work with no network. `state()` is resolved per dataset at render time, and the
reader is either given the report or told where it is and why it is not here --
never a link that 404s.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from . import audit

# Where they live in the built site, which is the only place they live. One
# directory per archive, named the way the archive names itself, so a reader can
# read the dataset off the URL and the path inside the site is the path inside the
# record. `fetch_reports.py` unpacks here and `site.build()` renders around what it
# finds; neither copies the other's bytes.
SITE_DIR = "qc-reports"


def report_root(site: Path) -> Path:
    """The reports directory of a built site, given the site's root."""
    return site / SITE_DIR


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

    From the manifest rather than the split list: the manifest was read off the
    archives, so it lists reports that exist rather than reports that should.
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

    Split names contain underscores, so the stem is ambiguous alone and is
    resolved against this dataset's splits, longest match first.
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


def present(root: Path, stem: str, paths: Iterable[str]) -> bool:
    """Whether every report this archive lists is on disk under `root`.

    Every file, not the directory: an interrupted unpack leaves a directory that
    exists and is short.
    """
    directory = root / stem
    return all((directory / path).is_file() for path in paths)


def state(unpacked: bool, published: bool) -> str:
    """`unpacked`, `linked` or `unpublished` -- three pages, not two.

    `linked` did not fetch the reports but can send a reader to the record;
    `unpublished` cannot do even that. Collapsing them would either promise a
    download that is not there or hide one that is.

    A fact about the machine that rendered, not about the run, which is why it is
    computed here and is not a field of the committed catalogue.
    """
    if unpacked:
        return "unpacked"
    return "linked" if published else "unpublished"


def archive_stem(dataset: audit.Dataset) -> str:
    """The directory an archive unpacks to: its own name, without `.zip`."""
    if dataset.reports is not None:
        return dataset.reports.archive.removesuffix(".zip")
    return f"{dataset.collection}-{dataset.dataset_name}"


def site_path(dataset: audit.Dataset, report: Report) -> str:
    """Where one report sits in the built site, relative to its root."""
    return f"{SITE_DIR}/{archive_stem(dataset)}/{report.path}"
