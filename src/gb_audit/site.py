"""Render the site from `docs/` into an output directory.

Reads the committed `docs/data/catalogue.json`, fills the templates in
`docs/templates/`, server-renders every figure with `charts.py`, copies the
assets, the vendored table library and the unpacked reports beside them, and
writes the result to `--out`:

    index.html                the corpus, in six figures
    catalogue.html            all 93 datasets, filterable
    checks.html               the ten checks, and what each returned
    core-set.html             the four gates, and the 10 that cleared them
    reports.html              the 423 reports, and how to get them
    methods.html              what was measured, and what it does not say
    datasets/<slug>.html      one page per dataset, 93 of them
    view/<archive>/<report>   one framed viewer per report, 423 of them
    qc-reports/<archive>/...  the reports themselves, unchanged

**The output is not committed, and that is the whole design.** Every number the
site publishes lives in `docs/data/catalogue.json`, which *is* committed and
gated in CI, so a change to a published number is already diffable in git
history. The HTML carries no number of its own -- it is a render of that file
plus the copy in `docs/templates/`. Committing it would buy no review the JSON
does not already give, and would cost a 93-page diff every time a template
changed. So CI builds it and hands the directory to Pages; nothing here writes
into the checkout.

**No number in the copy is typed.** The templates carry `{{placeholders}}` and
this module computes what goes in them from the catalogue -- 93, 10, 57, 34, 75
and the six heavily-overlapping datasets are all counted here at build time. A
count in prose that nothing recomputes is a sentence that goes stale silently,
and the whole argument of the site is that its numbers came from somewhere.

**No word in the copy is typed here either.** The words this module renders
server-side -- a flag's name, the sentence for an absent measurement -- come from
the `#site-copy` block in `templates/base.html`, the same block the scripts read.
`tools/vocab_check.py` scans `docs/` for prose and neither a `.js` nor a `.py`
file is prose to it, so a label written in either would be site copy that avoids
the vocabulary check.

**The catalogue is checked against the run before anything is rendered.** The
figures are drawn from `audit.run()` and the tables are fetched from
`catalogue.json`; if those two disagree, the site shows a figure and a number
that contradict each other, and neither says which is right. So `build()` rebuilds
the catalogue from the run and refuses to render if the committed bytes differ.

Usage:
    gb-audit render                    # into site/
    gb-audit render --out /tmp/preview
    gb-audit render --serve

`site/` is gitignored. Local review needs a server rather than `file://`, because
the catalogue page fetches `data/catalogue.json` and a `file://` fetch is a
cross-origin request every browser refuses -- hence `--serve`.
"""

from __future__ import annotations

import functools
import html
import http.server
import json
import re
import shutil
import socketserver
from pathlib import Path

from . import audit, catalogue, charts, reports, zenodo

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "docs"
TEMPLATES = SOURCE / "templates"
PARTS = TEMPLATES / "parts"
CATALOGUE = SOURCE / "data" / "catalogue.json"
DEFAULT_OUT = REPO / "site"

# Copied verbatim into the output. `data/` is the catalogue the pages fetch;
# `vendor/` is the table library, which is a file in this repository rather than
# a CDN call for the reasons docs/vendor/README.md gives.
COPIED = ("assets", "vendor", "data")

PLACEHOLDER = re.compile(r"\{\{(?P<name>[a-z0-9_]+)\}\}")
COPY_BLOCK = re.compile(
    r'<script type="application/json" id="site-copy">(?P<json>.*?)</script>', re.S
)
# What a path component of the built site may contain. Checked rather than
# slugified, because a slug is not reversible and the point of
# `qc-reports/<archive>/<path>` is that the path inside the site is the path
# inside the record.
URL_SAFE = re.compile(r"[A-Za-z0-9_.\-]+")


class TemplateError(RuntimeError):
    """A placeholder the build has no value for.

    Silent in a naive `str.replace` loop, which leaves the placeholder in place
    and publishes `{{n_fail}}` to a reader. Raised instead, because the numbers
    are the argument of the page.

    The reverse is deliberately not an error: `counts()` computes every number
    the site can state and each page uses the few it needs, so a value with no
    placeholder is the normal case rather than a mistake.
    """


class StaleCatalogue(RuntimeError):
    """The committed catalogue is not what the pinned tables produce.

    Raised rather than worked around, because the figures come from the run and
    the tables come from the catalogue: rendering both would publish a page whose
    picture and whose number disagree.
    """


# ------------------------------------------------------------- machinery ---


def fill(template: str, values: dict[str, str], where: str) -> str:
    """Substitute every `{{name}}`, raising on one with no value."""

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in values:
            raise TemplateError(
                f"{where}: no value for {{{{{name}}}}}. Either the template asks "
                f"for something site.py does not compute, or the name is "
                f"misspelled on one side."
            )
        return values[name]

    return PLACEHOLDER.sub(replace, template)


def plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


def site_copy(values: dict[str, str] | None = None) -> dict:
    """The reader-facing words, read out of the shell template.

    Parsed from `base.html` rather than kept in a `copy.json`, because
    `vocab_check.py` reads `.html` and does not read `.json`: a copy file of its
    own would be a copy file the vocabulary check never sees.

    **Filled with the same values the rest of the page is filled with.** The copy
    block carries `{{placeholders}}` too -- "the {{n_checks}} checks" rather than
    "the ten checks" -- and `render_page` substitutes them on the way out, so the
    browser reads finished sentences. Passing the same values here is what keeps
    the words this module renders identical to the words the scripts render from
    the page; without it, Python would quote a placeholder where JavaScript quoted
    a number, and the two halves of one site would disagree in public.

    Values are **not** escaped by the caller. They are copy from a file this
    repository controls, some of it carrying entities on purpose, and escaping it
    would publish the entity rather than the character.
    """
    match = COPY_BLOCK.search((TEMPLATES / "base.html").read_text(encoding="utf-8"))
    if match is None:
        raise TemplateError(
            "templates/base.html: no #site-copy block. It holds every word the "
            "site renders, and both this module and assets/site.js read it."
        )
    block = match.group("json")
    if values is not None:
        block = fill(block, values, "templates/base.html #site-copy")
    return json.loads(block)


def part(name: str, values: dict[str, str]) -> str:
    """One prose fragment, from `templates/parts/`.

    A note that appears on some pages and not others is still prose, so it is a
    template rather than a string in this file.
    """
    template = (PARTS / f"{name}.html").read_text(encoding="utf-8")
    return fill(template, values, f"templates/parts/{name}.html")


def shown(path: Path) -> str:
    """A path as an error message should print it: repo-relative where it can be.

    `relative_to` raises on a path outside the repository, which in an error
    message means the report of the first problem is replaced by a second one.
    """
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def load_document() -> dict:
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))


def check_fresh(run: audit.Run) -> None:
    """Refuse to render a catalogue that is not what the tables produce."""
    if not CATALOGUE.is_file():
        raise StaleCatalogue(
            f"{shown(CATALOGUE)} does not exist. Run "
            f"`gb-audit build` to write it from the tables in data/."
        )
    expected = catalogue.render(catalogue.build(run))
    if CATALOGUE.read_text(encoding="utf-8") != expected:
        raise StaleCatalogue(
            f"{shown(CATALOGUE)} is not what data/ produces. The site's "
            f"figures are drawn from the tables and its tables are fetched from "
            f"the catalogue, so rendering now would publish a figure and a number "
            f"that disagree. Run `gb-audit build` and commit the result."
        )


# ----------------------------------------------------------------- values ---


def record_line(document: dict) -> str:
    """The footer's one line about where the reports and full tables live."""
    provenance = document["provenance"]
    values = {
        "record_id": html.escape(str(provenance["zenodo_record_id"])),
        "record_url": html.escape(zenodo.public_record_url(), quote=True),
        "full_table": html.escape(zenodo.FULL_TABLE),
        "n_datasets": str(document["totals"]["n_datasets"]),
        "n_reports": str(document["totals"]["n_reports"]),
    }
    name = "record_published" if zenodo.registered() else "record_unpublished"
    return part(name, values)


