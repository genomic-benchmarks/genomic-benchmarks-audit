#!/usr/bin/env python3
"""Copy one published audit run into `data/`, and record what was copied.

The run is produced in `GenBench2_paper` by three workflows: `dataset_qc` measures
every split of every included dataset, `dataset_audit` rolls those up to one row per
dataset, and `core_set` applies the six gates over that rollup and a joint model of
the same features. All three write into a gitignored `runs/` tree, so the small
tables are copied in here and the site renders from the copy.

**Copied byte for byte, not projected.** This repository is the audit and its facets
come from the audit, so it keeps all 42 rollup columns rather than the 30 a registry
would let it drop. Keeping every byte also makes the committed copy diffable against
the record, which is what `data/provenance.json`'s digests support.

Three files are derived rather than copied, all from files that are themselves
published:

`splits.csv`
    The seven per-collection metadata TSVs the QC run writes, concatenated, plus
    the URL each split's file is served from. It is what says which splits a
    dataset has and which sequence columns were measured on it -- and therefore
    which reports exist, since a class report is written per split per sequence
    column.

`sources.csv`
    One row per dataset: the licence its splits are published under, whether that
    licence permits this project to republish them, and the DOI attribution is
    owed to. Derived from the corpus metadata records rather than from a run,
    because no run table carries any of the three -- and this repository states in
    its own Data availability that the collections are republished with the
    attribution they require, which is a promise nothing here could keep while the
    values stayed upstream.

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
omitted. Without either it exits 2 rather than reporting no drift against nothing.

**This one cannot run in CI.** Its source is a private repository no runner can
reach, so `--check` here is a maintainer command. What CI checks is everything
downstream of `data/`: that the tables agree, that the catalogue is what they build,
and that the site is what the catalogue renders.
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
# The Core Set is selected by a pipeline of its own, downstream of both. It has to
# be: its last gate reads a score the audit cannot compute -- what the ten checks'
# features recover jointly -- and a selection made inside the audit would put the
# two pipelines each behind the other. So the chain runs one way, dataset_qc ->
# dataset_audit -> qc_baseline -> core_set, and this is the fourth link's output.
CORE_RUN = Path("runs") / "core_set" / "published"

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
    "core_set.csv": CORE_RUN / "core_set" / "core_set.csv",
    "core_set_criteria.csv": CORE_RUN / "core_set" / "core_set_criteria.csv",
    "core_set_selection_trace.csv": CORE_RUN / "core_set" / "core_set_selection_trace.csv",
    # Every dataset the selection considered, not only the ten it returned -- and
    # the only table in `data/` carrying what the checks recover *jointly*. The
    # site needs it per dataset rather than per member: a reader on a page for a
    # dataset that did not make the Core Set is owed the number it was judged on.
    "core_set_candidates.csv": CORE_RUN / "core_set" / "core_set_candidates.csv",
    "combined_classes_results.csv": QC_RUN / "combined_classes_results.csv",
    "combined_splits_results.csv": QC_RUN / "combined_splits_results.csv",
}

METADATA_DIR = QC_RUN / "metadata"
ARCHIVE_DIR = QC_RUN / "zenodo"

# The corpus metadata records, `datasets/<collection>/<collection>_metadata.json`,
# one per collection. The only source read here that is not a run output: it is the
# corpus definition the QC workflow reads, and what the run keeps of it is a verdict
# -- `validation/<collection>_metadata_validation.flag` -- rather than a copy. So a
# working tree that has moved on since the run would describe a different corpus
# from the one the tables were measured on, and `read_splits` requires every split
# in the run's own metadata to be present here rather than trusting that it is.
CORPUS_DIR = Path("datasets")

SPLITS_COLUMNS = (
    "collection",
    "dataset",
    "split",
    "seq_cols",
    "label_col",
    "regression",
    "num_labels",
    "source_url",
)
SOURCES_COLUMNS = (
    "collection",
    "dataset",
    # The DOI attribution is owed to, resolved: the dataset's own where it has one,
    # the collection's where it does not. Both are carried, so a page can say which
    # of the two it is quoting -- they are equal where the dataset inherits.
    "doi",
    "collection_doi",
    "licence",
    "licence_url",
    "redistribution",
    "licence_note",
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
    for required in (AUDIT_RUN, QC_RUN, CORE_RUN):
        if not (root / required).is_dir():
            raise SourceUnreachable(
                f"{root} has no {required}. That is a published run directory -- "
                f"normally a symlink to the dated run that was uploaded."
            )
    if not (root / CORPUS_DIR).is_dir():
        raise SourceUnreachable(
            f"{root} has no {CORPUS_DIR}. That is the curated corpus itself, and "
            f"its per-collection metadata records are where the licence, the DOI "
            f"and the download URL are written down. No run carries them."
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


def read_corpus(root: Path) -> dict[tuple[str, str], dict]:
    """The seven corpus metadata records, each dataset's licence and DOI resolved.

    Both are stated per collection and overridden per dataset, and the override is
    not the rare case it looks like: eleven datasets carry their own licence, and
    mRNABench's collection-level one grants nothing at all -- `redistribution:
    unknown`, because the collection was published with no licence stated -- so
    every one of its retained datasets overrides it at its true upstream. A reader
    of this table wants the answer for the dataset in front of them, so the
    fallback is applied once, here, for the same reason the join key is renamed
    once: a fallback applied in two places is a fallback that will one day be
    applied in one.

    `dataset_doi` carries the literal string `collection_doi` where the dataset has
    no DOI of its own, which is a sentinel and not a DOI; 67 of the 93 use it.
    """
    found: dict[tuple[str, str], dict] = {}
    directory = root / CORPUS_DIR
    for path in sorted(directory.glob("*/*_metadata.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        collection = record["collection"]
        for entry in record["datasets"]:
            licence = entry.get("licence") or record["licence"]
            doi = entry.get("dataset_doi") or ""
            found[(collection, entry["dataset_name"])] = {
                "collection": collection,
                "dataset": entry["dataset_name"],
                "doi": record["collection_doi"] if doi == "collection_doi" else doi,
                "collection_doi": record["collection_doi"],
                # Null where the source states none, which is not the same as
                # permissive and is written through as empty rather than as a
                # word that would read like one.
                "licence": licence.get("name") or "",
                "licence_url": licence.get("url") or "",
                "redistribution": licence["redistribution"],
                # Why the answer is what it is -- the evidence, not a restatement.
                # It travels with the value because `denied` without the reason
                # reads as this project's decision rather than the source's.
                "licence_note": licence.get("note") or "",
                "urls": {
                    split: entry_split["dataset_url"]
                    for split, entry_split in (entry.get("split_metadata") or {}).items()
                },
            }
    if not found:
        raise SourceUnreachable(
            f"{directory} holds no <collection>/<collection>_metadata.json "
            f"records. They are where the licence, the DOI and the download URL "
            f"are written down; no run table carries any of the three."
        )
    return found


def read_splits(root: Path, corpus: dict[tuple[str, str], dict]) -> list[dict[str, str]]:
    """Every split of every included dataset, from the QC run's own metadata.

    The seven files cover the same 93 datasets and 234 splits the rollup covers,
    which `audit.read()` asserts rather than trusts.

    `source_url` is the one column not in them, and it is joined on per split
    rather than per dataset because that is the grain it varies at: 81 of the 93
    datasets are served as one file per split. It is the route back to the data
    itself, which for the sixteen splits this project may not republish is the only
    route there is.
    """
    rows: list[dict[str, str]] = []
    directory = root / METADATA_DIR
    for path in sorted(directory.glob("*_metadata.tsv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                # Renamed once, here, to the audit tables' own spelling.
                # `genomic-benchmarks-qc` writes `dataset` and the corpus metadata
                # writes `dataset_name`; the run publishes both, and a join key
                # spelled two ways inside one directory is a join that silently
                # returns nothing.
                key = (row["collection"], row["dataset_name"])
                where = f"{key[0]}:{key[1]} {row['split']}"
                record = corpus.get(key)
                if record is None:
                    raise SourceUnreachable(
                        f"{where} is in the run's metadata and in no record under "
                        f"{CORPUS_DIR}, so nothing says what licence it is "
                        f"published under or where its file is served from."
                    )
                if row["split"] not in record["urls"]:
                    raise SourceUnreachable(
                        f"{where} is in the run's metadata and not in that "
                        f"dataset's record under {CORPUS_DIR}, which carries "
                        f"{sorted(record['urls'])}. The corpus has moved since "
                        f"this run was measured; the two no longer describe one "
                        f"corpus and joining them would attribute a split to the "
                        f"wrong file."
                    )
                rows.append(
                    {
                        "collection": key[0],
                        "dataset": key[1],
                        "split": row["split"],
                        "seq_cols": row["seq_cols"],
                        "label_col": row["label_col"],
                        "regression": row["regression"],
                        "num_labels": row["num_labels"],
                        "source_url": record["urls"][row["split"]],
                    }
                )
    if not rows:
        raise SourceUnreachable(f"{directory} holds no *_metadata.tsv files")
    rows.sort(key=lambda row: (row["collection"], row["dataset"], row["split"]))
    return rows


def read_sources(
    corpus: dict[tuple[str, str], dict], known: dict[str, tuple[str, str]]
) -> list[dict[str, str]]:
    """One row per dataset: who it credits, and what it may be republished under.

    Driven by the rollup's own pairs rather than by the corpus record, which also
    carries the 54 datasets that were curated and not measured. The two files then
    describe one corpus, which is what `audit.read()` checks on the way back in.
    """
    rows = []
    for key in sorted(known.values()):
        record = corpus.get(key)
        if record is None:
            raise SourceUnreachable(
                f"{key[0]}:{key[1]} is in the rollup and in no record under "
                f"{CORPUS_DIR}. Every dataset the audit covers has a licence, "
                f"whether or not that licence permits republication."
            )
        rows.append({column: record[column] for column in SOURCES_COLUMNS})
    return rows


def read_reports(root: Path, known: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    """The 93 report archives, listed rather than predicted.

    An archive is matched by looking its whole stem up in `known`, not by splitting
    on the first hyphen: `<collection>-<dataset>.zip` is not a decodable name, and
    `genomic-benchmarks-human_ocr_ensembl.zip` splits into collection `genomic` on
    the obvious rule. The join runs one way, against the rollup's own pairs.
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
    corpus = read_corpus(root)
    known = known_datasets(files["dataset_level_summary.csv"])
    files["splits.csv"] = render_table(SPLITS_COLUMNS, read_splits(root, corpus))
    files["sources.csv"] = render_table(SOURCES_COLUMNS, read_sources(corpus, known))
    files["reports.csv"] = render_table(REPORTS_COLUMNS, read_reports(root, known))
    return files


def provenance(root: Path, files: dict[str, bytes]) -> dict:
    return {
        "audit_run": run_label(root, AUDIT_RUN),
        "qc_run": run_label(root, QC_RUN),
        "core_set_run": run_label(root, CORE_RUN),
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
    for field in ("audit_run", "qc_run", "core_set_run"):
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
                f"Core Set run {recorded['core_set_run']}, "
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
