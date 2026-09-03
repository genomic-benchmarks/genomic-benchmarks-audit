"""Server-rendered inline SVG for the audit pages.

Every figure on this site is written into the HTML at build time. There is no
chart library, no canvas, no data fetch on load: a page that renders at all
renders its figures, and a reader with scripting off sees the same numbers as a
reader with scripting on. The only thing JavaScript adds is the hover readout,
and each mark carries its own readout text in `data-tip`, so the layer that
shows it is a convenience and never the source.

Two rules run through the whole module and are worth stating once.

Colour never carries a meaning on its own. Every flag mark is drawn in a fill
whose *lightness* orders the severity -- `Pass` lightest, `Fail` darkest -- so
the ordering survives every kind of colour vision deficiency, and every figure
ships with a table twin (`Figure.table`) carrying the same values as text.
`Unknown` is deliberately not a fill: it is a hatch drawn on the surface,
because a check that ran and could not be scored is a different kind of thing
from a check that scored, and giving it a fourth colour on the same ramp would
invite reading it as a mild `Pass`. A check with nothing to run on is drawn as
nothing at all.

Every figure names the split its numbers were measured on. The rollup columns
are the values on the dataset's reference split, not a maximum over splits, and
a figure that does not say so is inviting the reader to assume the wrong one.

`VOCABULARY.md` binds captions and axis labels here exactly as it binds prose.
"""

from __future__ import annotations

import html
import math
import zlib
from dataclasses import dataclass
from typing import Iterable, Sequence

from . import audit
from .audit import Dataset, Run

# ------------------------------------------------------------------ palette ---

# Validated as a set, in light mode on a white surface, over normal vision and
# simulated protanopia, deuteranopia and tritanopia. Worst all-pairs CIELAB
# separation 29.6 (Warning/Fail under tritanopia); lightness strictly ordered
# Pass > Warning > Fail with adjacent steps of 0.09 and 0.21 relative luminance;
# the light end clears 2:1 against white, so a Pass cell is still a cell and not
# a gap in the grid.
FLAG_FILL = {"Pass": "#8dbc9d", "Warning": "#f57f17", "Fail": "#c62828"}

# `Unknown` is a texture, not a fill: hatched surface behind a hairline.
UNKNOWN_INK = "#6d7a77"

# Split series, validated all-pairs on the same terms: worst separation 14.6.
SPLIT_FILL = {
    "train": "#eb6834",
    "val": "#1baf7a",
    "test": "#2a78d6",
    "test_leftout": "#4a3aa7",
}

ACCENT = "#0f766e"  # single-series bars and histograms
GRID = "#e6eae9"  # hairline, solid, behind the marks
AXIS = "#4a5654"
INK = "#1c2321"
MUTED = "#6d7a77"

# ------------------------------------------------------------------- labels ---

# Two lines each, because the full names do not fit a matrix column and a
# rotated axis label is not a readable one. The full name is on the mark's
# hover readout and in the table twin, so nothing is only ever abbreviated.
CHECK_SHORT = {
    "Sequence lengths": ("Sequence", "lengths"),
    "Per sequence GC content": ("GC", "content"),
    "Per sequence nucleotide content": ("Nucleotide", "content"),
    "Per sequence dinucleotide content": ("Dinucleotide", "content"),
    "Per position nucleotide content": ("Per position", "nucleotide"),
    "Per position reversed nucleotide content": ("Per position", "from 3′"),
    "Unique bases": ("Unique", "bases"),
    "Sequence Duplications within Labels": ("Duplicates", "within label"),
    "Duplicate Sequences between Labels": ("Duplicates", "across labels"),
    "Split leakage": ("Split", "leakage"),
}

KIND_BANDS = (
    ("probe checks", 0, len(audit.PROBE_CHECKS)),
    ("integrity checks", len(audit.PROBE_CHECKS), len(audit.CLASS_CHECKS)),
    ("leakage scan", len(audit.CLASS_CHECKS), len(audit.CHECKS)),
)


# ------------------------------------------------------------------ figures ---


@dataclass(frozen=True)
class Figure:
    """One chart, its caption, and the table that says the same thing in words.

    `table` is not a fallback. It is shipped on every figure and reachable from
    the page, because a reader who wants the number rather than the shape should
    not have to hover 930 cells to get it.
    """

    slug: str
    title: str
    caption: str
    svg: str
    table: str
    note: str = ""


def render(figure: Figure) -> str:
    """The figure as it goes into a page: chart, caption, and the table twin."""
    note = f'\n      <p class="fig-note">{figure.note}</p>' if figure.note else ""
    return (
        f'<figure class="fig" id="fig-{figure.slug}">\n'
        f"  {figure.svg}\n"
        f"  <figcaption>\n"
        f'      <p class="fig-caption">{figure.caption}</p>{note}\n'
        f'      <details class="fig-table">\n'
        f"        <summary>Table view</summary>\n"
        f"        {figure.table}\n"
        f"      </details>\n"
        f"  </figcaption>\n"
        f"</figure>"
    )


# ---------------------------------------------------------------- primitives ---


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _f(value: float, places: int = 3) -> str:
    return f"{value:.{places}f}"


def _auroc(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.3f}"


def _pct(value: float | None, places: int = 2) -> str:
    return "not measured" if value is None else f"{value:.{places}f}%"


def _svg(width: int, height: int, title: str, desc: str, body: str, defs: str = "") -> str:
    """A responsive, labelled SVG. Width is fluid; the viewBox holds the layout.

    The title's element id is a CRC of the title rather than `hash()`, which is
    salted per process: two builds of the same run must produce the same bytes,
    or `--check` cannot tell a real change from a restart.
    """
    ident = f"t-{zlib.crc32(title.encode('utf-8')):08x}"
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" '
        f'height="auto" preserveAspectRatio="xMinYMin meet" role="img" '
        f'aria-labelledby="{ident}" xmlns="http://www.w3.org/2000/svg">'
        f'<title id="{ident}">{_esc(title)}</title>'
        f"<desc>{_esc(desc)}</desc>"
        f"{defs}{body}</svg>"
    )