def counts(document: dict) -> dict[str, str]:
    """Every number the copy states, counted from the catalogue.

    `overall_verdict` in the catalogue is the worst flag the ten checks returned
    on the dataset's reference split, so counting `Fail` over it answers "returned
    Fail on at least one check" -- and its complement is what the Core Set's
    integrity, leakage and separability gates then narrow. That equivalence is why
    these numbers can be read off one column, and why this function is the only
    place any of them is written down.
    """
    totals = document["totals"]
    datasets = document["datasets"]
    verdicts = totals["verdicts"]
    provenance = document["provenance"]
    facets = document["facets"]

    heavily = [d for d in datasets if (d["max_leaked_test_pct"] or 0) >= 50]
    complete = [d for d in heavily if d["max_leaked_test_pct"] == 100.0]
    unpacked = totals.get("n_reports_unpacked")

    values = {
        "n_datasets": str(totals["n_datasets"]),
        "n_collections": str(totals["n_collections"]),
        "n_splits": str(totals["n_splits"]),
        "n_reports": str(totals["n_reports"]),
        "n_reports_unpacked": str(unpacked if unpacked is not None else 0),
        "n_curated": str(totals["n_curated"]),
        "n_excluded": str(totals["n_excluded"]),
        "n_exclusion_reasons": str(totals["n_exclusion_reasons"]),
        "n_checks": str(len(document["checks"])),
        "n_probe_checks": str(
            sum(1 for c in document["checks"] if c["kind"] == "probe")
        ),
        "n_integrity_checks": str(
            sum(1 for c in document["checks"] if c["kind"] == "integrity")
        ),
        # The checks that run on one split, as against the leakage scan, which
        # runs on a pair of them. Counted rather than typed as "nine" because the
        # sentence "those nine run per split" is one a new check would falsify.
        "n_split_checks": str(
            sum(1 for c in document["checks"] if c["kind"] != "leakage scan")
        ),
        "n_flags": str(len(document["flags"])),
        "n_scored_flags": str(
            sum(1 for flag in document["flags"] if flag != "Unknown")
        ),
        "n_pass": str(verdicts["Pass"]),
        "n_warning": str(verdicts["Warning"]),
        "n_fail": str(verdicts["Fail"]),
        "n_flagged": str(verdicts["Warning"] + verdicts["Fail"]),
        "n_no_fail": str(totals["n_datasets"] - verdicts["Fail"]),
        "n_probed": str(totals["n_probed"]),
        "median_probe_auroc": f"{totals['median_max_probe_auroc']:.3f}",
        "n_probe_over_0_7": str(totals["n_probe_auroc_over_0_7"]),
        "n_leakage_scanned": str(totals["n_leakage_scanned"]),
        "n_leakage_unscanned": str(
            totals["n_datasets"] - totals["n_leakage_scanned"]
        ),
        "n_with_any_leakage": str(totals["n_with_any_leakage"]),
        "n_leakage_over_50": str(totals["n_leakage_over_50_pct"]),
        "n_leakage_complete": str(len(complete)),
        "median_leaked_pct": f"{totals['median_max_leaked_test_pct']:.2f}",
        "core_set_size": str(totals["core_set_size"]),
        "n_gates": str(len(document["gates"])),
        "n_species": str(len(facets["species"])),
        "n_task_categories": str(len(facets["task_category_grouped"])),
        "audit_run": html.escape(str(provenance["audit_run"])),
        "qc_run": html.escape(str(provenance["qc_run"])),
        "package_version": html.escape(str(provenance["package_version"])),
        "record_id": html.escape(str(provenance["zenodo_record_id"])),
        "schema_version": str(document["schema_version"]),
        "record_line": record_line(document),
    }
    # The word form of every count small enough to be spelled in a sentence.
    # Added rather than substituted so a heading can still say "10" where a
    # paragraph says "ten", and so no template has to choose between a computed
    # number and a readable one.
    for name in (
        "n_checks", "n_probe_checks", "n_integrity_checks", "n_split_checks",
        "n_flags", "n_scored_flags", "n_gates", "n_collections",
        "n_leakage_unscanned", "core_set_size",
    ):
        word = cardinal(int(values[name]))
        values[f"{name}_word"] = word
        # A sentence-initial word form. A separate key rather than a filter in the
        # template syntax, because `{{name}}` matching one lowercase identifier is
        # what makes an unfilled placeholder impossible to miss.
        values[f"{name}_cap"] = word[:1].upper() + word[1:]
    return values


# ------------------------------------------------------------- fragments ---


# How this site spells a small number in a sentence. The counts themselves are
# computed -- nothing here is typed into the prose -- but "those 9 run per split"
# is a sentence written by a machine, and "those nine" is one written for a
# reader. Only the structural counts get a word form: the corpus figures are
# large, and 93 is not improved by being spelled out.
CARDINALS = {
    0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
}


def cardinal(n: int) -> str:
    return CARDINALS.get(n, f"{n:,}")


def number(value: int | None, template: str = "{:,}") -> str:
    """A count, or an em dash where the tables carry none.

    Not `0`. The one dataset whose training split is not released has no training
    row count, and printing zero there would state a measurement nobody made.
    """
    return "&mdash;" if value is None else template.format(value)


def text(value: str | None) -> str:
    """One field, escaped, with an em dash for a field the tables leave empty."""
    return "&mdash;" if value in (None, "") else html.escape(value)


def flag_chip(flag: str | None, copy: dict) -> str:
    """One flag as a labelled chip, with a blank that says it is blank.

    A missing flag renders as an em dash carrying the sentence for it, never as
    an empty cell: an empty cell is read as nothing to report, and a check that
    had nothing to run on is a different statement from a check that returned
    Pass -- and from one that returned Unknown.
    """
    if flag is None:
        return (
            f'<span class="flag flag-blank" title="{html.escape(copy["flag_help"]["blank"], quote=True)}">'
            f"&mdash;</span>"
        )
    return (
        f'<span class="flag flag-{html.escape(flag, quote=True)}" '
        f'title="{html.escape(copy["flag_help"][flag], quote=True)}">'
        f'{html.escape(copy["flags"][flag])}</span>'
    )


