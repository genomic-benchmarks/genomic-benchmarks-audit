#!/usr/bin/env python3
"""Download the QC output from the Zenodo record into `data/`, and record what was downloaded.

The record is the only source this reads. Three files in `data/` come from it:

`combined_classes_results.csv`, `combined_splits_results.csv`
    Copied byte for byte, not projected. Keeping every byte makes the committed
    copy diffable against the record, which is what `data/provenance.json`'s
    digests support.

`reports.csv`
    Read out of the 93 archives by listing them: name, size, digest, and every HTML
    file inside. Listed rather than composed from a naming rule, because the rule
    has an exception -- a dataset with two sequence columns gets a report for each
    plus a `merged` one -- and a manifest that guessed would send a reader to a
    file that is not there.

The other eleven tables in `data/` are not on the record. They are kept in this
repository as they are, and nothing writes them. This reads one of them,
`dataset_level_summary.csv`, for the datasets whose archives to download.

Usage:
    scripts/regenerate_audit_data.py           # rewrite the three files
    scripts/regenerate_audit_data.py --check   # exit 1 if they have drifted
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

sys.path.insert(0, str(REPO / "src"))

from gb_audit import audit, zenodo  # noqa: E402

REPORTS_COLUMNS = ("collection", "dataset_name", "archive", "bytes", "sha256", "reports")


class SourceUnreachable(RuntimeError):
    """The record does not hold what this expects."""


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_reports(scratch: Path, known: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    """The 93 report archives, downloaded and listed rather than predicted.

    One per dataset in `known`, by the name the record uses. Sorted by that name,
    which is the order the manifest has always listed them in.
    """
    rows = []
    for stem, (collection, dataset) in sorted(
        known.items(), key=lambda item: zenodo.archive_name(*item[1])
    ):
        name = zenodo.archive_name(collection, dataset)
        payload = zenodo.fetch(name, scratch / name).read_bytes()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            inside = sorted(
                member for member in archive.namelist() if member.endswith(".html")
            )
        # Every path inside is prefixed with the archive's own directory, which is
        # the archive name without its suffix. Stripped here so the manifest names
        # the report and not the container, which is what a link needs.
        prefix = f"{stem}/"
        stripped = []
        for member in inside:
            if not member.startswith(prefix):
                raise SourceUnreachable(
                    f"{name} holds {member!r}, which is outside its own "
                    f"{prefix} directory. The archive is not the shape "
                    f"gb_audit.reports expects, and unpacking it would write "
                    f"beside the other 92 rather than inside its own."
                )
            stripped.append(member[len(prefix):])
        rows.append(
            {
                "collection": collection,
                "dataset_name": dataset,
                "archive": name,
                "bytes": str(len(payload)),
                "sha256": digest_bytes(payload),
                # One cell, `|`-separated. A row per report would be 423 rows to
                # say what 93 rows say, and the manifest's unit is the archive:
                # it is what gets fetched, checked and unpacked.
                "reports": "|".join(stripped),
            }
        )
    if not rows:
        raise SourceUnreachable("dataset_level_summary.csv names no datasets")
    return rows


def render_table(columns: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[column] for column in columns])
    return buffer.getvalue().encode("utf-8")


def known_datasets(rollup: bytes) -> dict[str, tuple[str, str]]:
    """`<collection>-<dataset>` -> the pair, for every dataset the audit covers."""
    reader = csv.DictReader(io.StringIO(rollup.decode("utf-8")))
    pairs = ((row["collection"], row["dataset_name"]) for row in reader)
    return {f"{collection}-{dataset}": (collection, dataset) for collection, dataset in pairs}


def assemble(scratch: Path) -> dict[str, bytes]:
    """The three files the record supplies, as bytes, before anything is written."""
    files = {
        name: zenodo.fetch(name, scratch / name).read_bytes()
        for name in zenodo.SUMMARY_TABLES
    }
    known = known_datasets((DATA / "dataset_level_summary.csv").read_bytes())
    files["reports.csv"] = render_table(REPORTS_COLUMNS, read_reports(scratch, known))
    return files


def provenance(files: dict[str, bytes]) -> dict:
    return {
        "zenodo_record_id": zenodo.RECORD_ID,
        "zenodo_concept_record_id": zenodo.CONCEPT_RECORD_ID,
        "zenodo_record_version": zenodo.VERSION,
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
    """What differs between the record and the committed copy, file by file."""
    problems = []
    for name, payload in sorted(files.items()):
        path = DATA / name
        if not path.exists():
            problems.append(f"{name}: absent from data/")
        elif path.read_bytes() != payload:
            problems.append(
                f"{name}: the copy is {path.stat().st_size:,} bytes, the record is "
                f"{len(payload):,}"
                if path.stat().st_size != len(payload)
                else f"{name}: same size, different bytes"
            )
    stated = json.loads((DATA / "provenance.json").read_text(encoding="utf-8"))
    for field in ("zenodo_record_id", "zenodo_record_version"):
        if stated.get(field) != recorded[field]:
            problems.append(
                f"provenance.{field}: the copy says {stated.get(field)!r}, the "
                f"record is {recorded[field]!r}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit 1 instead of rewriting data/",
    )
    args = parser.parse_args()

    try:
        with tempfile.TemporaryDirectory(prefix="gb-audit-regenerate-") as scratch:
            files = assemble(Path(scratch))
    except (SourceUnreachable, zenodo.RecordUnavailable, OSError, KeyError) as exc:
        print(f"regenerate_audit_data: {exc}", file=sys.stderr)
        return 2

    recorded = provenance(files)
    label = f"Zenodo record {zenodo.RECORD_ID}, version {zenodo.VERSION}"

    if (DATA / "provenance.json").exists():
        problems = drift(files, recorded)
        if not problems:
            print(f"regenerate_audit_data: data/ matches {label}, {len(files)} files, clear")
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
        print("regenerate_audit_data: data/provenance.json is absent", file=sys.stderr)
        return 1

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
        f"{DATA.relative_to(REPO)} from {label}: {len(run.datasets)} datasets, "
        f"{run.n_splits} splits, {run.n_reports} reports"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
