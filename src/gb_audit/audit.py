"""The archived run, read from `data/` and checked against itself.

Ten checks over 93 datasets and their 234 splits, published as three tables that
say the same things at three grains:

`combined_classes_results.csv`
    2,106 rows. One row per dataset per split per class-distribution check, with
    the flag and -- for the six probes -- the AUROC, AUPRC and accuracy that one
    sequence feature reaches on its own.

`combined_splits_results.csv`
    141 result rows. One per ordered pair of a dataset's splits, carrying the
    percentage of each side found in the other. Plus 92 rollup rows the QC run
    wrote for its own report, skipped here: reading them in would count each
    dataset's worst flag a second time.

`dataset_level_summary.csv`
    93 rows, one per dataset. The two tables above, rolled up.

**The rollup is a statement about the reference split**, `train` for 92 datasets
and `test` for the one that ships no train split -- not a maximum over splits.
`BEACON:Isoform` rolls up 0.749 while its `val` split reaches 0.757, so a page
printing the rollup under a heading naming another split would report a measurement
never made there. `Dataset` carries the per-split values too, and every figure
names its split.

**Nothing here is trusted that can be recomputed.** `read()` derives all ten flags,
`max_probe_auroc`, `strongest_probe` and the leakage summary from the two combined
tables and compares them against the rollup row by row; on the published run all 93
agree exactly. The tables are copied in from a run this repository cannot
re-execute, and a copy that lost a column is otherwise a page that disagrees with
itself in silence.

Two distinctions the reader has to keep:

`Unknown` is not a blank.
    `Unknown` is the tool's fourth flag: a check that ran and could not be scored,
    because a class fell under its sequence floor. It occurs 66 times. A blank had
    nothing to run on at all -- `miRBench:AGO2_eCLIP_Klimentova2022` ships one
    split, so the leakage scan had no pair. Read as `Pass`, either would claim a
    screening that did not happen.

Worst-of over four values has no honest single answer.
    `rollup()` returns the worst flag over the checks that *scored*, plus how many
    did not. Ranking `Unknown` above `Fail` overstates, below `Pass` understates,
    and dropping it hides that a check did not run.
"""

from __future__ import annotations

import csv
import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

# --------------------------------------------------------------- the checks ---

# The six probes: one hand-crafted sequence feature each, fitted alone as a
# single-feature classifier. They are the checks that carry a number.
PROBE_CHECKS = (
    "Sequence lengths",
    "Per sequence GC content",
    "Per sequence nucleotide content",
    "Per sequence dinucleotide content",
    "Per position nucleotide content",
    "Per position reversed nucleotide content",
)
# The three integrity checks. `VOCABULARY.md` says "integrity checks", never
# "structural checks", and two of the three are Tier 1 findings -- assertable
# without hedging, because no biological reading of them is available.
INTEGRITY_CHECKS = (
    "Unique bases",
    "Sequence Duplications within Labels",
    "Duplicate Sequences between Labels",
)
# Together, the nine `evaluate-classes` runs per split.
CLASS_CHECKS = PROBE_CHECKS + INTEGRITY_CHECKS
# The tenth, run by `evaluate-splits` over pairs of splits rather than over one.
LEAKAGE_SCAN = "Split leakage"
CHECKS = CLASS_CHECKS + (LEAKAGE_SCAN,)

# The order the ten are *read* in, which is not the order they arrive in.
#
# `CHECKS` above is a statement about the rollup file: those columns, in that
# order, or the build stops. This is a statement about a reader, and it is the
# manuscript's -- Supplementary Figure 2 sets the three composition probes first,
# then length, then the two positional ones; the two duplicate checks before the
# alphabet check; the leakage scan last. The grid on this site is that figure in
# HTML, so a reader with one open beside the other should not have to find a
# column twice.
DISPLAY_PROBE_CHECKS = (
    "Per sequence GC content",
    "Per sequence nucleotide content",
    "Per sequence dinucleotide content",
    "Sequence lengths",
    "Per position nucleotide content",
    "Per position reversed nucleotide content",
)
DISPLAY_INTEGRITY_CHECKS = (
    "Sequence Duplications within Labels",
    "Duplicate Sequences between Labels",
    "Unique bases",
)
DISPLAY_CLASS_CHECKS = DISPLAY_PROBE_CHECKS + DISPLAY_INTEGRITY_CHECKS
DISPLAY_CHECKS = DISPLAY_CLASS_CHECKS + (LEAKAGE_SCAN,)

