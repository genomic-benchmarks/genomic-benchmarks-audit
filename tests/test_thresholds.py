"""The threshold explorer: what it may re-decide, and what it must never touch.

The sliders answer "your boundaries are arbitrary" by letting a reader move them.
That only works if what moves is a flag and never a measurement, so the checks
here are mostly about what the grid does *not* hand the script.
"""

from __future__ import annotations

import re
from pathlib import Path

from gb_audit import audit, matrix

CELL = re.compile(r'<td class="mx-cell[^"]*"([^>]*)>')


def cells(html: str) -> list[dict[str, str]]:
    """Every grid cell, as the attributes `thresholds.js` reads off it."""
    out = []
    for attrs in CELL.findall(html):
        out.append(dict(re.findall(r'data-([a-z]+)="([^"]*)"', attrs)))
    return out


def test_every_probe_cell_carries_the_number_its_flag_came_from(run, copy):
    """Re-deciding a flag needs the value, and it has to be the published one.

    Compared against the run rather than merely asserted present: a cell carrying
    some other split's AUROC would re-decide correctly and describe the wrong
    measurement.
    """
    html = matrix.flag_matrix(run, copy)
    published = {}
    for dataset in run.datasets.values():
        for m in dataset.measurements:
            if m.split == dataset.reference_split and m.check in audit.PROBE_CHECKS:
                published[(dataset.benchmark_id, m.check)] = m.au_roc

    seen = 0
    for row in re.findall(r'<tr data-id="([^"]*)"(.*?)</tr>', html, re.S):
        benchmark_id, body = row
        for cell in cells(body):
            if "auroc" not in cell:
                continue
            expected = published[(benchmark_id, cell["check"])]
            assert abs(float(cell["auroc"]) - expected) < 1e-6, (benchmark_id, cell)
            seen += 1
    assert seen > 400, "the six probes over 93 datasets is most of the grid"


def test_nothing_that_cannot_be_re_decided_is_given_a_number(run, copy):
    """Three kinds of cell have no boundary to move, and get no value.

    An integrity check is not scored on a scale. `Unknown` is a check that could
    not be scored, and a blank is one with nothing to run on -- handing either a
    number is what would let a slider turn an absence of measurement into a Pass.
    """
    for cell in cells(matrix.flag_matrix(run, copy)):
        scale = "auroc" in cell or "leaked" in cell
        if cell.get("check") in audit.INTEGRITY_CHECKS:
            assert not scale, cell
        if cell.get("flag") in (None, audit.UNKNOWN):
            assert not scale, cell


def test_re_deciding_at_the_shipped_setting_reproduces_the_published_rollup(
    run, copy, committed
):
    """The script's rule, applied to the grid's own numbers, against the run.

    This is the check that makes the whole panel trustworthy: if re-deciding at
    the boundaries the run used did not return the flags the run published, then
    every other setting the reader can reach would be wrong in some unknown way.
    """
    severity = {"Pass": 0, "Warning": 1, "Fail": 2}

    def decide(auroc, leaked, warn=0.60, fail=0.70, leak=2.0):
        if auroc is not None:
            return "Fail" if auroc > fail else "Warning" if auroc > warn else "Pass"
        return "Fail" if leaked >= leak else "Warning" if leaked > 0 else "Pass"

    html = matrix.flag_matrix(run, copy)
    worst = {"Pass": 0, "Warning": 0, "Fail": 0}
    for benchmark_id, body in re.findall(r'<tr data-id="([^"]*)"(.*?)</tr>', html, re.S):
        top = None
        for cell in cells(body):
            flag = cell.get("flag")
            if flag is None or flag == audit.UNKNOWN:
                continue
            if "auroc" in cell or "leaked" in cell:
                flag = decide(
                    float(cell["auroc"]) if "auroc" in cell else None,
                    float(cell["leaked"]) if "leaked" in cell else None,
                )
            if top is None or severity[flag] > severity[top]:
                top = flag
        if top is not None:
            worst[top] += 1

    verdicts = committed["totals"]["verdicts"]
    assert worst == {k: verdicts[k] for k in worst}


def test_the_panel_ships_hidden_and_states_the_shipped_setting(built):
    """The sliders reveal themselves, and the page carries the run's own values.

    Hidden because sliders that recolour nothing are worse than no sliders. The
    values are on the form rather than in the script so that the page and the
    script cannot come to disagree about which setting is the published one.
    """
    page = (Path(built["out"]) / "checks.html").read_text()
    form = re.search(r'<form class="thresholds"[^>]*>', page)
    assert form is not None
    assert " hidden" in form.group(0)
    for name, value in (("warn", "0.60"), ("fail", "0.70"), ("leak", "2.0")):
        assert f'data-{name}="{value}"' in form.group(0)


def test_the_panel_is_only_where_the_grid_is(built):
    """Sliders on a page with nothing to recolour would be a control that lies."""
    out = Path(built["out"])
    assert 'id="thresholds"' in (out / "checks.html").read_text()
    assert 'id="thresholds"' not in (out / "index.html").read_text()