def measurement(value: float | None, template: str, copy: dict) -> str:
    """One measured figure, or the word for its absence -- never a stand-in zero.

    `null` here means the check had nothing to run on. Formatting it as `0.000`
    would publish the most reassuring possible number in place of no number at
    all, which is the failure `docs/vendor/README.md` records as the reason the
    table supplies its own sorters.
    """
    if value is None:
        return (
            f'<span class="absent" title="{html.escape(copy["flag_help"]["blank"], quote=True)}">'
            f"&mdash;</span>"
        )
    return template.format(value)


def figures(items) -> str:
    return "\n".join(charts.render(figure) for figure in items)


def check_rows(document: dict, copy: dict) -> str:
    """One row per check: what it is, and how the 93 datasets came out on it."""
    order = [check["name"] for check in document["checks"]]
    kinds = {check["name"]: check["kind"] for check in document["checks"]}
    rows = []
    for name in order:
        tally = {"Pass": 0, "Warning": 0, "Fail": 0, "Unknown": 0, None: 0}
        for dataset in document["datasets"]:
            tally[dataset["flags"].get(name)] += 1
        scored = sum(tally[f] for f in ("Pass", "Warning", "Fail", "Unknown"))
        cells = "".join(
            f'<td class="right num">{tally[flag] or "&mdash;"}</td>'
            for flag in ("Pass", "Warning", "Fail", "Unknown")
        )
        blank = (
            f'<td class="right num">{tally[None]}</td>'
            if tally[None]
            else '<td class="right num">&mdash;</td>'
        )
        rows.append(
            f'    <tr>\n'
            f'      <th scope="row" class="wrap">{html.escape(name)}</th>\n'
            f'      <td class="wrap"><span class="kind">'
            f'{html.escape(copy["kinds"][kinds[name]])}</span></td>\n'
            f"      {cells}{blank}\n"
            f'      <td class="right num">{scored}</td>\n'
            f"    </tr>"
        )
    return "\n".join(rows)


def gate_rows(document: dict) -> str:
    """The Core Set funnel as a table: one row per gate, in the order applied."""
    rows = []
    for gate in document["gates"]:
        rows.append(
            f'    <tr>\n'
            f'      <td class="right num">{gate["step"]}</td>\n'
            f'      <th scope="row" class="wrap">{html.escape(gate["criterion"])}</th>\n'
            f'      <td class="wrap">{html.escape(gate["requirement"])}</td>\n'
            f'      <td class="wrap"><code>{html.escape(gate["threshold"])}</code></td>\n'
            f'      <td class="right num">{gate["n_in"]}</td>\n'
            f'      <td class="right num">{gate["n_removed"] or "&mdash;"}</td>\n'
            f'      <td class="right num">{gate["n_out"]}</td>\n'
            f"    </tr>"
        )
    return "\n".join(rows)


def exclusion_rows(document: dict) -> str:
    """Why 54 curated datasets are not in the audit, as the curation recorded it."""
    rows = []
    for entry in sorted(
        document["exclusions"], key=lambda e: -int(e["n_datasets"])
    ):
        rows.append(
            f'    <tr>\n'
            f'      <td class="right num">{html.escape(str(entry["n_datasets"]))}</td>\n'
            f'      <td class="wrap">{html.escape(entry["excluded"])}</td>\n'
            f'      <td class="wrap fine">{html.escape(entry["collections"])}</td>\n'
            f"    </tr>"
        )
    return "\n".join(rows)


def core_rows(document: dict, copy: dict) -> str:
    """The Core Set, in the rank the selection assigned."""
    members = sorted(
        (d for d in document["datasets"] if d["in_core_set"]),
        key=lambda d: (d["core_set_rank"] is None, d["core_set_rank"]),
    )
    rows = []
    for dataset in members:
        rows.append(
            f'    <tr>\n'
            f'      <td class="right num">{dataset["core_set_rank"]}</td>\n'
            f'      <th scope="row" class="wrap">{dataset_link(dataset)}</th>\n'
            f'      <td class="wrap">{text(dataset["task_type"])}</td>\n'
            f'      <td class="wrap">{text(dataset["species"])}</td>\n'
            f'      <td class="right num">{number(dataset["total_size"])}</td>\n'
            f'      <td>{flag_chip(dataset["overall_verdict"], copy)}</td>\n'
            f'      <td class="right num">'
            f'{measurement(dataset["max_probe_auroc"], "{:.3f}", copy)}</td>\n'
            f'      <td class="right num">'
            f'{measurement(dataset["max_leaked_test_pct"], "{:.2f}%", copy)}</td>\n'
            f"    </tr>"
        )
    return "\n".join(rows)