def _hatch_def(name: str = "unknown-hatch") -> str:
    """The `Unknown` texture: 45-degree hairlines on the page surface."""
    return (
        f'<defs><pattern id="{name}" width="6" height="6" '
        f'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<rect width="6" height="6" fill="#ffffff"/>'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{UNKNOWN_INK}" '
        f'stroke-width="1.4" opacity="0.55"/></pattern></defs>'
    )


def _flag_mark(x: float, y: float, w: float, h: float, flag: str | None, tip: str) -> str:
    """One flag cell. A fill for a scored flag, a hatch for `Unknown`, nothing
    for a check that had nothing to run on."""
    if flag is None:
        return ""
    common = f'data-tip="{_esc(tip)}" tabindex="0"'
    if flag == audit.UNKNOWN:
        return (
            f'<rect class="cell" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
            f'height="{h:.1f}" rx="1.5" fill="url(#unknown-hatch)" '
            f'stroke="{UNKNOWN_INK}" stroke-width="1" {common}/>'
        )
    return (
        f'<rect class="cell" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
        f'height="{h:.1f}" rx="1.5" fill="{FLAG_FILL[flag]}" {common}/>'
    )


def _text(x: float, y: float, content: str, cls: str = "lab", anchor: str = "start", extra: str = "") -> str:
    return (
        f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"{extra}>'
        f"{_esc(content)}</text>"
    )


def _gridline(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{GRID}" stroke-width="1" shape-rendering="crispEdges"/>'
    )


def _bar(x: float, y: float, w: float, h: float, fill: str, tip: str, horizontal: bool) -> str:
    """A bar with its data end rounded and its baseline square.

    Drawn as a path rather than a rect because only the end that carries the
    value should be rounded -- a rounded baseline reads as a value that stops
    short of the axis.
    """
    r = min(4.0, w / 2 if horizontal else h / 2, h / 2 if horizontal else w / 2)
    if r <= 0.5 or (horizontal and w < 1) or (not horizontal and h < 1):
        r = 0.0
    if horizontal:
        d = (
            f"M{x:.1f},{y:.1f} H{x + w - r:.1f} "
            f"a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f} "
            f"V{y + h - r:.1f} a{r:.1f},{r:.1f} 0 0 1 -{r:.1f},{r:.1f} "
            f"H{x:.1f} Z"
        )
    else:
        d = (
            f"M{x:.1f},{y + h:.1f} V{y + r:.1f} "
            f"a{r:.1f},{r:.1f} 0 0 1 {r:.1f},-{r:.1f} "
            f"H{x + w - r:.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f} "
            f"V{y + h:.1f} Z"
        )
    return (
        f'<path class="bar" d="{d}" fill="{fill}" data-tip="{_esc(tip)}" tabindex="0"/>'
    )


def _flag_legend(x: float, y: float, flags: Sequence[str]) -> str:
    """The key. The word is always next to the swatch, on every figure that has
    more than one series -- the swatch is the second channel, not the first."""
    parts = []
    cursor = x
    for flag in flags:
        if flag == audit.UNKNOWN:
            swatch = (
                f'<rect x="{cursor:.1f}" y="{y - 8:.1f}" width="11" height="11" rx="1.5" '
                f'fill="url(#unknown-hatch)" stroke="{UNKNOWN_INK}" stroke-width="1"/>'
            )
        else:
            swatch = (
                f'<rect x="{cursor:.1f}" y="{y - 8:.1f}" width="11" height="11" '
                f'rx="1.5" fill="{FLAG_FILL[flag]}"/>'
            )
        parts.append(swatch + _text(cursor + 16, y + 1, flag, "leg"))
        cursor += 22 + len(flag) * 6.2
    return "".join(parts)


def _split_legend(x: float, y: float, splits: Sequence[str]) -> str:
    parts = []
    cursor = x
    for split in splits:
        parts.append(
            f'<rect x="{cursor:.1f}" y="{y - 8:.1f}" width="11" height="11" rx="1.5" '
            f'fill="{SPLIT_FILL.get(split, ACCENT)}"/>'
            + _text(cursor + 16, y + 1, split, "leg")
        )
        cursor += 22 + len(split) * 6.2
    return "".join(parts)


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]], caption: str = "") -> str:
    head = "".join(f"<th scope=\"col\">{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>"
        + f'<th scope="row">{_esc(row[0])}</th>'
        + "".join(f"<td>{_esc(cell)}</td>" for cell in row[1:])
        + "</tr>"
        for row in rows
    )
    cap = f"<caption>{_esc(caption)}</caption>" if caption else ""
    return f'<table class="data">{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _wrap(text: str, width: int, lines: int = 2) -> list[str]:
    """Break on words, never mid-word.

    A threshold clipped at a fixed character count reads as a different
    threshold -- `< 2% of held-o` is not a criterion anybody can check.
    """
    out: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width or not current:
            current = candidate
        else:
            out.append(current)
            current = word
            if len(out) == lines - 1:
                break
    remainder = " ".join([current] + text.split()[sum(len(l.split()) for l in out) + len(current.split()):])
    out.append(remainder.strip())
    if len(out) > lines:
        out = out[: lines - 1] + [" ".join(out[lines - 1 :])]
    return out


def _severity_key(dataset: Dataset) -> tuple:
    rank = {"Fail": 0, "Warning": 1, "Pass": 2, audit.UNKNOWN: 3, None: 4}
    return (
        rank.get(dataset.overall_verdict, 4),
        -(dataset.max_probe_auroc or 0.0),
        dataset.dataset_name.lower(),
    )


# ------------------------------------------------------- corpus-wide figures ---


