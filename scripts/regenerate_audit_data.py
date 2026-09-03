#!/usr/bin/env python3
"""Copy one published audit run into `data/`, and record what was copied.

The run this repository publishes is produced in `GenBench2_paper` by two
workflows: `dataset_qc` measures every split of every included dataset, and
`dataset_audit` rolls those measurements up to one row per dataset and selects the
Core Set. Both write into a `runs/` tree that is gitignored there. So there is no
path a site build can read that does not assume a checkout, and no call it can make
that does not reach the network -- which is why the small tables are copied in here
and the site renders from the copy.

**Copied byte for byte, not projected.** `gb_leaderboard` keeps 30 of the rollup's
42 columns because the registry it carries already states the other twelve, and two
copies of `task_category` are two copies that can disagree. This repository has no
registry: it is the audit, its facets come from the audit, and the twelve columns
are the only place it has to get them. Keeping every byte also makes the committed
copy diffable against the record once the deposition lands, which is the check that
`data/provenance.json`'s digests exist to support.

Two files are derived rather than copied, and both are derived from files that are
themselves published:

`splits.csv`
    The seven per-collection metadata TSVs the QC run writes, concatenated. It is
    what says which splits a dataset has and which sequence columns were measured
    on it -- and therefore which reports exist, since a class report is written per
    split per sequence column.

`reports.csv`
    Read out of the 93 archives by listing them: name, size, digest, and every HTML
    file inside. Listed rather than composed from a naming rule, because the rule
    has an exception -- a dataset with two sequence columns gets a report for each
    plus a `merged` one -- and a manifest that guessed would send a reader to a
    file that is not there.

Usage:
    scripts/regenerate_audit_data.py --source PATH   # rewrite data/
    scripts/regenerate_audit_data.py --check         # exit 1 if it has drifted

PATH is a `GenBench2_paper` checkout; `$GB_AUDIT_RUN` is used when `--source` is
omitted. Without either it exits 2 rather than reporting no drift against nothing,
which is the distinction `gb_leaderboard`'s regenerators make when the package they
compare against is missing.

**This one cannot run in CI**, and that is worth being loud about. Its source is a
private repository no runner can reach, so `--check` here is a maintainer command.
What CI can check is everything downstream of `data/`: that the tables agree with
each other, that the catalogue is what they build, and that the site is what the
catalogue renders.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

sys.path.insert(0, str(REPO / "src"))

from gb_audit import audit, zenodo  # noqa: E402

ENV_VAR = "GB_AUDIT_RUN"

AUDIT_RUN = Path("runs") / "dataset_audit" / "published"
QC_RUN = Path("runs") / "dataset_qc" / "published"

# Copied unchanged. The left column is the name in `data/`; the right is where it
# sits in the checkout. Flat here because `data/` is one archived run and a reader
# opening it should see the run rather than the directory layout of the machine it
# was produced on.
COPIED = {
    "dataset_level_summary.csv": AUDIT_RUN / "audit" / "dataset_level_summary.csv",
    "summary_by_check.csv": AUDIT_RUN / "audit" / "summary_by_check.csv",
    "summary_by_collection.csv": AUDIT_RUN / "audit" / "summary_by_collection.csv",
    "summary_by_task_category.csv": AUDIT_RUN / "audit" / "summary_by_task_category.csv",
    "exclusion_summary.csv": AUDIT_RUN / "audit" / "exclusion_summary.csv",
    "core_set.csv": AUDIT_RUN / "core_set" / "core_set.csv",
    "core_set_criteria.csv": AUDIT_RUN / "core_set" / "core_set_criteria.csv",
    "core_set_selection_trace.csv": AUDIT_RUN / "core_set" / "core_set_selection_trace.csv",
    "combined_classes_results.csv": QC_RUN / "combined_classes_results.csv",
    "combined_splits_results.csv": QC_RUN / "combined_splits_results.csv",
}

METADATA_DIR = QC_RUN / "metadata"
ARCHIVE_DIR = QC_RUN / "zenodo"

SPLITS_COLUMNS = (
    "collection",
    "dataset",
    "split",
    "seq_cols",
    "label_col",
    "regression",
    "num_labels",
)
REPORTS_COLUMNS = ("collection", "dataset", "archive", "bytes", "sha256", "reports")


class SourceUnreachable(RuntimeError):
    """The run is not where we were told to look."""


def locate(source: str | None) -> Path:
    if not source:
        raise SourceUnreachable(
            f"no run given. Pass --source, or set ${ENV_VAR}, to a GenBench2_paper "
            f"checkout. There is nothing else to read it from: the runs/ tree is "
            f"gitignored upstream and the Zenodo record carries the QC tables but "
            f"not the audit's rollup, which this repository is the publisher of."
        )
    root = Path(source).expanduser().resolve()
    for required in (AUDIT_RUN, QC_RUN):
        if not (root / required).is_dir():
            raise SourceUnreachable(
                f"{root} has no {required}. That is a published run directory -- "
                f"normally a symlink to the dated run that was uploaded."
            )
    return root


def run_label(root: Path, published: Path) -> str:
    """The name of the run directory, after following `published`.

    Read off the resolved path rather than the symlink, because `published` is a
    pointer and the label is what a reader needs to find the run again.
    """
    return (root / published).resolve().name


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_splits(root: Path) -> list[dict[str, str]]:
    """Every split of every included dataset, from the QC run's own metadata.

    The seven files cover exactly the 93 included datasets and their 234 splits,
    which is the same set the rollup covers -- `audit.read()` asserts that rather
    than trusting it, because two files agreeing about a corpus is the thing that
    stops being true first when a dataset is added.
    """
    rows: list[dict[str, str]] = []
    directory = root / METADATA_DIR
    for path in sorted(directory.glob("*_metadata.tsv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                rows.append(
                    {
                        "collection": row["collection"],
                        # Renamed once, here, to the audit tables' own spelling.
                        # `genomic-benchmarks-qc` writes `dataset` and the corpus
                        # metadata writes `dataset_name`; the run publishes both,
                        # and a join key spelled two ways inside one directory is
                        # a join that silently returns nothing.
                        "dataset": row["dataset_name"],
                        "split": row["split"],
                        "seq_cols": row["seq_cols"],
                        "label_col": row["label_col"],
                        "regression": row["regression"],
                        "num_labels": row["num_labels"],
                    }
                )
    if not rows:
        raise SourceUnreachable(f"{directory} holds no *_metadata.tsv files")
    rows.sort(key=lambda row: (row["collection"], row["dataset"], row["split"]))
    return rows


def read_reports(root: Path, known: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    """The 93 report archives, listed rather than predicted.

    An archive is matched to a dataset by looking its whole stem up in `known`,
    not by splitting on the first hyphen. `<collection>-<dataset>.zip` is not a
    decodable name: `genomic-benchmarks-human_ocr_ensembl.zip` splits into
    collection `genomic` on the obvious rule, and did, silently, until seven
    datasets went missing from the manifest. The record is flat and the join is
    one-way, so the rollup's own pairs are what the name is resolved against.
    """
    directory = root / ARCHIVE_DIR
    rows = []
    for path in sorted(directory.glob("*.zip")):
        payload = path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            inside = sorted(
                name for name in archive.namelist() if name.endswith(".html")
            )
        stem = path.stem
        if stem not in known:
            raise SourceUnreachable(
                f"{path.name} does not name any dataset in the rollup, so nothing "
                f"can say whose reports it holds. Archives are "
                f"<collection>-<dataset>.zip and the pair has to be one the audit "
                f"covers."
            )
        collection, dataset = known[stem]
        # Every path inside is prefixed with the archive's own directory, which is
        # the archive name without its suffix. Stripped here so the manifest names
        # the report and not the container, which is what a link needs.
        prefix = f"{stem}/"
        stripped = []
        for name in inside:
            if not name.startswith(prefix):
                raise SourceUnreachable(
                    f"{path.name} holds {name!r}, which is outside its own "
                    f"{prefix} directory. The archive is not the shape "
                    f"gb_audit.reports expects, and unpacking it would write "
                    f"beside the other 92 rather than inside its own."
                )
            stripped.append(name[len(prefix):])
        rows.append(
            {
                "collection": collection,
                "dataset": dataset,
                "archive": path.name,
                "bytes": str(len(payload)),
                "sha256": digest_bytes(payload),
                # One cell, `|`-separated. A row per report would be 423 rows to
                # say what 93 rows say, and the manifest's unit is the archive:
                # it is what gets fetched, checked and unpacked.
                "reports": "|".join(stripped),
            }
        )
    if not rows:
        raise SourceUnreachable(f"{directory} holds no report archives")
    return rows


def render_table(columns: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[column] for column in columns])
    return buffer.getvalue().encode("utf-8")


def known_datasets(rollup: bytes) -> dict[str, tuple[str, str]]:
    """`<collection>-<dataset>` -> the pair, for every dataset the audit covers.

    The archive names are resolved against this rather than parsed, for the reason
    `read_reports` gives.
    """
    reader = csv.DictReader(io.StringIO(rollup.decode("utf-8")))
    return {
        f"{row['collection']}-{row['dataset']}": (row["collection"], row["dataset"])
        for row in reader
    }


def assemble(root: Path) -> dict[str, bytes]:
    """Everything `data/` should hold, as bytes, before anything is written."""
    files = {name: (root / source).read_bytes() for name, source in COPIED.items()}
    files["splits.csv"] = render_table(SPLITS_COLUMNS, read_splits(root))
    files["reports.csv"] = render_table(
        REPORTS_COLUMNS,
        read_reports(root, known_datasets(files["dataset_level_summary.csv"])),
    )
    return files


def provenance(root: Path, files: dict[str, bytes]) -> dict:
    return {
        "audit_run": run_label(root, AUDIT_RUN),
        "qc_run": run_label(root, QC_RUN),
        "source_repository": "GenBench2_paper",
        "zenodo_record_id": zenodo.RECORD_ID,
        "zenodo_concept_record_id": zenodo.CONCEPT_RECORD_ID,
        "zenodo_record_registered": zenodo.registered(),
        "copied": datetime.date.today().isoformat(),
        "generated_by": "scripts/regenerate_audit_data.py",
        "files": {
            name: {"bytes": len(payload), "sha256": digest_bytes(payload)}
            for name, payload in sorted(files.items())
        },
    }


def render_provenance(document: dict) -> bytes:
    return (json.dumps(document, indent=2) + "\n").encode("utf-8")


def drift(files: dict[str, bytes], recorded: dict) -> list[str]:
    """What differs between the run and the committed copy, file by file."""
    problems = []
    for name, payload in sorted(files.items()):
        path = DATA / name
        if not path.exists():
            problems.append(f"{name}: absent from data/")
        elif path.read_bytes() != payload:
            problems.append(
                f"{name}: the copy is {path.stat().st_size:,} bytes, the run is "
                f"{len(payload):,}"
                if path.stat().st_size != len(payload)
                else f"{name}: same size, different bytes"
            )
    for stray in sorted(DATA.glob("*.csv")):
        if stray.name not in files:
            problems.append(f"{stray.name}: in data/ and not in the run")
    stated = json.loads((DATA / "provenance.json").read_text(encoding="utf-8"))
    for field in ("audit_run", "qc_run"):
        if stated.get(field) != recorded[field]:
            problems.append(
                f"provenance.{field}: the copy says {stated.get(field)!r}, the run "
                f"says {recorded[field]!r}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source",
        default=os.environ.get(ENV_VAR),
        help=f"a GenBench2_paper checkout; defaults to ${ENV_VAR}",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit 1 instead of rewriting data/",
    )
    args = parser.parse_args()

    try:
        root = locate(args.source)
        files = assemble(root)
    except (SourceUnreachable, OSError, KeyError) as exc:
        print(f"regenerate_audit_data: {exc}", file=sys.stderr)
        return 2

    recorded = provenance(root, files)

    if DATA.exists() and (DATA / "provenance.json").exists():
        problems = drift(files, recorded)
        if not problems:
            print(
                f"regenerate_audit_data: data/ states audit run "
                f"{recorded['audit_run']}, QC run {recorded['qc_run']}, "
                f"{len(files)} files, clear"
            )
            return 0
        for problem in problems:
            print(f"regenerate_audit_data: {problem}", file=sys.stderr)
        if args.check:
            print(
                "regenerate_audit_data: run without --check to rewrite data/, then "
                "read the diff before committing it.",
                file=sys.stderr,
            )
            return 1
    elif args.check:
        print("regenerate_audit_data: data/ is absent", file=sys.stderr)
        return 1

    DATA.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        (DATA / name).write_bytes(payload)
    (DATA / "provenance.json").write_bytes(render_provenance(recorded))

    # Read back through the same reader the site uses, so a copy that is internally
    # inconsistent -- a rollup flag that disagrees with the class table beside it,
    # a dataset in one file and not another -- stops here rather than at the first
    # page that renders it.
    try:
        run = audit.read(DATA)
    except audit.RunInvalid as exc:
        print(f"regenerate_audit_data: {exc}", file=sys.stderr)
        return 2

    print(
        f"regenerate_audit_data: wrote {len(files) + 1} files to "
        f"{DATA.relative_to(REPO)} from audit run {recorded['audit_run']} and QC "
        f"run {recorded['qc_run']}: {len(run.datasets)} datasets, "
        f"{run.n_splits} splits, {run.n_reports} reports"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
