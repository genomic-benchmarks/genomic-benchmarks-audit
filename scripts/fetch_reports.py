#!/usr/bin/env python3
"""Fetch the 93 report archives and unpack them where the site can render them.

90 MB that this repository deliberately does not carry. `data/reports.csv` is the
manifest -- name, byte count, SHA-256, and every path inside each archive -- so
this script knows exactly what it expects before it asks for anything, and can say
what is missing without a network at all.

**Nothing is unpacked before it is verified.** Each archive is downloaded to a
scratch file, hashed, and compared against the manifest; a mismatch is refused and
the scratch file is deleted. The failure this guards against is not corruption in
transit so much as success in transit: an endpoint that answers a 404 with a
readable HTML error page produces a file that unzips to nothing and a build that
renders 93 empty report pages without complaining once.

**A member of the archive is checked before it is written.** `zipfile.extractall`
will follow an absolute path or a `..` out of the destination, so every member is
resolved against the destination first and an escaping one aborts the archive.
These archives come from a run in this project and none of them do that; the check
costs nothing and the alternative is trusting a 90 MB download to be well behaved.

**The route is recorded, not just taken.** `docs/reports/PROVENANCE.json` says
which of the three routes served these bytes, and the site prints it, because
reports fetched from an unpublished draft are not reports a reader can go and get
for themselves. It carries no timestamp: the site is built from it and two builds
of one run must produce the same bytes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from gb_audit import zenodo  # noqa: E402

MANIFEST = REPO / "data" / "reports.csv"
UNPACKED = REPO / "docs" / "reports"
PROVENANCE = UNPACKED / "PROVENANCE.json"


class Refused(RuntimeError):
    """An archive that arrived but is not the archive the manifest describes."""


def manifest() -> list[dict]:
    """The 93 archives this run produced, in the order the manifest lists them."""
    with MANIFEST.open(newline="") as handle:
        return list(csv.DictReader(handle))


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def stem(entry: dict) -> str:
    return entry["archive"].removesuffix(".zip")


def expected_paths(entry: dict) -> list[str]:
    return [part for part in entry["reports"].split("|") if part]


def present(entry: dict) -> bool:
    """Whether this archive is already unpacked, judged by every file it lists.

    Every file and not the directory: an interrupted unpack leaves a directory
    that exists and is short, and a check that stops at `is_dir()` would call that
    done and leave the site linking to reports that are not there.
    """
    root = UNPACKED / stem(entry)
    return all((root / path).is_file() for path in expected_paths(entry))


def safe_members(archive: zipfile.ZipFile, destination: Path) -> list[zipfile.ZipInfo]:
    """Every member, once each has been shown to land inside `destination`."""
    resolved_destination = destination.resolve()
    # `ZipFile.filename` is None when the archive was opened from a buffer, and
    # `Path(None)` raises -- which would replace the report of the refusal with a
    # different error entirely, at the one moment the message matters.
    name = Path(archive.filename).name if archive.filename else "the archive"
    members = []
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != resolved_destination and resolved_destination not in target.parents:
            raise Refused(
                f"{name} contains {member.filename!r}, which resolves outside "
                f"{destination}. Nothing was unpacked."
            )
        members.append(member)
    return members


def unpack(source: Path, entry: dict) -> None:
    """Replace this archive's directory with its contents, atomically enough.

    Unpacked beside the target and moved into place, so an interrupted run leaves
    either the previous directory or none -- never half of a new one that
    `present()` would then have to be clever about.
    """
    UNPACKED.mkdir(parents=True, exist_ok=True)
    final = UNPACKED / stem(entry)
    staging = UNPACKED / f".{stem(entry)}.incoming"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(source) as archive:
            archive.extractall(staging, members=safe_members(archive, staging))
        # The archive holds one top-level directory named after itself; the site
        # wants its contents at `docs/reports/<stem>/`, not `<stem>/<stem>/`.
        inner = staging / stem(entry)
        source_dir = inner if inner.is_dir() else staging
        missing = [p for p in expected_paths(entry) if not (source_dir / p).is_file()]
        if missing:
            raise Refused(
                f"{entry['archive']} unpacked without {len(missing)} file(s) the "
                f"manifest lists, first {missing[0]!r}. Nothing was installed."
            )
        shutil.rmtree(final, ignore_errors=True)
        source_dir.replace(final)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def acquire(entry: dict, *, timeout: float) -> tuple[str, str]:
    """Fetch one archive, verify it, unpack it. Returns (archive, route)."""
    with tempfile.TemporaryDirectory(prefix="gb-audit-fetch-") as scratch:
        scratch_file = Path(scratch) / entry["archive"]
        path, route = zenodo.fetch(entry["archive"], scratch_file, timeout=timeout)
        found = digest(path)
        if found != entry["sha256"]:
            size = path.stat().st_size
            raise Refused(
                f"{entry['archive']} is not what data/reports.csv describes: got "
                f"sha256 {found} at {size:,} bytes, expected {entry['sha256']} at "
                f"{int(entry['bytes']):,}. Not unpacked."
            )
        unpack(path, entry)
    return entry["archive"], route


def write_provenance(entries: list[dict], route: str) -> None:
    """What is here, and where it came from, for the site to print."""
    installed = sorted(stem(entry) for entry in entries if present(entry))
    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE.write_text(
        json.dumps(
            {
                "route": route,
                "zenodo_record_id": zenodo.RECORD_ID,
                "zenodo_record_registered": zenodo.registered(),
                "manifest": "data/reports.csv",
                "n_expected": len(entries),
                "n_unpacked": len(installed),
                "unpacked": installed,
            },
            indent=2,
        )
        + "\n"
    )


def verify(entries: list[dict]) -> int:
    """Check what is unpacked against the manifest, touching no network."""
    missing_archives = [e for e in entries if not present(e)]
    total = sum(len(expected_paths(e)) for e in entries)
    here = sum(
        1
        for e in entries
        for p in expected_paths(e)
        if (UNPACKED / stem(e) / p).is_file()
    )
    print(f"manifest: {len(entries)} archives, {total} reports")
    print(f"unpacked: {len(entries) - len(missing_archives)} archives, {here} reports")
    if missing_archives:
        print(f"missing : {len(missing_archives)} archives, first few:")
        for entry in missing_archives[:5]:
            print(f"          {entry['archive']}")
        return 1
    print("every report the manifest lists is present.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what is unpacked against the manifest and exit; no network",
    )
    parser.add_argument(
        "--force", action="store_true", help="re-fetch archives already unpacked"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="fetch at most N archives, for a quick end-to-end check",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="ARCHIVE",
        help="fetch just this archive (repeatable); name with or without .zip",
    )
    parser.add_argument("--jobs", type=int, default=4, help="parallel downloads")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="say which route would be used and what would be fetched",
    )
    args = parser.parse_args(argv)

    entries = manifest()
    if args.only:
        wanted = {name.removesuffix(".zip") for name in args.only}
        entries = [entry for entry in entries if stem(entry) in wanted]
        unknown = wanted - {stem(entry) for entry in entries}
        if unknown:
            parser.error(f"not in the manifest: {', '.join(sorted(unknown))}")

    if args.check:
        return verify(entries)

    todo = entries if args.force else [entry for entry in entries if not present(entry)]
    if args.limit:
        todo = todo[: args.limit]

    route = zenodo.route()
    if args.dry_run:
        size = sum(int(entry["bytes"]) for entry in todo)
        print(f"route      : {route}")
        print(f"record     : {zenodo.RECORD_ID} (registered={zenodo.registered()})")
        print(f"would fetch: {len(todo)} of {len(entries)} archives, {size:,} bytes")
        for entry in todo[:5]:
            print(f"             {entry['archive']}")
        return 0 if route != "unavailable" else 1

    if not todo:
        print(f"all {len(entries)} archives are unpacked; nothing to fetch.")
        write_provenance(manifest(), route)
        return 0

    print(f"fetching {len(todo)} archives via {route}...")
    failures: list[str] = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {
            pool.submit(acquire, entry, timeout=args.timeout): entry for entry in todo
        }
        for future in concurrent.futures.as_completed(futures):
            entry = futures[future]
            done += 1
            try:
                name, _ = future.result()
            except (Refused, zenodo.RecordUnavailable) as exc:
                failures.append(entry["archive"])
                print(f"  [{done}/{len(todo)}] FAILED {entry['archive']}: {exc}")
            else:
                print(f"  [{done}/{len(todo)}] {name}")

    write_provenance(manifest(), route)
    if failures:
        print(f"\n{len(failures)} archive(s) failed; the rest were unpacked.")
        return 1
    print(f"\nunpacked {len(todo)} archives into {UNPACKED.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