def dataset_link(dataset: dict, prefix: str = "") -> str:
    """A dataset's name as a link, wrapping after the collection."""
    return (
        f'<a href="{prefix}datasets/{dataset["slug"]}.html">'
        f'<span class="collection-part">{html.escape(dataset["collection"])}:</span><wbr>'
        f'{html.escape(dataset["dataset_name"])}</a>'
    )


def split_rows(dataset: dict, copy: dict) -> str:
    rows = []
    for split in dataset["splits"]:
        row_class = ' class="is-reference"' if split["is_reference"] else ""
        reference = (
            ' <span class="ref-mark" title="This dataset\'s reference split: the '
            'split the rollup figures on this page were measured on.">reference</span>'
            if split["is_reference"]
            else ""
        )
        rollup = split["rollup"]
        # Parenthesised, because "Pass 6 Unknown" set side by side reads as one
        # compound flag rather than as a flag and a count of what was not scored.
        unknown = (
            f' <span class="fine">({rollup["n_unknown"]} Unknown)</span>'
            if rollup["n_unknown"]
            else ""
        )
        rows.append(
            f"    <tr{row_class}>\n"
            f'      <th scope="row"><code>{html.escape(split["split"])}</code>{reference}</th>\n'
            f'      <td class="wrap">'
            f'{", ".join(f"<code>{html.escape(c)}</code>" for c in split["seq_cols"])}</td>\n'
            f'      <td>{flag_chip(rollup["flag"], copy)}{unknown}</td>\n'
            f'      <td class="right num">{rollup["n_scored"]}</td>\n'
            f'      <td class="wrap fine">{text(split["strongest_probe"])}</td>\n'
            f'      <td class="right num">'
            f'{measurement(split["max_probe_auroc"], "{:.3f}", copy)}</td>\n'
            f"    </tr>"
        )
    return "\n".join(rows)


def leakage_rows(dataset: dict, copy: dict) -> str:
    rows = []
    for pair in dataset["leakage"]:
        rows.append(
            f'    <tr>\n'
            f'      <th scope="row" class="wrap"><code>{html.escape(pair["query_split"])}</code> '
            f'in <code>{html.escape(pair["target_split"])}</code></th>\n'
            f'      <td>{flag_chip(pair["flag"], copy)}</td>\n'
            f'      <td class="right num">'
            f'{measurement(pair["leaked_queries_pct"], "{:.2f}%", copy)}</td>\n'
            f'      <td class="right num">'
            f'{measurement(pair["leaked_targets_pct"], "{:.2f}%", copy)}</td>\n'
            f"    </tr>"
        )
    return "\n".join(rows)


def siblings(dataset: dict, document: dict) -> str:
    """The other datasets in this collection, as links.

    Server-rendered rather than fetched, which is what lets a dataset page carry
    no script at all: everything on it is already known at build time, and a page
    that needs JavaScript to offer its own navigation is a page that loses it
    whenever the fetch does.
    """
    family = [
        d
        for d in document["datasets"]
        if d["collection"] == dataset["collection"]
        and d["benchmark_id"] != dataset["benchmark_id"]
    ]
    if not family:
        return ""
    links = ", ".join(
        dataset_link(other, prefix="../")
        for other in sorted(family, key=lambda d: d["dataset_name"])
    )
    return (
        f'<p class="fine">{len(family)} other '
        f'{plural(len(family), "dataset")} in '
        f'<strong>{html.escape(dataset["collection"])}</strong>: {links}</p>'
    )


def view_path(archive_stem: str, report_path: str) -> str:
    """Where the framed viewer for one report goes.

    The report's own path with its separators folded into hyphens, so the file
    name still reads as the thing it frames and the two directories the viewer
    sits under are the same for every report on a dataset.
    """
    return f"view/{archive_stem}/{report_path.replace('/', '-')}"


def report_items(dataset: dict, copy: dict, prefix: str = "") -> str:
    """One dataset's reports as links, class reports before leakage scans."""
    entry = dataset["reports"]
    if entry is None or not entry["files"]:
        return f'<p class="note">{html.escape(copy["reports"]["none"])}</p>'
    stem = entry["archive"].removesuffix(".zip")
    unpacked = entry["state"] == "unpacked"
    items = []
    for report in entry["files"]:
        kind = copy["reports"][
            "class_kind" if report["kind"] == "class" else "leakage_kind"
        ]
        title = html.escape(report["title"])
        if unpacked:
            href = f"{prefix}{view_path(stem, report['path'])}"
            body = f'<a href="{href}">{title}</a>'
        else:
            body = f"<span>{title}</span>"
        # "leakage scan" carries a space, and a space in a class attribute is
        # two classes rather than one hyphenated name.
        marker = report["kind"].replace(" ", "-")
        items.append(
            f'    <li class="report report-{marker}">{body} '
            f'<span class="fine">{html.escape(kind)}</span></li>'
        )
    return '<ul class="reports">\n' + "\n".join(items) + "\n  </ul>"