def flag_matrix(run: Run) -> Figure:
    """Every dataset against every check, on its reference split.

    The signature figure: 93 rows, 10 columns, one mark each. Grouped by
    collection and sorted worst-first inside each group, so the shape of the
    audit -- which checks flag broadly, which collections flag together -- is
    visible before a single number is read.
    """
    datasets = list(run.datasets.values())
    by_collection: dict[str, list[Dataset]] = {}
    for dataset in datasets:
        by_collection.setdefault(dataset.collection, []).append(dataset)
    order = sorted(by_collection)

    label_w, col_w, cell_w = 262, 66, 62
    row_h, row_gap = 10, 2
    pitch = row_h + row_gap
    band_h, header_h, group_h = 14, 26, 22
    top = 8 + band_h + header_h
    left = label_w

    height = top + sum(group_h + len(by_collection[c]) * pitch for c in order) + 34
    width = left + col_w * len(audit.CHECKS) + 8

    body = []

    # Which family each column belongs to, stated once above the headers.
    for name, start, stop in KIND_BANDS:
        x0 = left + start * col_w
        x1 = left + stop * col_w - (col_w - cell_w)
        body.append(
            f'<line x1="{x0:.1f}" y1="14" x2="{x1:.1f}" y2="14" '
            f'stroke="{MUTED}" stroke-width="1"/>'
        )
        body.append(_text((x0 + x1) / 2, 10, name, "band", "middle"))

    for index, check in enumerate(audit.CHECKS):
        x = left + index * col_w + cell_w / 2
        line1, line2 = CHECK_SHORT[check]
        body.append(_text(x, 8 + band_h + 11, line1, "colhead", "middle"))
        body.append(_text(x, 8 + band_h + 21, line2, "colhead", "middle"))

    rows_out: list[list[object]] = []
    y = top
    for collection in order:
        members = sorted(by_collection[collection], key=_severity_key)
        body.append(_gridline(8, y + 4, width - 8, y + 4))
        body.append(_text(8, y + 17, f"{collection}  ({len(members)})", "group"))
        y += group_h
        for dataset in members:
            body.append(_text(label_w - 10, y + row_h - 1.5, dataset.dataset_name, "rowlab", "end"))
            for index, check in enumerate(audit.CHECKS):
                flag = dataset.flags[check]
                tip = (
                    f"{dataset.benchmark_id}  •  {check}: "
                    f"{flag or 'no result recorded'}"
                    f"  •  reference split {dataset.reference_split}"
                )
                body.append(
                    _flag_mark(left + index * col_w, y, cell_w, row_h, flag, tip)
                )
            rows_out.append(
                [dataset.benchmark_id] + [dataset.flags[c] or "" for c in audit.CHECKS]
            )
            y += pitch

    body.append(_flag_legend(8, height - 12, ["Pass", "Warning", "Fail"]))
    body.append(
        _text(width - 8, height - 11, "blank: the check had nothing to run on", "leg", "end")
    )

    svg = _svg(
        width,
        height,
        "Flag matrix: every dataset against every check",
        "A grid of 93 dataset rows by 10 check columns. Each cell is filled "
        "green for Pass, orange for Warning, red for Fail, and left blank where "
        "the check had nothing to run on. Rows are grouped by collection.",
        "".join(body),
        _hatch_def(),
    )
    return Figure(
        slug="flag-matrix",
        title="Flag matrix",
        caption=(
            "Every one of the 93 included datasets against all ten checks, on "
            "that dataset’s reference split. Rows are grouped by collection "
            "and ordered worst-first within a group."
        ),
        note=(
            "One dataset (miRBench:AGO2_eCLIP_Klimentova2022) ships only a test "
            "split, so the leakage scan had no split pair to compare and its "
            "cell is blank — which is not the same statement as "
            "<code>Unknown</code>."
        ),
        svg=svg,
        table=_table(
            ["Dataset"] + [CHECK_SHORT[c][0] + " " + CHECK_SHORT[c][1] for c in audit.CHECKS],
            rows_out,
            "Flag per dataset per check, on the reference split.",
        ),
    )


def check_bars(run: Run) -> Figure:
    """How broadly each check flagged, as a share of the corpus.

    Stacked, ordered by the share flagged, so the checks that separate the
    corpus sit at the top and the ones that rarely fire sit at the bottom.
    """
    datasets = list(run.datasets.values())
    counts = []
    for check in audit.CHECKS:
        flags = [d.flags[check] for d in datasets]
        counts.append(
            {
                "check": check,
                "Pass": sum(1 for f in flags if f == "Pass"),
                "Warning": sum(1 for f in flags if f == "Warning"),
                "Fail": sum(1 for f in flags if f == "Fail"),
                audit.UNKNOWN: sum(1 for f in flags if f == audit.UNKNOWN),
                "blank": sum(1 for f in flags if f is None),
            }
        )
    counts.sort(key=lambda c: (c["Fail"] + c["Warning"]), reverse=True)

    label_w, plot_w = 240, 560
    row_h, pitch = 20, 30
    top, bottom = 34, 42
    width = label_w + plot_w + 60
    height = top + len(counts) * pitch + bottom
    total = len(datasets)

    body = []
    for tick in range(0, 101, 25):
        x = label_w + plot_w * tick / 100
        body.append(_gridline(x, top - 8, x, top + len(counts) * pitch - 10))
        body.append(_text(x, top - 14, f"{tick}%", "tick", "middle"))
    body.append(_text(label_w + plot_w / 2, 12, "share of the 93 datasets", "axis", "middle"))

    rows_out = []
    for index, entry in enumerate(counts):
        y = top + index * pitch
        check = entry["check"]
        body.append(_text(label_w - 12, y + row_h - 5, check, "rowlab", "end"))
        cursor = float(label_w)
        segments = [
            ("Pass", entry["Pass"]),
            ("Warning", entry["Warning"]),
            ("Fail", entry["Fail"]),
            (audit.UNKNOWN, entry[audit.UNKNOWN]),
        ]
        for flag, n in segments:
            if not n:
                continue
            w = plot_w * n / total
            tip = f"{check}: {n} of {total} datasets flagged {flag}"
            if flag == audit.UNKNOWN:
                body.append(
                    f'<rect class="cell" x="{cursor:.1f}" y="{y:.1f}" width="{max(w - 2, 1):.1f}" '
                    f'height="{row_h}" rx="2" fill="url(#unknown-hatch)" '
                    f'stroke="{UNKNOWN_INK}" stroke-width="1" data-tip="{_esc(tip)}" tabindex="0"/>'
                )
            else:
                body.append(
                    f'<rect class="cell" x="{cursor:.1f}" y="{y:.1f}" width="{max(w - 2, 1):.1f}" '
                    f'height="{row_h}" rx="2" fill="{FLAG_FILL[flag]}" '
                    f'data-tip="{_esc(tip)}" tabindex="0"/>'
                )
            cursor += w
        flagged = entry["Warning"] + entry["Fail"]
        body.append(
            _text(label_w + plot_w + 10, y + row_h - 5, f"{flagged}/{total}", "val")
        )
        rows_out.append(
            [
                check,
                entry["Pass"],
                entry["Warning"],
                entry["Fail"],
                entry["blank"] or "",
                f"{100 * flagged / total:.1f}%",
            ]
        )

    body.append(_flag_legend(label_w, height - 14, ["Pass", "Warning", "Fail"]))

    svg = _svg(
        width,
        height,
        "How broadly each check flagged",
        "Ten horizontal stacked bars, one per check, showing the share of the "
        "93 datasets flagged Pass, Warning or Fail on that check.",
        "".join(body),
        _hatch_def(),
    )
    return Figure(
        slug="check-bars",
        title="Flags by check",
        caption=(
            "The share of the 93 datasets carrying each flag on each check, "
            "measured on each dataset’s reference split. The trailing "
            "figure counts the datasets flagged <code>Warning</code> or "
            "<code>Fail</code>."
        ),
        svg=svg,
        table=_table(
            ["Check", "Pass", "Warning", "Fail", "No result", "Flagged"],
            rows_out,
            "Datasets per flag per check.",
        ),
    )