# Both orders are written out by hand, so they are checked against each other on
# import rather than trusted. Two things have to hold: the same ten names, and
# each family in one unbroken run, because the grid's band row spans its columns
# by position -- a check that moved between families would put "integrity checks"
# over a probe rather than fail.
if sorted(DISPLAY_CHECKS) != sorted(CHECKS):
    raise RuntimeError(
        "DISPLAY_CHECKS must be a reordering of CHECKS; they differ at "
        f"{sorted(set(DISPLAY_CHECKS) ^ set(CHECKS))}"
    )
if sorted(DISPLAY_PROBE_CHECKS) != sorted(PROBE_CHECKS) or sorted(
    DISPLAY_INTEGRITY_CHECKS
) != sorted(INTEGRITY_CHECKS):
    raise RuntimeError(
        "DISPLAY_CHECKS must keep each family in one run: the band row spans "
        "columns by position and cannot label a family that is split"
    )

FLAGS = ("Pass", "Warning", "Fail", "Unknown")
UNKNOWN = "Unknown"

# `Unknown` is deliberately absent. See the module docstring: a check that could
# not be scored is neither worse than `Warning` nor better than `Pass`, and putting
# it on this scale would let it be summarised away.
SEVERITY = {"Pass": 0, "Warning": 1, "Fail": 2}

# Every split name the corpus uses, in the order a reader thinks about them:
# what the model saw, what it was tuned on, what it is scored on.
SPLIT_ORDER = ("train", "val", "test", "test_leftout")

# The 42 columns of the rollup, in file order. Stated so that a run whose output
# moved stops the build here, naming the columns, rather than three calls deeper
# with a `KeyError`.
ROLLUP_COLUMNS = (
    "collection",
    "dataset",
    "task_category",
    "molecular_level",
    "task_type",
    "species",
    "n_species",
    "train_size",
    "total_size",
    "min_seq_length",
    "max_seq_length",
    "task_category_grouped",
    "reference_split",
    "has_reference_split",
    "overall_verdict",
    "worst_class_flag",
    "n_checks_failed",
    "n_checks_warning",
    "n_checks_unknown",
    "n_checks_reported",
    "n_checks_scored",
    "strongest_probe",
    "max_probe_auroc",
    "max_probe_accuracy",
    "max_leaked_test_pct",
    "max_leaked_train_pct",
    "worst_leakage_comparison",
    "n_split_comparisons",
    *(f"flag: {name}" for name in CHECKS),
    *(f"max_probe_auroc: {split}" for split in ("test", "test_leftout", "train", "val")),
)


class RunInvalid(ValueError):
    """The archived run does not say what a run of this instrument can say.

    A flag outside the tool's four, a rollup that disagrees with the table it
    summarises, a dataset in one file and not another. Raised on read: a number
    that reached a page without an origin is worse than a build that stops.
    """


# ------------------------------------------------------------------- flags ---


def worst_flag(flags: Iterable[str | None]) -> str | None:
    """The worst of `Pass`/`Warning`/`Fail`, ignoring `Unknown` and blanks.

    `None` when nothing scored. `rollup()` is the call that also says how many
    did not, which is the half of the answer a single flag cannot carry.
    """
    ranked = [flag for flag in flags if flag in SEVERITY]
    if not ranked:
        return None
    return max(ranked, key=lambda flag: SEVERITY[flag])


def rollup(flags: Sequence[str | None]) -> dict:
    """The worst flag over the checks that scored, and how many did not.

    One `Fail` and five `Unknown`s is a `Fail`; `Unknown` survives only when there
    is nothing else to roll up. `flag` is None when nothing was recorded at all,
    which means the check had nothing to run on rather than that it ran.
    """
    scored = [flag for flag in flags if flag in SEVERITY]
    unknown = [flag for flag in flags if flag == UNKNOWN]
    if scored:
        answer: str | None = max(scored, key=lambda flag: SEVERITY[flag])
    elif unknown:
        answer = UNKNOWN
    else:
        answer = None
    return {"flag": answer, "n_scored": len(scored), "n_unknown": len(unknown)}


def check_kind(name: str) -> str:
    """`probe`, `integrity` or `leakage scan` -- the words `VOCABULARY.md` uses."""
    if name in PROBE_CHECKS:
        return "probe"
    if name in INTEGRITY_CHECKS:
        return "integrity"
    return "leakage scan"