# ----------------------------------------------------------------- pages ---


def render_page(
    name: str, document: dict, extra: dict[str, str] | None = None
) -> str:
    """One page: the named content template inside `base.html`."""
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    content = (TEMPLATES / f"{name}.html").read_text(encoding="utf-8")

    values = counts(document)
    values.update(extra or {})
    values.setdefault("root", "")
    values.setdefault("scripts", "")
    values.setdefault("head_extra", "")

    filled = fill(content, values, f"templates/{name}.html")
    return fill(base, {**values, "content": filled}, "templates/base.html")


def landing(run: audit.Run, document: dict, copy: dict) -> str:
    corpus = charts.corpus_figures(run)
    by_slug = {figure.slug: figure for figure in corpus}
    return render_page(
        "index",
        document,
        {
            "title": "Overview",
            "fig_check_bars": charts.render(by_slug["check-bars"]),
            "fig_probe_auroc": charts.render(by_slug["probe-auroc"]),
            "fig_leakage": charts.render(by_slug["leakage"]),
            "fig_collection_bars": charts.render(by_slug["collection-bars"]),
        },
    )


def checks_page(run: audit.Run, document: dict, copy: dict) -> str:
    by_slug = {f.slug: f for f in charts.corpus_figures(run)}
    return render_page(
        "checks",
        document,
        {
            "title": "The checks",
            "check_rows": check_rows(document, copy),
            "fig_flag_matrix": charts.render(by_slug["flag-matrix"]),
            "fig_check_bars": charts.render(by_slug["check-bars"]),
        },
    )


def core_set_page(run: audit.Run, document: dict, copy: dict) -> str:
    by_slug = {f.slug: f for f in charts.corpus_figures(run)}
    return render_page(
        "core-set",
        document,
        {
            "title": "The Core Set",
            "fig_funnel": charts.render(by_slug["core-set-funnel"]),
            "gate_rows": gate_rows(document),
            "core_rows": core_rows(document, copy),
        },
    )


def catalogue_page(document: dict) -> str:
    return render_page(
        "catalogue",
        document,
        {
            "title": "The datasets",
            "head_extra": (
                '<link rel="stylesheet" '
                'href="vendor/tabulator-6.5.2/tabulator.min.css">'
            ),
            "scripts": (
                '<script src="vendor/tabulator-6.5.2/tabulator.min.js"></script>\n'
                '<script src="assets/catalogue.js"></script>'
            ),
        },
    )


def reports_page(document: dict, copy: dict) -> str:
    entries = [d for d in document["datasets"] if d["reports"]]
    states = {"unpacked": 0, "linked": 0, "unpublished": 0}
    for dataset in entries:
        states[dataset["reports"]["state"]] += 1
    rows = []
    for dataset in sorted(entries, key=lambda d: d["benchmark_id"]):
        entry = dataset["reports"]
        by_kind = {"class": 0, "leakage scan": 0}
        for report in entry["files"]:
            by_kind[report["kind"] if report["kind"] == "class" else "leakage scan"] += 1
        rows.append(
            f'    <tr>\n'
            f'      <th scope="row" class="wrap">{dataset_link(dataset)}</th>\n'
            f'      <td class="right num">{by_kind["class"]}</td>\n'
            f'      <td class="right num">{by_kind["leakage scan"] or "&mdash;"}</td>\n'
            f'      <td class="right num">{entry["bytes"] / 1048576:.1f} MB</td>\n'
            f'      <td class="wrap">{report_items(dataset, copy)}</td>\n'
            f"    </tr>"
        )
    return render_page(
        "reports",
        document,
        {
            "title": "The reports",
            "report_rows": "\n".join(rows),
            "n_datasets_unpacked": str(states["unpacked"]),
            "n_datasets_absent": str(states["linked"] + states["unpublished"]),
            "report_state": part(
                "reports_present" if states["unpacked"] else "reports_absent",
                counts(document),
            ),
        },
    )


def methods_page(document: dict, copy: dict) -> str:
    return render_page(
        "methods",
        document,
        {
            "title": "Methods",
            "exclusion_rows": exclusion_rows(document),
            "check_rows": check_rows(document, copy),
        },
    )


