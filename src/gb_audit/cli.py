"""`gb-audit` -- build the catalogue, fetch the reports, render the site.

Four verbs, and the order they are meant in:

    gb-audit build     data/*.csv          -> docs/data/catalogue.json
    gb-audit fetch     Zenodo or a mirror  -> docs/reports/
    gb-audit render    the above           -> site/
    gb-audit check     everything above, without writing anything

`build` and `render` are separate because what they produce are reviewed
differently. The catalogue is committed, so a change to a published number shows
up as a diff; the site is not, because it adds no number the catalogue does not
already carry. `check` is what CI runs: it rebuilds the catalogue in memory and
compares, so a pull request that changes a number without committing the
catalogue fails rather than quietly renders something else.

`fetch` is separate from both because it is the only one that needs a network,
and everything else has to work without one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, audit, catalogue, site, zenodo


def cmd_build(args: argparse.Namespace) -> int:
    run = audit.run()
    document = catalogue.build(run)
    rendered = catalogue.render(document)
    target = site.CATALOGUE

    if args.check:
        if not target.is_file():
            print(f"{site.shown(target)} does not exist.", file=sys.stderr)
            return 1
        if target.read_text(encoding="utf-8") != rendered:
            print(
                f"{site.shown(target)} is not what data/ produces. Run "
                f"`gb-audit build` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{site.shown(target)} is current.")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    totals = document["totals"]
    print(
        f"wrote {site.shown(target)}: {totals['n_datasets']} datasets, "
        f"{totals['n_splits']} splits, {totals['n_reports']} reports, "
        f"{len(rendered):,} bytes"
    )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    # Imported here rather than at the top: it is the one command that reaches a
    # network, and `gb-audit render` should not so much as import the machinery.
    sys.path.insert(0, str(site.REPO / "scripts"))
    import fetch_reports

    forwarded = []
    if args.check:
        forwarded.append("--check")
    if args.force:
        forwarded.append("--force")
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.limit:
        forwarded += ["--limit", str(args.limit)]
    for name in args.only:
        forwarded += ["--only", name]
    forwarded += ["--jobs", str(args.jobs)]
    return fetch_reports.main(forwarded)


def cmd_render(args: argparse.Namespace) -> int:
    result = site.build(args.out)
    out = result["out"]
    print(
        f"wrote {result['pages']} pages into {out}: "
        f"{result['dataset_pages']} dataset pages, "
        f"{result['report_views']} framed reports, "
        f"{result['reports_copied']} report files copied, "
        f"{result['bytes'] / 1048576:.1f} MB"
    )
    if not result["reports_copied"]:
        print(
            "no reports in this build -- every report page says so. "
            "`gb-audit fetch` brings them in."
        )
    if args.serve:
        site.serve(out, args.port)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Everything CI needs to know, without writing into the checkout."""
    failures = []

    run = audit.run()
    print(f"tables      : {len(run.datasets)} datasets from data/")

    rendered = catalogue.render(catalogue.build(run))
    if not site.CATALOGUE.is_file():
        failures.append("docs/data/catalogue.json does not exist")
    elif site.CATALOGUE.read_text(encoding="utf-8") != rendered:
        failures.append(
            "docs/data/catalogue.json is not what data/ produces; run `gb-audit build`"
        )
    else:
        print("catalogue   : current")

    print(f"record      : {zenodo.RECORD_ID} (published={zenodo.registered()})")
    print(f"fetch route : {zenodo.route()}")

    import tempfile

    with tempfile.TemporaryDirectory(prefix="gb-audit-check-") as scratch:
        try:
            result = site.build(Path(scratch) / "site", run=run)
        except (site.TemplateError, site.StaleCatalogue) as exc:
            failures.append(str(exc))
        else:
            print(
                f"site        : {result['pages']} pages render "
                f"({result['dataset_pages']} datasets, "
                f"{result['report_views']} framed reports)"
            )

    if failures:
        print()
        for failure in failures:
            print(f"FAILED: {failure}", file=sys.stderr)
        return 1
    print("\nall checks passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gb-audit", description=__doc__)
    parser.add_argument("--version", action="version", version=f"gb-audit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="write docs/data/catalogue.json")
    build.add_argument(
        "--check",
        action="store_true",
        help="verify the committed catalogue matches data/, writing nothing",
    )
    build.set_defaults(func=cmd_build)

    fetch = sub.add_parser("fetch", help="download and unpack the report archives")
    fetch.add_argument("--check", action="store_true", help="report what is unpacked")
    fetch.add_argument("--force", action="store_true", help="re-fetch what is present")
    fetch.add_argument("--dry-run", action="store_true", help="say what would happen")
    fetch.add_argument("--limit", type=int, default=0, help="fetch at most N archives")
    fetch.add_argument("--only", action="append", default=[], metavar="ARCHIVE")
    fetch.add_argument("--jobs", type=int, default=4)
    fetch.set_defaults(func=cmd_fetch)

    render = sub.add_parser("render", help="write the site")
    render.add_argument("--out", type=Path, default=site.DEFAULT_OUT)
    render.add_argument("--serve", action="store_true", help="serve the result")
    render.add_argument("--port", type=int, default=8000)
    render.set_defaults(func=cmd_render)

    check = sub.add_parser("check", help="verify everything, writing nothing")
    check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