# ---------------------------------------------------------------- readings ---


@dataclass(frozen=True)
class Measurement:
    """One class-distribution check, on one split of one dataset.

    `au_roc`, `au_pr` and `accuracy` are `None` on the three integrity checks,
    which return a flag and no number. Absent is rendered as absent: `0.000` would
    be the most reassuring possible figure in place of no figure at all.
    """

    check: str
    split: str
    flag: str | None
    accuracy: float | None
    au_pr: float | None
    au_roc: float | None

    @property
    def kind(self) -> str:
        return check_kind(self.check)


@dataclass(frozen=True)
class LeakageComparison:
    """One ordered pair of splits, scanned for shared sequences.

    The tool searches the held-out split (`query_split`) against the trained-on
    split (`target_split`), so `leaked_queries_pct` is the percentage of held-out
    rows also in train, and `leaked_targets_pct` the same overlap counted the other
    way. Both sides are named because the query side is `val` rather than `test` on
    25 of the 93 datasets.
    """

    query_split: str
    target_split: str
    flag: str | None
    leaked_queries_pct: float | None
    leaked_targets_pct: float | None

    @property
    def label(self) -> str:
        """How the rollup names this comparison: `<target> vs <query>`."""
        return f"{self.target_split} vs {self.query_split}"


@dataclass(frozen=True)
class Split:
    """One split, as the QC run's own metadata records it.

    `seq_cols` is the reason this file is read at all: a class report is written
    per split per sequence column, so it is what says which reports exist. Most
    datasets have one column; `GUE_v2`'s enhancer-promoter pairs have two, as do
    miRBench's, and those get a report per column plus a `merged` one.
    """

    split: str
    seq_cols: tuple[str, ...]
    label_col: str
    regression: bool
    num_labels: int | None


@dataclass(frozen=True)
class Reports:
    """The per-dataset report archive: what it is called and what is inside it.

    Read off the archives themselves at copy time rather than composed from a
    naming rule, because the rule has exceptions and a manifest that guessed would
    link a reader to a file that is not there.
    """

    archive: str
    n_bytes: int
    sha256: str
    paths: tuple[str, ...]

    @property
    def class_reports(self) -> tuple[tuple[str, str, str], ...]:
        """`(split, seq_col, path)` for each class report, in split order."""
        found = []
        for path in self.paths:
            parts = path.split("/")
            if len(parts) == 3 and parts[0] == "class":
                found.append((parts[1], parts[2].removesuffix(".html"), path))
        return tuple(sorted(found, key=lambda item: (_split_rank(item[0]), item[1])))

    @property
    def split_reports(self) -> tuple[tuple[str, str], ...]:
        """`(pair, path)` for each leakage report, where `pair` is `a_b`."""
        found = [
            (path.split("/")[1].removesuffix(".html"), path)
            for path in self.paths
            if path.startswith("split/")
        ]
        return tuple(sorted(found))


def _split_rank(split: str) -> tuple[int, str]:
    """Sort splits the way a reader thinks about them, unknown names last."""
    return (
        SPLIT_ORDER.index(split) if split in SPLIT_ORDER else len(SPLIT_ORDER),
        split,
    )