def dataset_page(
    dataset: dict, measured: audit.Dataset, document: dict, copy: dict
) -> str:
    """One dataset's page: what the ten checks returned, and what they do not say."""
    drawn = {f.slug: f for f in charts.dataset_figures(measured)}
    reference = dataset["reference_split"]
    corpus = counts(document)

    core = (
        part(
            "core_member",
            {**corpus, "core_set_rank": str(dataset["core_set_rank"])},
        )
        if dataset["in_core_set"]
        else part("core_absent", corpus)
    )

    probe = (
        part(
            "probe_reached",
            {
                "strongest_probe": html.escape(dataset["strongest_probe"] or ""),
                "max_probe_auroc": f'{dataset["max_probe_auroc"]:.3f}',
                "reference_split": html.escape(reference or ""),
            },
        )
        if dataset["max_probe_auroc"] is not None
        else part("probe_absent", {})
    )

    if not dataset["leakage"]:
        leakage = part(
            "leakage_absent",
            {
                "n_dataset_splits_word": cardinal(len(dataset["splits"])),
                "split_word": plural(len(dataset["splits"]), "split"),
            },
        )
    elif dataset["max_leaked_test_pct"]:
        worst = max(dataset["leakage"], key=lambda p: p["leaked_queries_pct"] or 0)
        leakage = part(
            "leakage_found",
            {
                "leaked_pct": f'{worst["leaked_queries_pct"]:.2f}',
                "query_split": html.escape(worst["query_split"]),
                "target_split": html.escape(worst["target_split"]),
                "reverse_pct": f'{worst["leaked_targets_pct"] or 0:.2f}',
                "n_comparisons_word": cardinal(len(dataset["leakage"])),
                "comparison_word": plural(len(dataset["leakage"]), "comparison"),
            },
        )
    else:
        leakage = part(
            "leakage_none",
            {
                "n_comparisons_word": cardinal(len(dataset["leakage"])),
                "comparison_word": plural(len(dataset["leakage"]), "comparison"),
            },
        )

    return render_page(
        "dataset",
        document,
        {
            "title": dataset["benchmark_id"],
            "root": "../",
            "benchmark_id": html.escape(dataset["benchmark_id"]),
            "collection": html.escape(dataset["collection"]),
            "dataset_name": html.escape(dataset["dataset_name"]),
            "task_category": text(dataset["task_category"]),
            "task_type": text(dataset["task_type"]),
            "molecular_level": text(dataset["molecular_level"]),
            "species": text(dataset["species"]),
            "n_species": str(dataset["n_species"]),
            "total_size": number(dataset["total_size"]),
            "train_size": number(dataset["train_size"]),
            "min_seq_length": number(dataset["min_seq_length"]),
            "max_seq_length": number(dataset["max_seq_length"]),
            "n_dataset_splits": str(len(dataset["splits"])),
            "split_word": plural(len(dataset["splits"]), "split"),
            "reference_split": html.escape(reference or ""),
            "rollup_flag": flag_chip(dataset["overall_verdict"], copy),
            "n_checks_failed": str(dataset["n_checks_failed"]),
            "n_checks_warning": str(dataset["n_checks_warning"]),
            "n_checks_unknown": str(dataset["n_checks_unknown"]),
            "n_checks_scored": str(dataset["n_checks_scored"]),
            "n_checks_reported": str(dataset["n_checks_reported"]),
            "core_note": core,
            "probe_note": probe,
            "leakage_note": leakage,
            "split_rows": split_rows(dataset, copy),
            "report_items": report_items(dataset, copy, prefix="../"),
            "siblings": siblings(dataset, document),
            "fig_checks": charts.render(drawn["dataset-checks"]),
            "fig_probes": charts.render(drawn["dataset-probes"]),
            "leakage_section": leakage_section(dataset, drawn, copy, corpus),
        },
    )


def leakage_section(
    dataset: dict, drawn: dict, copy: dict, corpus: dict[str, str]
) -> str:
    """The split-comparison section, or the sentence that replaces it.

    A dataset with one split has no pair to scan, and rendering the table anyway
    leaves column headers with nothing under them -- which reads as a page that
    failed to load rather than as a measurement nobody made.
    """
    splits = len(dataset["splits"])
    values = {
        **corpus,
        "n_dataset_splits_word": cardinal(splits),
        "split_word": plural(splits, "split"),
    }
    if not dataset["leakage"] or "dataset-leakage" not in drawn:
        return part("leakage_section_absent", values)
    return part(
        "leakage_section",
        {
            **values,
            "fig_leakage": charts.render(drawn["dataset-leakage"]),
            "leakage_rows": leakage_rows(dataset, copy),
        },
    )


