"""The flag matrix: the one figure on this site that is a table.

Every other figure in `charts.py` is a chart -- a shape drawn from numbers, where
the picture says something the numbers do not. This one is not. It is 93 rows by
ten columns of a categorical value, and the only thing the drawing adds is that a
fill is faster to scan than a word. That makes it a table whose cells are
coloured, and it is written here as one.

What the change buys, none of which an SVG gives without work:

- **Every mark is a link.** A cell opens the dataset's checks, a row label opens
  the dataset, a collection heading opens that collection in the catalogue, a
  column heading opens that check's row on the checks page. Focus order, middle
  click and "open in new tab" all come from the browser.
- **A filter is a hidden row.** In the SVG every row carries an absolute `y`, so
  narrowing to one collection means recomputing 93 transforms; here the browser
  reflows and `assets/matrix.js` only sets `hidden`.
- **A screen reader reads a cell as a sentence.** `<th scope="row">` and
  `<th scope="col">` make "GUE_v2 tf_prediction_0, Split leakage, Fail" the
  announcement, rather than 930 unlabelled rectangles.
- **The figure and its table twin are one artifact.** Every other figure ships a
  `<details>` carrying the same values as text. For this one that would be two
  copies of the same 930 cells.

The two rules from `charts.py` still hold. The fills are `charts.FLAG_FILL`, whose
lightness orders the severity, so the ordering survives colour vision deficiency;
and colour is never the only signal, because every cell also carries the flag as
text -- visible to a screen reader, and to the pointer as a `title`.

The controls are rendered here rather than built by the script, so a reader with
scripting off gets the whole matrix and no buttons that do nothing: the container
ships `hidden` and `assets/matrix.js` is what reveals it.
"""

from __future__ import annotations

import html
import re
import urllib.parse

from . import audit, catalogue, charts
from .audit import Dataset, Run

# One fill per flag, and the one texture. Shared with the SVG figures so the
# legend a reader learned on the check bars is the legend here.
FLAG_FILL = charts.FLAG_FILL
UNKNOWN_INK = charts.UNKNOWN_INK


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def check_slug(check: str) -> str:
    """The id a check's row carries on the checks page.

    Derived from the check's name rather than its index, so a column heading
    still lands on the right row after a check is added in the middle.
    """
    return "check-" + re.sub(r"[^a-z0-9]+", "-", check.lower()).strip("-")


def _cell(dataset: Dataset, check: str, prefix: str) -> str:
    """One flag, as a linked cell.

    Three absences are kept apart, as everywhere else on this site: a scored flag
    is a fill, `Unknown` is a hatch, and a check with nothing to run on is an
    empty cell that is still a cell -- not a link, because there is no result on
    the other end of it.
    """
    flag = dataset.flags[check]
    if flag is None:
        return (
            f'<td class="mx-cell mx-blank" title="'
            f"{_esc(check)}: the check had nothing to run on"
            f'"><span class="sr-only">no result recorded</span></td>'
        )
    tip = (
        f"{dataset.benchmark_id} · {check}: {flag} "
        f"· reference split {dataset.reference_split}"
    )
    href = f"{prefix}datasets/{_esc(catalogue.slug(dataset))}.html#checks"
    return (
        f'<td class="mx-cell mx-{_esc(flag)}">'
        f'<a href="{href}" title="{_esc(tip)}">'
        f'<span class="sr-only">{_esc(flag)}</span></a></td>'
    )


def _row_key(dataset: Dataset) -> tuple:
    """Where a dataset sits inside its collection: worst-first, the paper's way.

    How many of the ten checks flagged at all, then how many of those flagged
    Fail, then the name. It is the sort the manuscript's supplementary matrix
    uses, so a dataset is in the same place in both -- and the name is compared
    as it is written, because that figure sorts in pandas and pandas orders
    capitals before lower case.

    Counting Warning and Fail together first, rather than ranking by the rollup
    flag, is what makes the gradient inside a block visible: a rollup of Fail is
    56 of the 93 datasets, so it sorts more than half the corpus into one tie.
    """
    flags = [dataset.flags[check] for check in audit.CHECKS]
    return (
        -sum(1 for flag in flags if flag in ("Warning", "Fail")),
        -sum(1 for flag in flags if flag == "Fail"),
        dataset.dataset_name,
    )


def _row(dataset: Dataset, prefix: str) -> str:
    cells = "".join(_cell(dataset, check, prefix) for check in audit.DISPLAY_CHECKS)
    href = f"{prefix}datasets/{_esc(catalogue.slug(dataset))}.html"
    return (
        f'<tr data-collection="{_esc(dataset.collection)}" '
        f'data-verdict="{_esc(dataset.overall_verdict or "")}">'
        f'<th scope="row" class="mx-name">'
        f'<a href="{href}" title="{_esc(dataset.benchmark_id)}">'
        f"{_esc(dataset.dataset_name)}</a></th>"
        f"{cells}</tr>"
    )