@dataclass(frozen=True)
class Dataset:
    """One of the 93 included datasets, and everything the run says about it."""

    collection: str
    dataset_name: str

    task_category: str
    task_category_grouped: str
    molecular_level: str
    task_type: str
    species: str
    n_species: int | None
    train_size: int | None
    total_size: int | None
    min_seq_length: int | None
    max_seq_length: int | None

    # Which split the rollup's figures were taken on. `train` for 92 datasets,
    # `test` for the one that ships no train split.
    reference_split: str | None

    overall_verdict: str | None
    worst_class_flag: str | None
    n_checks_failed: int
    n_checks_warning: int
    n_checks_unknown: int
    n_checks_reported: int
    n_checks_scored: int

    strongest_probe: str | None
    max_probe_auroc: float | None
    max_probe_accuracy: float | None
    max_leaked_test_pct: float | None
    max_leaked_train_pct: float | None
    worst_leakage_comparison: str | None
    n_split_comparisons: int | None

    flags: dict[str, str | None]
    probe_auroc_by_split: dict[str, float]

    measurements: tuple[Measurement, ...]
    leakage: tuple[LeakageComparison, ...]
    splits: tuple[Split, ...]
    reports: Reports | None
    core_set_rank: int | None

    @property
    def benchmark_id(self) -> str:
        return f"{self.collection}:{self.dataset_name}"

    @property
    def in_core_set(self) -> bool:
        return self.core_set_rank is not None

    @property
    def split_names(self) -> tuple[str, ...]:
        return tuple(split.split for split in self.splits)

    def measurements_on(self, split: str) -> tuple[Measurement, ...]:
        """The nine class checks on one split, in the audit's own order."""
        by_check = {m.check: m for m in self.measurements if m.split == split}
        return tuple(by_check[name] for name in CLASS_CHECKS if name in by_check)

    def strongest_probe_on(self, split: str) -> Measurement | None:
        """The probe that reaches furthest on one split, or None if none scored.

        Per split rather than per dataset, because `strongest_probe` in the rollup
        is the reference split's answer and 22 datasets have a different strongest
        probe somewhere else. A page that names a feature has to name the one that
        was measured where it says it was.
        """
        scored = [
            m
            for m in self.measurements
            if m.split == split and m.kind == "probe" and m.au_roc is not None
        ]
        if not scored:
            return None
        return max(scored, key=lambda m: m.au_roc)

    def worst_leakage(self) -> LeakageComparison | None:
        """The comparison the rollup's leakage figures came from."""
        scored = [c for c in self.leakage if c.leaked_queries_pct is not None]
        if not scored:
            return None
        return max(scored, key=lambda c: c.leaked_queries_pct)


@dataclass(frozen=True)
class Gate:
    """One step of the Core Set selection funnel."""

    step: int
    criterion: str
    requirement: str
    threshold: str
    n_in: int
    n_removed: int
    n_out: int


@dataclass
class Run:
    """The whole archived run: every table, joined and checked."""

    datasets: dict[str, Dataset]
    by_check: tuple[dict[str, str], ...]
    by_collection: tuple[dict[str, str], ...]
    by_task_category: tuple[dict[str, str], ...]
    exclusions: tuple[dict[str, str], ...]
    gates: tuple[Gate, ...]
    selection_trace: tuple[dict[str, str], ...]
    provenance: dict

    @property
    def n_splits(self) -> int:
        return sum(len(d.splits) for d in self.datasets.values())

    @property
    def n_reports(self) -> int:
        return sum(
            len(d.reports.paths) for d in self.datasets.values() if d.reports is not None
        )

    @property
    def core_set(self) -> tuple[Dataset, ...]:
        chosen = [d for d in self.datasets.values() if d.in_core_set]
        return tuple(sorted(chosen, key=lambda d: d.core_set_rank))


# ------------------------------------------------------------------ reading ---