def report_view(
    dataset: dict, report: dict, document: dict, copy: dict
) -> str:
    """One report, framed in the site's own chrome.

    An iframe rather than a re-parse. `genomic-benchmarks-qc` writes a complete
    document with its own stylesheet, and lifting its body into this page would
    put two stylesheets in one scope and make the report's appearance depend on
    the site's. Framing it keeps the reader inside the site's navigation while the
    report renders exactly as the tool wrote it -- and the raw file is one click
    away for anyone who would rather have it on its own.
    """
    stem = dataset["reports"]["archive"].removesuffix(".zip")
    raw = f"../../qc-reports/{stem}/{report['path']}"
    kind = copy["reports"][
        "class_kind" if report["kind"] == "class" else "leakage_kind"
    ]
    return render_page(
        "report_view",
        document,
        {
            "title": f'{dataset["benchmark_id"]} · {report["title"]}',
            "root": "../../",
            "benchmark_id": html.escape(dataset["benchmark_id"]),
            "dataset_href": f'../../datasets/{dataset["slug"]}.html',
            "report_title": html.escape(report["title"]),
            "report_kind": html.escape(kind),
            "report_description": html.escape(report_description(report, copy)),
            "raw_href": html.escape(raw, quote=True),
        },
    )


def report_description(report: dict, copy: dict) -> str:
    """What one report holds, in the vocabulary the rest of the site uses."""
    if report["kind"] == "class":
        return (
            f'The nine class-distribution checks on the {report["split"]} split, '
            f'measured on the {report["seq_col"]} column: the distribution of each '
            f"feature by class, and the fit of each probe."
        )
    first, second = report["pair"]
    return (
        f"The leakage scan between {first} and {second}: the sequences of one "
        f"split that were also found in the other, listed individually rather "
        f"than only counted."
    )


# ----------------------------------------------------------------- build ---


def safe_component(value: str, what: str) -> str:
    if not URL_SAFE.fullmatch(value):
        raise TemplateError(
            f"{what}: {value!r} cannot be a path component, so it has no URL. "
            f"Either the naming convention changed or URL_SAFE needs widening -- "
            f"deliberately, not silently."
        )
    return value


def build(out: Path | None = None, *, run: audit.Run | None = None) -> dict:
    """Render every page and copy every asset. Returns what was written."""
    out = DEFAULT_OUT if out is None else out
    run = audit.run() if run is None else run
    check_fresh(run)

    document = load_document()
    copy = site_copy(counts(document))

    if out.exists():
        # Rebuilt from scratch rather than merged into: a stale file left behind
        # by a renamed template is a page that is still being served and that
        # nothing regenerates.
        shutil.rmtree(out)
    out.mkdir(parents=True)

    pages: dict[Path, str] = {
        Path("index.html"): landing(run, document, copy),
        Path("catalogue.html"): catalogue_page(document),
        Path("checks.html"): checks_page(run, document, copy),
        Path("core-set.html"): core_set_page(run, document, copy),
        Path("reports.html"): reports_page(document, copy),
        Path("methods.html"): methods_page(document, copy),
    }

    n_views = 0
    for dataset in document["datasets"]:
        slug = safe_component(dataset["slug"], dataset["benchmark_id"])
        measured = run.datasets[dataset["benchmark_id"]]
        pages[Path("datasets") / f"{slug}.html"] = dataset_page(
            dataset, measured, document, copy
        )
        entry = dataset["reports"]
        if entry is None or entry["state"] != "unpacked":
            continue
        stem = safe_component(
            entry["archive"].removesuffix(".zip"), dataset["benchmark_id"]
        )
        for report in entry["files"]:
            pages[Path(view_path(stem, report["path"]))] = report_view(
                dataset, report, document, copy
            )
            n_views += 1

    for relative, text in pages.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    for directory in COPIED:
        shutil.copytree(SOURCE / directory, out / directory)
    # The vendored library ships with its own notes for a maintainer, which are
    # not a page.
    (out / "vendor" / "README.md").unlink(missing_ok=True)

    # Pages otherwise runs Jekyll over the output, which drops directories whose
    # name begins with an underscore and rewrites what it feels like. Nothing here
    # wants templating; it has already been rendered.
    (out / ".nojekyll").write_text("")

    copied_reports = 0
    if reports.UNPACKED.is_dir():
        destination = out / reports.SITE_DIR
        shutil.copytree(
            reports.UNPACKED,
            destination,
            ignore=shutil.ignore_patterns("PROVENANCE.json", ".*"),
        )
        copied_reports = sum(1 for _ in destination.rglob("*.html"))

    return {
        "out": out,
        "pages": len(pages),
        "dataset_pages": len(document["datasets"]),
        "report_views": n_views,
        "reports_copied": copied_reports,
        "bytes": sum(p.stat().st_size for p in out.rglob("*") if p.is_file()),
    }


def serve(out: Path, port: int) -> None:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(out)
    )
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"serving {out} at http://127.0.0.1:{port}/  (ctrl-c to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()