def _histogram(
    values: Sequence[tuple[str, float]],
    *,
    slug: str,
    title: str,
    caption: str,
    axis_label: str,
    lo: float,
    hi: float,
    bins: int,
    unit: str,
    places: int,
    threshold: tuple[float, str] | None = None,
    note: str = "",
) -> Figure:
    """A distribution, binned, with each bar carrying the datasets it holds."""
    edges = [lo + (hi - lo) * i / bins for i in range(bins + 1)]
    buckets: list[list[str]] = [[] for _ in range(bins)]
    for name, value in values:
        index = min(bins - 1, max(0, int((value - lo) / (hi - lo) * bins)))
        buckets[index].append(name)
    peak = max(len(b) for b in buckets) or 1

    left, right, top, bottom = 52, 16, 30, 62
    plot_w, plot_h = 650, 250
    width, height = left + plot_w + right, top + plot_h + bottom
    slot = plot_w / bins
    bar_w = min(24.0, slot - 3)

    body = []
    step = 5 if peak <= 25 else 10 if peak <= 60 else 20
    tick = 0
    while tick <= peak:
        y = top + plot_h - plot_h * tick / peak
        body.append(_gridline(left, y, left + plot_w, y))
        body.append(_text(left - 8, y + 3.5, str(tick), "tick", "end"))
        tick += step
    body.append(_text(6, top - 14, "datasets", "axis"))

    for index, bucket in enumerate(buckets):
        n = len(bucket)
        if not n:
            continue
        h = plot_h * n / peak
        x = left + index * slot + (slot - bar_w) / 2
        y = top + plot_h - h
        listed = ", ".join(sorted(bucket)[:6])
        more = f" and {n - 6} more" if n > 6 else ""
        tip = (
            f"{_f(edges[index], places)}–{_f(edges[index + 1], places)}{unit}: "
            f"{n} dataset{'s' if n != 1 else ''} — {listed}{more}"
        )
        body.append(_bar(x, y, bar_w, h, ACCENT, tip, horizontal=False))

    for i in range(0, bins + 1, max(1, bins // 5)):
        x = left + i * slot
        body.append(_text(x, top + plot_h + 18, _f(edges[i], places), "tick", "middle"))
    body.append(_text(left + plot_w / 2, top + plot_h + 38, axis_label, "axis", "middle"))

    if threshold is not None:
        mark, mark_label = threshold
        x = left + plot_w * (mark - lo) / (hi - lo)
        body.append(
            f'<line x1="{x:.1f}" y1="{top - 6:.1f}" x2="{x:.1f}" y2="{top + plot_h:.1f}" '
            f'stroke="{INK}" stroke-width="2" stroke-dasharray="5 4"/>'
        )
        body.append(_text(x + 6, top - 10, mark_label, "leg"))

    rows_out = [
        [
            f"{_f(edges[i], places)}–{_f(edges[i + 1], places)}{unit}",
            len(buckets[i]),
            ", ".join(sorted(buckets[i])) or "—",
        ]
        for i in range(bins)
        if buckets[i]
    ]
    svg = _svg(
        width,
        height,
        title,
        f"A histogram of {axis_label} over {len(values)} datasets, in {bins} bins.",
        "".join(body),
    )
    return Figure(
        slug=slug,
        title=title,
        caption=caption,
        note=note,
        svg=svg,
        table=_table(["Bin", "Datasets", "Which"], rows_out, f"{title}, binned."),
    )


def auroc_histogram(run: Run) -> Figure:
    """How separable the corpus is by a single sequence feature.

    Each value is the strongest single-feature probe on that dataset's reference
    split -- a lower bound on how much of the label a model can recover without
    learning anything the benchmark is asking about.
    """
    values = [
        (d.benchmark_id, d.max_probe_auroc)
        for d in run.datasets.values()
        if d.max_probe_auroc is not None
    ]
    lo = min(0.5, min(v for _, v in values))
    return _histogram(
        values,
        slug="probe-auroc",
        title="Strongest single-feature probe",
        caption=(
            f"The strongest single-feature probe AUROC on each dataset’s "
            f"reference split, over the {len(values)} datasets where a probe "
            f"was measured. Every value is a lower bound: it is what one simple "
            f"feature recovered, not the most that could be."
        ),
        note=(
            "The dashed line marks 0.7, the threshold the Core Set uses; it is a "
            "selection cut, not a claim about the datasets either side of it."
        ),
        axis_label="strongest-probe AUROC on the reference split",
        lo=math.floor(lo * 20) / 20,
        hi=1.0,
        bins=25,
        unit="",
        places=2,
        threshold=(0.7, "0.70"),
    )


LEAKAGE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("none detected", 0.0, 0.0),
    ("up to 0.5%", 0.0, 0.5),
    ("0.5% to 1%", 0.5, 1.0),
    ("1% to 2%", 1.0, 2.0),
    ("2% to 5%", 2.0, 5.0),
    ("5% to 10%", 5.0, 10.0),
    ("10% to 25%", 10.0, 25.0),
    ("25% to 50%", 25.0, 50.0),
    ("over 50%", 50.0, 100.0),
)


def leakage_bands(run: Run) -> Figure:
    """How much of the held-out data was already visible in training.

    Deliberately not a histogram. Three quarters of the corpus sits under 5%
    and a handful sits near 100%, so equal-width bins put almost every dataset
    in one bar and spend the rest of the axis on empty space -- a picture of the
    binning, not of the corpus. These bands are uneven and named, and the axis
    counts datasets rather than implying a density, which is the honest way to
    draw a distribution whose interesting structure is all at one end.
    """
    values = [
        (d.benchmark_id, d.max_leaked_test_pct)
        for d in run.datasets.values()
        if d.max_leaked_test_pct is not None
    ]
    buckets: list[list[str]] = [[] for _ in LEAKAGE_BANDS]
    for name, value in values:
        for index, (_, lo, hi) in enumerate(LEAKAGE_BANDS):
            if (value == 0.0 and lo == hi == 0.0) or (lo < value <= hi):
                buckets[index].append(name)
                break
    peak = max(len(b) for b in buckets) or 1

    label_w, plot_w = 150, 520
    row_h, pitch = 22, 32
    top, bottom = 38, 52
    width = label_w + plot_w + 80
    height = top + len(LEAKAGE_BANDS) * pitch + bottom

    body = [_text(label_w, 14, "datasets", "axis")]
    step = 5 if peak <= 25 else 10 if peak <= 60 else 20
    tick = 0
    while tick <= peak:
        x = label_w + plot_w * tick / peak
        body.append(_gridline(x, top - 10, x, top + len(LEAKAGE_BANDS) * pitch - 10))
        body.append(_text(x, top - 16, str(tick), "tick", "middle"))
        tick += step

    rows_out = []
    for index, ((label, lo, hi), bucket) in enumerate(zip(LEAKAGE_BANDS, buckets)):
        y = top + index * pitch
        body.append(_text(label_w - 12, y + row_h - 6, label, "rowlab", "end"))
        n = len(bucket)
        if n:
            listed = ", ".join(sorted(bucket)[:6])
            more = f" and {n - 6} more" if n > 6 else ""
            body.append(
                _bar(
                    label_w,
                    y,
                    max(plot_w * n / peak, 2.0),
                    row_h,
                    ACCENT,
                    f"{label}: {n} dataset{'s' if n != 1 else ''} — {listed}{more}",
                    horizontal=True,
                )
            )
        body.append(_text(label_w + plot_w + 10, y + row_h - 6, str(n), "val"))
        rows_out.append([label, n, ", ".join(sorted(bucket)) or "—"])

    # The Core Set cut sits between the fourth and fifth band, and is drawn
    # there rather than as a value on the axis, because it is a threshold on
    # the measurement and not on the count.
    cut = top + 4 * pitch - 5
    body.append(
        f'<line x1="{label_w:.1f}" y1="{cut:.1f}" x2="{label_w + plot_w:.1f}" '
        f'y2="{cut:.1f}" stroke="{INK}" stroke-width="2" stroke-dasharray="5 4"/>'
    )
    body.append(
        _text(label_w + plot_w, cut - 6, "Core Set threshold: 2%", "leg", "end")
    )

    svg = _svg(
        width,
        height,
        "Held-out sequences also present in training",
        f"Nine horizontal bars, one per named band, counting how many of "
        f"{len(values)} datasets fall in each band of held-out overlap.",
        "".join(body),
    )
    return Figure(
        slug="leakage",
        title="Held-out sequences also present in training",
        caption=(
            f"For each of the {len(values)} datasets the leakage scan could "
            f"compare, the largest share of a held-out split whose sequences "
            f"also appear in the training split. Measured on exact sequence "
            f"identity."
        ),
        note=(
            "The bands are uneven, so the bar lengths count datasets and are "
            "not a density. A dataset in “none detected” had no exact sequence "
            "in common between the splits the scan compared."
        ),
        svg=svg,
        table=_table(
            ["Overlap", "Datasets", "Which"],
            rows_out,
            "Datasets per band of held-out overlap.",
        ),
    )


def core_set_funnel(run: Run) -> Figure:
    """The five gates, and what each one removed.

    Drawn as a funnel rather than a table of counts because the point is the
    shape: the corpus does not narrow evenly, and two gates account for most of
    the loss.
    """
    gates = sorted(run.gates, key=lambda g: g.step)
    if not gates:
        raise ValueError("core_set_criteria.csv carried no gates")
    start = gates[0].n_in

    label_w, plot_w = 268, 520
    row_h, pitch = 24, 50
    top, bottom = 44, 40
    width = label_w + plot_w + 130
    height = top + (len(gates) + 1) * pitch + bottom

    body = [_text(label_w, 16, "datasets remaining", "axis")]
    for tick in (0, 25, 50, 75, 93):
        x = label_w + plot_w * tick / start
        body.append(_gridline(x, top - 10, x, top + len(gates) * pitch + row_h))
        body.append(_text(x, top - 16, str(tick), "tick", "middle"))

    body.append(
        _bar(label_w, top, plot_w, row_h, MUTED, f"{start} datasets entered the funnel", True)
    )
    body.append(_text(label_w - 12, top + row_h - 7, "included in the audit", "rowlab", "end"))
    body.append(_text(label_w + plot_w + 12, top + row_h - 7, str(start), "val"))

    rows_out = []
    for index, gate in enumerate(gates):
        y = top + (index + 1) * pitch
        kept = plot_w * gate.n_out / start
        removed = plot_w * gate.n_removed / start
        body.append(
            _bar(
                label_w,
                y,
                kept,
                row_h,
                ACCENT,
                f"gate {gate.step} — {gate.criterion}: {gate.n_out} of "
                f"{gate.n_in} remained ({gate.requirement})",
                True,
            )
        )
        if gate.n_removed:
            body.append(
                f'<rect class="cell" x="{label_w + kept + 2:.1f}" y="{y:.1f}" '
                f'width="{max(removed - 2, 1):.1f}" height="{row_h}" rx="2" '
                f'fill="url(#unknown-hatch)" stroke="{UNKNOWN_INK}" stroke-width="1" '
                f'data-tip="{_esc(f"gate {gate.step} removed {gate.n_removed}: {gate.threshold}")}" '
                f'tabindex="0"/>'
            )
        body.append(_text(label_w - 12, y + row_h - 20, f"{gate.step}. {gate.criterion}", "rowlab", "end"))
        for offset, line in enumerate(_wrap(gate.threshold, 46)):
            body.append(_text(label_w - 12, y + row_h - 8 + offset * 11, line, "sub", "end"))
        body.append(_text(label_w + plot_w + 12, y + row_h - 7, f"{gate.n_out}  (−{gate.n_removed})", "val"))
        rows_out.append(
            [f"{gate.step}. {gate.criterion}", gate.requirement, gate.threshold, gate.n_in, gate.n_removed, gate.n_out]
        )

    body.append(
        f'<rect x="{label_w:.1f}" y="{height - 22:.1f}" width="11" height="11" rx="1.5" '
        f'fill="url(#unknown-hatch)" stroke="{UNKNOWN_INK}" stroke-width="1"/>'
        + _text(label_w + 16, height - 13, "removed by this gate", "leg")
    )

    svg = _svg(
        width,
        height,
        "Core Set selection",
        f"A funnel of {len(gates)} gates narrowing {start} datasets to "
        f"{gates[-1].n_out}, with the count removed at each gate hatched.",
        "".join(body),
        _hatch_def(),
    )
    return Figure(
        slug="core-set-funnel",
        title="Core Set selection",
        caption=(
            f"The {len(gates)} gates that narrow the {start} included datasets "
            f"to the {gates[-1].n_out} of the Core Set. Each gate is applied to "
            f"what the one above it left."
        ),
        note=(
            "The gates are selection criteria, not a ranking. A dataset removed "
            "at a gate is one this audit measured a flag on, and nothing more "
            "than that."
        ),
        svg=svg,
        table=_table(
            ["Gate", "Requirement", "Threshold", "In", "Removed", "Out"],
            rows_out,
            "The Core Set gates in order.",
        ),
    )


def collection_bars(run: Run) -> Figure:
    """The rollup flag per collection, so a reader can see where flags cluster."""
    datasets = list(run.datasets.values())
    groups: dict[str, list[Dataset]] = {}
    for dataset in datasets:
        groups.setdefault(dataset.collection, []).append(dataset)

    entries = []
    for collection, members in groups.items():
        counts = {flag: 0 for flag in audit.FLAGS}
        for member in members:
            if member.overall_verdict in counts:
                counts[member.overall_verdict] += 1
        entries.append((collection, len(members), counts))
    entries.sort(key=lambda e: (-e[2]["Fail"] / e[1], e[0]))

    label_w, plot_w = 220, 520
    row_h, pitch = 22, 32
    top, bottom = 34, 42
    width = label_w + plot_w + 96
    height = top + len(entries) * pitch + bottom

    body = []
    for tick in range(0, 101, 25):
        x = label_w + plot_w * tick / 100
        body.append(_gridline(x, top - 8, x, top + len(entries) * pitch - 10))
        body.append(_text(x, top - 14, f"{tick}%", "tick", "middle"))
    body.append(_text(label_w + plot_w / 2, 12, "share of the collection", "axis", "middle"))

    rows_out = []
    for index, (collection, total, counts) in enumerate(entries):
        y = top + index * pitch
        body.append(_text(label_w - 12, y + row_h - 6, collection, "rowlab", "end"))
        cursor = float(label_w)
        for flag in ("Pass", "Warning", "Fail"):
            n = counts[flag]
            if not n:
                continue
            w = plot_w * n / total
            body.append(
                f'<rect class="cell" x="{cursor:.1f}" y="{y:.1f}" width="{max(w - 2, 1):.1f}" '
                f'height="{row_h}" rx="2" fill="{FLAG_FILL[flag]}" '
                f'data-tip="{_esc(f"{collection}: {n} of {total} datasets roll up to {flag}")}" '
                f'tabindex="0"/>'
            )
            cursor += w
        body.append(_text(label_w + plot_w + 10, y + row_h - 6, f"n={total}", "val"))
        rows_out.append([collection, total, counts["Pass"], counts["Warning"], counts["Fail"]])

    body.append(_flag_legend(label_w, height - 14, ["Pass", "Warning", "Fail"]))
    svg = _svg(
        width,
        height,
        "Rollup flag by collection",
        "One stacked bar per collection showing the share of its datasets whose "
        "checks roll up to Pass, Warning or Fail.",
        "".join(body),
        _hatch_def(),
    )
    return Figure(
        slug="collection-bars",
        title="Rollup flag by collection",
        caption=(
            "For each collection, the share of its datasets whose ten checks "
            "roll up to each flag. The rollup is the worst flag over the checks "
            "that scored."
        ),
        note=(
            "Collections differ in size, in task, and in how their splits were "
            "drawn; a taller red bar is a measurement on those datasets, not a "
            "comparison between collections."
        ),
        svg=svg,
        table=_table(
            ["Collection", "Datasets", "Pass", "Warning", "Fail"],
            rows_out,
            "Rollup flag per collection.",
        ),
    )


# ------------------------------------------------------- per-dataset figures ---


def dataset_check_grid(dataset: Dataset) -> Figure:
    """Every class-distribution check on this dataset, on every split it has.

    The rollup reports the reference split. This is the figure that shows what
    the other splits did, including the checks that ran and could not be scored.
    """
    splits = [s for s in audit.SPLIT_ORDER if s in dataset.split_names]
    splits += [s for s in dataset.split_names if s not in splits]
    scored: dict[tuple[str, str], list] = {}
    for measurement in dataset.measurements:
        scored.setdefault((measurement.split, measurement.check), []).append(measurement)

    label_w, col_w, cell_w = 130, 66, 62
    row_h, pitch = 22, 28
    band_h, header_h = 14, 26
    top = 8 + band_h + header_h
    width = label_w + col_w * len(audit.CLASS_CHECKS) + 8
    height = top + len(splits) * pitch + 40

    body = []
    for name, start, stop in KIND_BANDS[:2]:
        x0 = label_w + start * col_w
        x1 = label_w + stop * col_w - (col_w - cell_w)
        body.append(f'<line x1="{x0:.1f}" y1="14" x2="{x1:.1f}" y2="14" stroke="{MUTED}" stroke-width="1"/>')
        body.append(_text((x0 + x1) / 2, 10, name, "band", "middle"))
    for index, check in enumerate(audit.CLASS_CHECKS):
        x = label_w + index * col_w + cell_w / 2
        line1, line2 = CHECK_SHORT[check]
        body.append(_text(x, 8 + band_h + 11, line1, "colhead", "middle"))
        body.append(_text(x, 8 + band_h + 21, line2, "colhead", "middle"))

    rows_out = []
    for row, split in enumerate(splits):
        y = top + row * pitch
        mark = "  ◂ reference" if split == dataset.reference_split else ""
        body.append(_text(label_w - 10, y + row_h - 6, f"{split}{mark}", "rowlab", "end"))
        cells = []
        for index, check in enumerate(audit.CLASS_CHECKS):
            found = scored.get((split, check), [])
            flag = audit.worst_flag([m.flag for m in found])
            if flag is None and any(m.flag == audit.UNKNOWN for m in found):
                flag = audit.UNKNOWN
            auroc = [m.au_roc for m in found if m.au_roc is not None]
            detail = f", AUROC {max(auroc):.3f}" if auroc else ""
            over = f" over {len(found)} sequence columns" if len(found) > 1 else ""
            tip = f"{split} • {check}: {flag or 'no result recorded'}{detail}{over}"
            body.append(_flag_mark(label_w + index * col_w, y, cell_w, row_h, flag, tip))
            cells.append((flag or "", f"{max(auroc):.3f}" if auroc else ""))
        rows_out.append([split] + [f"{f} {a}".strip() or "—" for f, a in cells])

    legend = ["Pass", "Warning", "Fail"]
    if any(m.flag == audit.UNKNOWN for m in dataset.measurements):
        legend.append(audit.UNKNOWN)
    body.append(_flag_legend(label_w, height - 12, legend))

    svg = _svg(
        width,
        height,
        f"Checks by split — {dataset.benchmark_id}",
        f"A grid of {len(splits)} split rows by {len(audit.CLASS_CHECKS)} check "
        f"columns for {dataset.benchmark_id}.",
        "".join(body),
        _hatch_def(),
    )
    return Figure(
        slug="dataset-checks",
        title="Checks by split",
        caption=(
            f"The nine class-distribution checks on each of "
            f"{dataset.benchmark_id}’s {len(splits)} splits. The rollup "
            f"reports the <strong>{dataset.reference_split}</strong> row."
        ),
        note=(
            "A hatched cell is <code>Unknown</code>: the check ran and could not "
            "be scored. It is not a mild <code>Pass</code>, and it is not "
            "counted in the rollup."
            if any(m.flag == audit.UNKNOWN for m in dataset.measurements)
            else ""
        ),
        svg=svg,
        table=_table(
            ["Split"] + [CHECK_SHORT[c][0] + " " + CHECK_SHORT[c][1] for c in audit.CLASS_CHECKS],
            rows_out,
            "Flag and, where measured, the strongest probe AUROC per check per split.",
        ),
    )


def dataset_probe_bars(dataset: Dataset) -> Figure:
    """Probe AUROC per check, grouped by split.

    The bars are lower bounds, and the axis starts at 0.5 because 0.5 is what a
    probe that recovered nothing would read.
    """
    splits = [s for s in audit.SPLIT_ORDER if s in dataset.split_names]
    splits += [s for s in dataset.split_names if s not in splits]
    best: dict[tuple[str, str], float] = {}
    for measurement in dataset.measurements:
        if measurement.check in audit.PROBE_CHECKS and measurement.au_roc is not None:
            key = (measurement.check, measurement.split)
            best[key] = max(best.get(key, 0.0), measurement.au_roc)
    if not best:
        return Figure(
            slug="dataset-probes",
            title="Probe AUROC by check",
            caption="No probe recorded an AUROC on this dataset.",
            svg="",
            table="",
        )

    lo = min(0.5, min(best.values()))
    hi = 1.0
    left, right, top, bottom = 52, 16, 34, 92
    plot_w, plot_h = 700, 200
    width, height = left + plot_w + right, top + plot_h + bottom
    group = plot_w / len(audit.PROBE_CHECKS)
    bar_w = min(24.0, (group - 12) / max(len(splits), 1) - 2)

    body = []
    tick = lo
    while tick <= hi + 1e-9:
        y = top + plot_h - plot_h * (tick - lo) / (hi - lo)
        body.append(_gridline(left, y, left + plot_w, y))
        body.append(_text(left - 8, y + 3.5, f"{tick:.2f}", "tick", "end"))
        tick += 0.1
    body.append(_text(6, top - 16, "AUROC", "axis"))

    rows_out = []
    for index, check in enumerate(audit.PROBE_CHECKS):
        base = left + index * group
        span = len(splits) * (bar_w + 2) - 2
        start = base + (group - span) / 2
        row = [check]
        for position, split in enumerate(splits):
            value = best.get((check, split))
            if value is None:
                row.append("—")
                continue
            h = max(plot_h * (value - lo) / (hi - lo), 1.0)
            x = start + position * (bar_w + 2)
            y = top + plot_h - h
            body.append(
                _bar(
                    x,
                    y,
                    bar_w,
                    h,
                    SPLIT_FILL.get(split, ACCENT),
                    f"{check} on {split}: AUROC {value:.3f}",
                    horizontal=False,
                )
            )
            row.append(f"{value:.3f}")
        rows_out.append(row)
        line1, line2 = CHECK_SHORT[check]
        body.append(_text(base + group / 2, top + plot_h + 18, line1, "colhead", "middle"))
        body.append(_text(base + group / 2, top + plot_h + 29, line2, "colhead", "middle"))

    body.append(
        f'<line x1="{left}" y1="{top + plot_h:.1f}" x2="{left + plot_w}" '
        f'y2="{top + plot_h:.1f}" stroke="{AXIS}" stroke-width="1"/>'
    )
    body.append(_split_legend(left, height - 30, splits))
    body.append(
        _text(left, height - 10, "every value is a lower bound on separability", "leg")
    )

    svg = _svg(
        width,
        height,
        f"Probe AUROC by check — {dataset.benchmark_id}",
        f"Grouped bars: six probe checks, each with one bar per split, showing "
        f"the AUROC a single-feature probe reached on {dataset.benchmark_id}.",
        "".join(body),
    )
    return Figure(
        slug="dataset-probes",
        title="Probe AUROC by check",
        caption=(
            "What each single-feature probe recovered, on each split. Where a "
            "dataset has several sequence columns the strongest is shown; the "
            "table view lists every value."
        ),
        note=(
            "The axis starts at 0.50 because that is what a probe recovering "
            "nothing would read. A value is a lower bound: it is what one "
            "feature reached, not the most that could be reached."
        ),
        svg=svg,
        table=_table(["Check"] + splits, rows_out, "Probe AUROC per check per split."),
    )


def dataset_leakage_bars(dataset: Dataset) -> Figure:
    """Exact-sequence overlap between each pair of splits, both directions.

    Two bars per pair, because "1% of train is in test" and "40% of test is in
    train" are different statements about the same overlap and only the second
    one bears on whether a held-out score means anything.
    """
    comparisons = list(dataset.leakage)
    if not comparisons:
        return Figure(
            slug="dataset-leakage",
            title="Split overlap",
            caption=(
                "This dataset ships a single split, so the leakage scan had no "
                "pair to compare."
            ),
            svg="",
            table="",
        )

    bars: list[tuple[str, str, float, str]] = []
    for comparison in comparisons:
        if comparison.leaked_targets_pct is not None:
            bars.append(
                (
                    f"{comparison.target_split} also in {comparison.query_split}",
                    comparison.target_split,
                    comparison.leaked_targets_pct,
                    comparison.flag or "",
                )
            )
        if comparison.leaked_queries_pct is not None:
            bars.append(
                (
                    f"{comparison.query_split} also in {comparison.target_split}",
                    comparison.query_split,
                    comparison.leaked_queries_pct,
                    comparison.flag or "",
                )
            )

    peak = max((value for _, _, value, _ in bars), default=0.0)
    hi = next((step for step in (0.5, 1, 2, 5, 10, 25, 50, 100) if peak <= step), 100.0)

    label_w, plot_w = 250, 460
    row_h, pitch = 20, 28
    top, bottom = 36, 56
    width = label_w + plot_w + 90
    height = top + len(bars) * pitch + bottom

    body = [_text(label_w, 14, "share of that split (%)", "axis")]
    steps = 5
    for i in range(steps + 1):
        value = hi * i / steps
        x = label_w + plot_w * i / steps
        body.append(_gridline(x, top - 8, x, top + len(bars) * pitch - 8))
        body.append(_text(x, top - 14, f"{value:g}", "tick", "middle"))

    for index, (label, split, value, flag) in enumerate(bars):
        y = top + index * pitch
        body.append(_text(label_w - 12, y + row_h - 5, label, "rowlab", "end"))
        tip = f"{value:.2f}% of {split} also appears in the other split" + (
            f" — the scan flagged {flag}" if flag else ""
        )
        if value > 0:
            # A bar drawn for an exact zero would read as a small value; the
            # trailing figure says 0.00% and that is the whole statement.
            w = max(plot_w * min(value, hi) / hi, 2.0)
            body.append(
                _bar(label_w, y, w, row_h, SPLIT_FILL.get(split, ACCENT), tip, horizontal=True)
            )
        else:
            body.append(
                f'<line x1="{label_w}" y1="{y:.1f}" x2="{label_w}" y2="{y + row_h}" '
                f'stroke="{AXIS}" stroke-width="1.5" data-tip="{_esc(tip)}" tabindex="0"/>'
            )
        body.append(_text(label_w + plot_w + 10, y + row_h - 5, f"{value:.2f}%", "val"))

    body.append(_split_legend(label_w, height - 30, sorted({s for _, s, _, _ in bars})))
    body.append(_text(label_w, height - 10, "measured on exact sequence identity", "leg"))

    svg = _svg(
        width,
        height,
        f"Split overlap — {dataset.benchmark_id}",
        f"Horizontal bars, two per split pair, showing what share of each split "
        f"also appears in the other for {dataset.benchmark_id}.",
        "".join(body),
    )
    return Figure(
        slug="dataset-leakage",
        title="Split overlap",
        caption=(
            "For every pair of splits the scan compared, the share of each "
            "split whose sequences also appear in the other. Each bar is "
            "coloured by the split it counts."
        ),
        note=(
            "The two directions of a pair are different statements. A held-out "
            "split largely contained in train is the one that bears on whether "
            "a score on it is a held-out score."
        ),
        svg=svg,
        table=_table(
            ["Comparison", "Share", "Flag"],
            [[label, f"{value:.2f}%", flag or "—"] for label, _, value, flag in bars],
            "Exact-sequence overlap, both directions, per split pair.",
        ),
    )


def dataset_figures(dataset: Dataset) -> tuple[Figure, ...]:
    """The three figures a dataset page carries, in the order it carries them."""
    return tuple(
        figure
        for figure in (
            dataset_check_grid(dataset),
            dataset_probe_bars(dataset),
            dataset_leakage_bars(dataset),
        )
        if figure.svg
    )


def corpus_figures(run: Run) -> tuple[Figure, ...]:
    return (
        check_bars(run),
        auroc_histogram(run),
        leakage_bands(run),
        collection_bars(run),
        flag_matrix(run),
        core_set_funnel(run),
    )