def _rows(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    if not path.exists():
        raise RunInvalid(
            f"{path.name} is not in {path.parent}. Regenerate the archived run "
            f"with scripts/regenerate_audit_data.py rather than assembling it by "
            f"hand; the tables are checked against each other on read and a "
            f"missing one cannot be checked at all."
        )
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def _optional_float(value: str, where: str, column: str) -> float | None:
    value = value.strip().rstrip("%")
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise RunInvalid(f"{where}.{column}: {value!r} is not a number") from exc


def _optional_int(value: str, where: str, column: str) -> int | None:
    number = _optional_float(value, where, column)
    if number is None:
        return None
    if number != int(number):
        raise RunInvalid(f"{where}.{column}: {value!r} is not a whole number")
    return int(number)


def _flag(value: str, where: str, column: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    if value not in FLAGS:
        raise RunInvalid(
            f"{where}: {column} is {value!r}, which is not one of "
            f"{', '.join(FLAGS)}. The four flags are the tool's output and a "
            f"fifth value means the table was edited."
        )
    return value


def _read_measurements(path: Path) -> dict[tuple[str, str], list[Measurement]]:
    found: dict[tuple[str, str], list[Measurement]] = {}
    for row in _rows(path):
        key = (row["collection"], row["dataset"])
        where = f"{key[0]}:{key[1]} {row['split']} {row['check']}"
        found.setdefault(key, []).append(
            Measurement(
                check=row["check"],
                split=row["split"],
                flag=_flag(row["flag"], where, "flag"),
                accuracy=_optional_float(row["accuracy"], where, "accuracy"),
                au_pr=_optional_float(row["au_pr"], where, "au_pr"),
                au_roc=_optional_float(row["au_roc"], where, "au_roc"),
            )
        )
    return found


def _read_leakage(path: Path) -> dict[tuple[str, str], list[LeakageComparison]]:
    """The 141 result rows, without the 92 rollup rows beside them.

    A result has a check and a split pair; a rollup has a `statistic` and neither.
    A row of a third shape is raised on rather than skipped.
    """
    found: dict[tuple[str, str], list[LeakageComparison]] = {}
    for row in _rows(path):
        key = (row["collection"], row["dataset"])
        found.setdefault(key, [])
        if not row["check"].strip():
            if row["statistic"].strip():
                continue
            raise RunInvalid(
                f"{key[0]}:{key[1]}: a row of combined_splits_results.csv has "
                f"neither a check nor a statistic, so nothing can say whether it "
                f"is a result to read or a rollup to skip: {row}"
            )
        where = f"{key[0]}:{key[1]} {row['train_split']} vs {row['test_split']}"
        found[key].append(
            LeakageComparison(
                query_split=row["test_split"],
                target_split=row["train_split"],
                flag=_flag(row["flag"], where, "flag"),
                leaked_queries_pct=_optional_float(
                    row["percentage_of_leaked_queries"], where, "leaked queries"
                ),
                leaked_targets_pct=_optional_float(
                    row["percentage_of_leaked_targets"], where, "leaked targets"
                ),
            )
        )
    for comparisons in found.values():
        comparisons.sort(key=lambda c: (_split_rank(c.query_split), c.target_split))
    return found


def _read_splits(path: Path) -> dict[tuple[str, str], list[Split]]:
    found: dict[tuple[str, str], list[Split]] = {}
    for row in _rows(path):
        key = (row["collection"], row["dataset"])
        where = f"{key[0]}:{key[1]} {row['split']}"
        found.setdefault(key, []).append(
            Split(
                split=row["split"],
                seq_cols=tuple(
                    part for part in row["seq_cols"].split(",") if part.strip()
                ),
                label_col=row["label_col"],
                regression=row["regression"].strip().lower() == "true",
                num_labels=_optional_int(row["num_labels"], where, "num_labels"),
            )
        )
    for splits in found.values():
        splits.sort(key=lambda s: _split_rank(s.split))
    return found


def _read_reports(path: Path) -> dict[tuple[str, str], Reports]:
    found = {}
    for row in _rows(path):
        found[(row["collection"], row["dataset"])] = Reports(
            archive=row["archive"],
            n_bytes=int(row["bytes"]),
            sha256=row["sha256"],
            paths=tuple(part for part in row["reports"].split("|") if part),
        )
    return found


def _verify(dataset: Dataset) -> None:
    """Recompute the rollup from the tables it summarises, and compare.

    Thirteen values that are functions of the two combined tables plus the
    reference split, and are stated in the rollup as well. One pass over 2,106
    rows, buying the only guarantee available here: the tables were copied whole.
    """
    where = dataset.benchmark_id
    reference = dataset.reference_split

    if reference is not None:
        on_reference = {
            m.check: m for m in dataset.measurements if m.split == reference
        }
        for name in CLASS_CHECKS:
            measured = on_reference.get(name)
            stated = dataset.flags[name]
            derived = measured.flag if measured is not None else None
            if stated != derived:
                raise RunInvalid(
                    f"{where}: the rollup flags {name!r} as {stated!r}, and "
                    f"combined_classes_results.csv flags it {derived!r} on the "
                    f"reference split ({reference})."
                )

        probes = [
            m for m in on_reference.values() if m.kind == "probe" and m.au_roc is not None
        ]
        strongest = max(probes, key=lambda m: m.au_roc) if probes else None
        if (strongest.check if strongest else None) != dataset.strongest_probe:
            raise RunInvalid(
                f"{where}: the rollup names {dataset.strongest_probe!r} as the "
                f"strongest probe on {reference}, and the class table's strongest "
                f"there is {strongest.check if strongest else None!r}."
            )
        stated_auroc = dataset.max_probe_auroc
        derived_auroc = strongest.au_roc if strongest else None
        if not _close(stated_auroc, derived_auroc):
            raise RunInvalid(
                f"{where}: the rollup states max_probe_auroc {stated_auroc!r} and "
                f"the class table's strongest probe on {reference} reaches "
                f"{derived_auroc!r}."
            )

    stated_leakage = dataset.flags[LEAKAGE_SCAN]
    derived_leakage = worst_flag(c.flag for c in dataset.leakage)
    if stated_leakage != derived_leakage:
        raise RunInvalid(
            f"{where}: the rollup flags the leakage scan {stated_leakage!r} and "
            f"the worst over its {len(dataset.leakage)} split comparison(s) is "
            f"{derived_leakage!r}."
        )

    worst = dataset.worst_leakage()
    if not _close(
        dataset.max_leaked_test_pct, worst.leaked_queries_pct if worst else None
    ):
        raise RunInvalid(
            f"{where}: the rollup states max_leaked_test_pct "
            f"{dataset.max_leaked_test_pct!r} and the worst comparison leaked "
            f"{worst.leaked_queries_pct if worst else None!r}."
        )

    overall = worst_flag(dataset.flags[name] for name in CHECKS)
    if dataset.overall_verdict != overall:
        raise RunInvalid(
            f"{where}: overall_verdict is {dataset.overall_verdict!r} but the "
            f"worst of the ten flags is {overall!r}."
        )
    class_worst = worst_flag(dataset.flags[name] for name in CLASS_CHECKS)
    if dataset.worst_class_flag != class_worst:
        raise RunInvalid(
            f"{where}: worst_class_flag is {dataset.worst_class_flag!r} but the "
            f"worst of the nine class-distribution checks is {class_worst!r}."
        )


def _close(a: float | None, b: float | None, tolerance: float = 1e-6) -> bool:
    if a is None or b is None:
        return a is b or (a is None and b is None)
    return abs(a - b) <= tolerance


def read(root: Path | str = DATA) -> Run:
    """Every table under `root`, joined into 93 datasets and checked.

    Takes a path rather than resolving package data, because `data/` is a
    repository directory and not something a wheel carries. `run()` is the cached
    call for the committed one.
    """
    root = Path(root)

    rollup_rows = _rows(root / "dataset_level_summary.csv")
    header = tuple(rollup_rows[0]) if rollup_rows else ()
    if header != ROLLUP_COLUMNS:
        raise RunInvalid(
            f"dataset_level_summary.csv: unexpected columns. Missing "
            f"{sorted(set(ROLLUP_COLUMNS) - set(header))}, unexpected "
            f"{sorted(set(header) - set(ROLLUP_COLUMNS))}. The audit's output "
            f"moved; read what changed before re-copying it."
        )

    measurements = _read_measurements(root / "combined_classes_results.csv")
    leakage = _read_leakage(root / "combined_splits_results.csv")
    splits = _read_splits(root / "splits.csv")
    reports = _read_reports(root / "reports.csv")
    core_set = {
        (row["collection"], row["dataset"]): int(row["selection_rank"])
        for row in _rows(root / "core_set.csv")
    }

    datasets: dict[str, Dataset] = {}
    for row in rollup_rows:
        key = (row["collection"], row["dataset"])
        where = f"{key[0]}:{key[1]}"
        if where in datasets:
            raise RunInvalid(f"{where} appears twice in dataset_level_summary.csv")

        flags = {
            name: _flag(row[f"flag: {name}"], where, f"flag: {name}") for name in CHECKS
        }
        probe_auroc_by_split = {}
        for split in ("test", "test_leftout", "train", "val"):
            value = _optional_float(
                row[f"max_probe_auroc: {split}"], where, f"max_probe_auroc: {split}"
            )
            if value is not None:
                probe_auroc_by_split[split] = value

        dataset = Dataset(
            collection=key[0],
            dataset_name=key[1],
            task_category=row["task_category"],
            task_category_grouped=row["task_category_grouped"],
            molecular_level=row["molecular_level"],
            task_type=row["task_type"],
            species=row["species"],
            n_species=_optional_int(row["n_species"], where, "n_species"),
            train_size=_optional_int(row["train_size"], where, "train_size"),
            total_size=_optional_int(row["total_size"], where, "total_size"),
            min_seq_length=_optional_int(row["min_seq_length"], where, "min_seq_length"),
            max_seq_length=_optional_int(row["max_seq_length"], where, "max_seq_length"),
            reference_split=row["reference_split"].strip() or None,
            overall_verdict=row["overall_verdict"].strip() or None,
            worst_class_flag=row["worst_class_flag"].strip() or None,
            n_checks_failed=_optional_int(row["n_checks_failed"], where, "n_checks_failed") or 0,
            n_checks_warning=_optional_int(row["n_checks_warning"], where, "n_checks_warning") or 0,
            n_checks_unknown=_optional_int(row["n_checks_unknown"], where, "n_checks_unknown") or 0,
            n_checks_reported=_optional_int(row["n_checks_reported"], where, "n_checks_reported") or 0,
            n_checks_scored=_optional_int(row["n_checks_scored"], where, "n_checks_scored") or 0,
            strongest_probe=row["strongest_probe"].strip() or None,
            max_probe_auroc=_optional_float(row["max_probe_auroc"], where, "max_probe_auroc"),
            max_probe_accuracy=_optional_float(row["max_probe_accuracy"], where, "max_probe_accuracy"),
            max_leaked_test_pct=_optional_float(row["max_leaked_test_pct"], where, "max_leaked_test_pct"),
            max_leaked_train_pct=_optional_float(row["max_leaked_train_pct"], where, "max_leaked_train_pct"),
            worst_leakage_comparison=row["worst_leakage_comparison"].strip() or None,
            n_split_comparisons=_optional_int(row["n_split_comparisons"], where, "n_split_comparisons"),
            flags=flags,
            probe_auroc_by_split=probe_auroc_by_split,
            measurements=tuple(
                sorted(
                    measurements.get(key, ()),
                    key=lambda m: (_split_rank(m.split), CLASS_CHECKS.index(m.check)),
                )
            ),
            leakage=tuple(leakage.get(key, ())),
            splits=tuple(splits.get(key, ())),
            reports=reports.get(key),
            core_set_rank=core_set.get(key),
        )
        _verify(dataset)
        datasets[where] = dataset

    _cover(datasets, measurements, "combined_classes_results.csv")
    _cover(datasets, leakage, "combined_splits_results.csv", allow_missing=1)
    _cover(datasets, splits, "splits.csv")
    _cover(datasets, reports, "reports.csv")

    missing_rank = sorted(set(core_set) - {(d.collection, d.dataset_name) for d in datasets.values()})
    if missing_rank:
        raise RunInvalid(
            f"core_set.csv names {missing_rank}, which the rollup does not carry."
        )

    return Run(
        datasets=datasets,
        by_check=tuple(_rows(root / "summary_by_check.csv")),
        by_collection=tuple(_rows(root / "summary_by_collection.csv")),
        by_task_category=tuple(_rows(root / "summary_by_task_category.csv")),
        exclusions=tuple(_rows(root / "exclusion_summary.csv")),
        gates=tuple(
            Gate(
                step=int(row["step"]),
                criterion=row["criterion"],
                requirement=row["requirement"],
                threshold=row["threshold"],
                n_in=int(row["n_in"]),
                n_removed=int(row["n_removed"]),
                n_out=int(row["n_out"]),
            )
            for row in _rows(root / "core_set_criteria.csv")
        ),
        selection_trace=tuple(_rows(root / "core_set_selection_trace.csv")),
        provenance=json.loads((root / "provenance.json").read_text(encoding="utf-8")),
    )


def _cover(
    datasets: dict[str, Dataset],
    other: dict,
    name: str,
    allow_missing: int = 0,
) -> None:
    """Both files describe the same corpus, or the build stops naming the gap.

    A dataset in the rollup and not in a table renders an empty section; one in a
    table and not in the rollup is a row nobody sees and nobody notices is stale.

    `allow_missing` is the leakage table's one exception:
    `miRBench:AGO2_eCLIP_Klimentova2022` has one split and nothing to compare it
    against. Bounded at one, so a second dataset losing its comparisons still
    fails.
    """
    ours = {(d.collection, d.dataset_name) for d in datasets.values()}
    theirs = set(other)
    missing = sorted(ours - theirs)
    extra = sorted(theirs - ours)
    if len(missing) > allow_missing or extra:
        raise RunInvalid(
            f"{name} and dataset_level_summary.csv do not cover the same corpus. "
            f"In the rollup and not in {name}: {missing}. In {name} and not in the "
            f"rollup: {extra}."
        )


@functools.lru_cache(maxsize=1)
def run() -> Run:
    """The committed run, read and checked once."""
    return read(DATA)