def _head(prefix: str) -> str:
    """Two heading rows: which family a column belongs to, then the column.

    The band row is `<td>`/`<th scope="colgroup">` rather than a caption line,
    because "probe checks" is a fact about six of the columns and a screen reader
    should get it as one.
    """
    bands = ['<tr class="mx-bands"><td></td>']
    for name, start, stop in charts.KIND_BANDS:
        bands.append(
            f'<th scope="colgroup" colspan="{stop - start}">{_esc(name)}</th>'
        )
    bands.append("</tr>")

    cols = ['<tr class="mx-heads"><th scope="col" class="mx-corner">Dataset</th>']
    for check in audit.DISPLAY_CHECKS:
        line1, line2 = charts.CHECK_SHORT[check]
        cols.append(
            f'<th scope="col" class="mx-head">'
            f'<a href="{prefix}checks.html#{check_slug(check)}" '
            f'title="{_esc(check)}">{_esc(line1)}<br>{_esc(line2)}</a></th>'
        )
    cols.append("</tr>")
    return f"<thead>{''.join(bands)}{''.join(cols)}</thead>"


def _controls(
    order: list[str], sizes: dict[str, int], verdicts: dict[str, int], copy: dict
) -> str:
    """The filter, as buttons that exist before the script runs.

    Two groups and nothing else. The catalogue is where a reader narrows by
    species, task or probe AUROC; a second copy of those facets here would be a
    second thing to keep in step, and this figure only has to answer "which
    collection" and "which flag".
    """
    words = copy["matrix"]

    def chip(facet: str, value: str, label: str, n: int) -> str:
        return (
            f'<button type="button" class="mx-chip" data-facet="{_esc(facet)}" '
            f'data-value="{_esc(value)}" aria-pressed="false">'
            f"{_esc(label)}<span class=\"mx-n\">{n}</span></button>"
        )

    collections = "".join(chip("collection", c, c, sizes[c]) for c in order)
    flags = "".join(
        chip("verdict", flag, copy["flags"][flag], verdicts.get(flag, 0))
        for flag in ("Pass", "Warning", "Fail")
        if verdicts.get(flag, 0)
    )
    return (
        f'<div class="mx-controls" id="matrix-controls" hidden>'
        f'<div class="mx-group" role="group" aria-label="{_esc(words["collection"])}">'
        f'<span class="mx-label">{_esc(words["collection"])}</span>{collections}</div>'
        f'<div class="mx-group" role="group" aria-label="{_esc(words["flag"])}">'
        f'<span class="mx-label">{_esc(words["flag"])}</span>{flags}</div>'
        f'<div class="mx-status">'
        f'<button type="button" class="ghost" id="matrix-clear" hidden>'
        f'{_esc(words["clear"])}</button>'
        f'<span class="count" id="matrix-count" aria-live="polite"></span>'
        f"</div></div>"
    )


def _legend(copy: dict) -> str:
    """The key, as words with a swatch rather than swatches with a caption."""
    items = "".join(
        f'<li><span class="mx-swatch mx-{flag}"></span>{_esc(copy["flags"][flag])}</li>'
        for flag in ("Pass", "Warning", "Fail")
    )
    return (
        f'<ul class="mx-legend">{items}'
        f'<li><span class="mx-swatch mx-blank"></span>'
        f'{_esc(copy["matrix"]["blank"])}</li></ul>'
    )


def flag_matrix(run: Run, copy: dict, prefix: str = "") -> str:
    """Every dataset against every check, on its reference split.

    Grouped by collection and ordered worst-first inside a group, so the shape of
    the audit -- which checks flag broadly, which collections flag together -- is
    there before a single number is read. Both orderings are the manuscript's:
    collections alphabetically, rows by `_row_key`, columns in
    `audit.DISPLAY_CHECKS`. This grid and Supplementary Figure 2 are the same
    figure, and they are laid out the same way on purpose.

    `prefix` is how far the page sits below the site root, the same value
    `base.html` writes onto `<body data-root>`: this figure renders on more than
    one page and a leading slash would break the site under a project prefix.
    """
    datasets = list(run.datasets.values())
    by_collection: dict[str, list[Dataset]] = {}
    verdicts: dict[str, int] = {}
    for dataset in datasets:
        by_collection.setdefault(dataset.collection, []).append(dataset)
        if dataset.overall_verdict:
            verdicts[dataset.overall_verdict] = verdicts.get(dataset.overall_verdict, 0) + 1
    order = sorted(by_collection)
    sizes = {c: len(by_collection[c]) for c in order}

    words = copy["matrix"]
    span = len(audit.DISPLAY_CHECKS) + 1
    bodies = []
    for collection in order:
        members = sorted(by_collection[collection], key=_row_key)
        query = urllib.parse.urlencode({"collection": collection})
        href = _esc(f"{prefix}catalogue.html?{query}")
        rows = "".join(_row(dataset, prefix) for dataset in members)
        bodies.append(
            f'<tbody data-collection="{_esc(collection)}">'
            f'<tr class="mx-groupline"><th scope="colgroup" colspan="{span}">'
            f'<a href="{href}">{_esc(collection)}</a>'
            f'<span class="mx-n">{len(members)}</span></th></tr>'
            f"{rows}</tbody>"
        )

    return (
        f'<figure class="fig mx" id="fig-flag-matrix" data-total="{len(datasets)}">'
        f"{_controls(order, sizes, verdicts, copy)}"
        f'<div class="mx-scroll" tabindex="0" role="region" '
        f'aria-label="{_esc(words["region"])}">'
        f'<table class="mx-grid">'
        f'<caption class="sr-only">{_esc(words["caption"])}</caption>'
        f"{_head(prefix)}{''.join(bodies)}</table></div>"
        f'<p class="mx-empty" id="matrix-empty" hidden>{_esc(words["empty"])}</p>'
        f"<figcaption>{_legend(copy)}"
        f'<p class="fig-caption">{words["note"]}</p></figcaption>'
        f"</figure>"
    )
