"""The figures: that they are honest, legible, and the same bytes twice."""

from __future__ import annotations

import re
import zlib

import pytest
from gb_audit import charts

# --- colour ------------------------------------------------------------------
#
# Reproduced here rather than imported: a palette checked by the same code that
# chose it is not checked. Vienot (1999) matrices and a plain CIELAB dE76.

RGB2LMS = ((17.8824, 43.5161, 4.11935),
           (3.45565, 27.1554, 3.86714),
           (0.0299566, 0.184309, 1.46709))
LMS2RGB = ((0.080944, -0.130504, 0.116721),
           (-0.0102485, 0.0540194, -0.113615),
           (-0.000365294, -0.00412163, 0.693513))
SIMULATE = {
    "protan": ((0, 2.02344, -2.52581), (0, 1, 0), (0, 0, 1)),
    "deutan": ((1, 0, 0), (0.494207, 0, 1.24827), (0, 0, 1)),
    "tritan": ((1, 0, 0), (0, 1, 0), (-0.395913, 0.801109, 0)),
}


def _mul(matrix, vector):
    return tuple(sum(m * v for m, v in zip(row, vector)) for row in matrix)


def _linear(channel):
    channel /= 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _srgb(value):
    value = max(0.0, min(1.0, value))
    out = 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return max(0.0, min(255.0, out * 255))


def _hex(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def simulate(colour, kind):
    rgb = _hex(colour)
    lms = _mul(RGB2LMS, rgb)
    return tuple(_srgb(c / 255.0) for c in _mul(LMS2RGB, _mul(SIMULATE[kind], lms)))


def lab(rgb):
    r, g, b = (_linear(float(c)) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(one, two):
    a, b = lab(one), lab(two)
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def relative_luminance(colour):
    r, g, b = (_linear(float(c)) for c in _hex(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@pytest.mark.parametrize("kind", ["protan", "deutan", "tritan"])
def test_the_flag_ramp_stays_apart_under_colour_vision_deficiency(kind):
    """Three fills, and every pair distinguishable in all three simulations.

    9.0 is the threshold this project uses for categorical fills. `Unknown` is
    absent from the ramp on purpose: it is a hatch, not a fourth colour.
    """
    fills = list(charts.FLAG_FILL.values())
    worst = min(
        delta_e(simulate(a, kind), simulate(b, kind))
        for i, a in enumerate(fills)
        for b in fills[i + 1:]
    )
    assert worst >= 9.0, f"{kind}: worst pair dE {worst:.1f}"


@pytest.mark.parametrize("kind", ["protan", "deutan", "tritan"])
def test_the_split_series_stays_apart_too(kind):
    fills = list(charts.SPLIT_FILL.values())
    worst = min(
        delta_e(simulate(a, kind), simulate(b, kind))
        for i, a in enumerate(fills)
        for b in fills[i + 1:]
    )
    assert worst >= 9.0, f"{kind}: worst pair dE {worst:.1f}"


def test_severity_is_ordered_by_lightness_not_only_by_hue():
    """So the ramp still reads in greyscale, in print, and to a colourblind eye.

    Colour is never the only signal on this site; lightness carrying the ordering
    is the half of that promise the palette itself has to keep.
    """
    ordered = [charts.FLAG_FILL[f] for f in ("Pass", "Warning", "Fail")]
    lightness = [relative_luminance(c) for c in ordered]
    assert lightness == sorted(lightness, reverse=True), lightness
    for lighter, darker in zip(lightness, lightness[1:]):
        assert lighter - darker > 0.05


def test_unknown_is_a_hatch_and_not_a_fourth_fill():
    """A check that ran and could not be scored is a different kind of thing.

    Encoding it as one more colour on the severity ramp says it sits somewhere on
    that ramp. It does not.
    """
    assert "Unknown" not in charts.FLAG_FILL
    assert charts.UNKNOWN_INK not in charts.FLAG_FILL.values()
    mark = charts._flag_mark(0, 0, 10, 10, "Unknown", "a tooltip")
    assert "url(#" in mark  # the hatch pattern, not a fill
    assert charts._flag_mark(0, 0, 10, 10, None, "a tooltip") == ""


def test_svg_ids_are_stable_across_processes():
    """`hash()` is salted per process; two builds must produce the same bytes."""
    title = "Strongest single-feature probe"
    assert f"{zlib.crc32(title.encode('utf-8')):08x}" in charts._svg(
        200, 100, title, "a description", "<g/>"
    )


# --- content -----------------------------------------------------------------

def test_every_dataset_draws_without_raising(run):
    drawn = 0
    for dataset in run.datasets.values():
        for figure in charts.dataset_figures(dataset):
            assert figure.svg.startswith("<svg")
            drawn += 1
    assert drawn > 250


def test_every_figure_ships_a_table_of_the_same_numbers(run):
    """No figure is the only statement of what it shows."""
    figures = list(charts.corpus_figures(run)) + list(
        charts.dataset_figures(next(iter(run.datasets.values())))
    )
    for figure in figures:
        assert figure.table, figure.slug
        rendered = charts.render(figure)
        assert "<details" in rendered and "<table" in rendered
        assert figure.caption in rendered


def test_no_label_is_cut_off_mid_word():
    """Thresholds were being clipped at a character count, which read as a
    different threshold: `< 2% of held-o` is not a criterion anybody can check."""
    wrapped = charts._wrap(
        "flag != Fail in any split pair (< 2% of held-out sequences)", 34, lines=2
    )
    assert "".join(wrapped).replace(" ", "") in (
        "flag!=Failinanysplitpair(<2%ofheld-outsequences)"
    ).replace(" ", "")
    for line in wrapped:
        assert not line.endswith("-") or line.endswith("held-")


def test_figures_carry_a_title_and_description_for_a_screen_reader(run):
    for figure in charts.corpus_figures(run):
        assert 'role="img"' in figure.svg
        assert "<title" in figure.svg and "<desc>" in figure.svg
