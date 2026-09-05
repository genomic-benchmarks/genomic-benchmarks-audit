"""The flag matrix: that it is the manuscript's figure, in HTML.

The grid on this site and Supplementary Figure 2 of the paper are the same
figure drawn twice, so what these tests pin is the layout the two have to share
-- the column order, the family bands, and where a dataset sits inside its
collection. The orders are written out here rather than imported from
`gb_audit.audit`, because an order checked against the constant that declares it
is not checked. They are transcribed from
`GenBench2_paper/workflows/dataset_audit/bin/plot_audit_overview.py`
(`CATEGORY_CHECK_ORDER`, `CHECK_FAMILIES`) and `plot_flag_matrix.py`
(`build_blocks`).
"""

from __future__ import annotations

import re

from gb_audit import matrix, site

# CATEGORY_CHECK_ORDER: the composition probes, then length, then the two
# positional ones; the duplicate checks before the alphabet check; leakage last.
PAPER_COLUMNS = [
    "Per sequence GC content",
    "Per sequence nucleotide content",
    "Per sequence dinucleotide content",
    "Sequence lengths",
    "Per position nucleotide content",
    "Per position reversed nucleotide content",
    "Sequence Duplications within Labels",
    "Duplicate Sequences between Labels",
    "Unique bases",
    "Split leakage",
]
# CHECK_FAMILIES, as the spans a band row can be drawn over.
PAPER_BANDS = [(6, "probe checks"), (3, "integrity checks"), (1, "leakage scan")]


def rendered(run):
    return matrix.flag_matrix(run, site.site_copy())


def blocks(html):
    """The grid's collection blocks, each as (collection, [dataset ids])."""
    out = []
    for collection, body in re.findall(
        r'<tbody data-collection="([^"]+)">(.*?)</tbody>', html, re.S
    ):
        names = re.findall(
            r'<th scope="row" class="mx-name"><a [^>]*title="([^"]+)"', body
        )
        out.append((collection, names))
    return out


def test_columns_are_the_papers_order(run):
    heads = re.search(r'<tr class="mx-heads">(.*?)</tr>', rendered(run), re.S)
    assert re.findall(r'title="([^"]+)"', heads.group(1)) == PAPER_COLUMNS


def test_bands_tile_the_columns_in_families(run):
    bands = re.search(r'<tr class="mx-bands">(.*?)</tr>', rendered(run), re.S)
    found = [
        (int(span), name)
        for span, name in re.findall(
            r'<th scope="colgroup" colspan="(\d+)">([^<]+)</th>', bands.group(1)
        )
    ]
    assert found == PAPER_BANDS
    assert sum(span for span, _ in found) == len(PAPER_COLUMNS)


def test_collections_are_alphabetical_and_whole(run, committed):
    found = blocks(rendered(run))
    assert [collection for collection, _ in found] == sorted(
        {d["collection"] for d in committed["datasets"]}
    )
    assert sum(len(names) for _, names in found) == len(committed["datasets"])


def test_rows_are_worst_first_the_papers_way(run, committed):
    """(checks flagged, checks flagged Fail, name) -- `build_blocks`, descending.

    Computed here from the committed catalogue rather than from the objects the
    figure sorted, so the two routes to the order have nothing in common but the
    run they describe.
    """
    by_collection: dict[str, list] = {}
    for dataset in committed["datasets"]:
        flags = [dataset["flags"][check] for check in PAPER_COLUMNS]
        by_collection.setdefault(dataset["collection"], []).append(
            (
                -sum(1 for flag in flags if flag in ("Warning", "Fail")),
                -sum(1 for flag in flags if flag == "Fail"),
                dataset["dataset_name"],
                dataset["benchmark_id"],
            )
        )
    expected = [
        (collection, [row[3] for row in sorted(by_collection[collection])])
        for collection in sorted(by_collection)
    ]
    assert blocks(rendered(run)) == expected


def test_every_cell_is_present_and_a_blank_is_not_a_link(run, committed):
    html = rendered(run)
    cells = re.findall(r'<td class="mx-cell([^"]*)"[^>]*>(.*?)</td>', html, re.S)
    assert len(cells) == len(committed["datasets"]) * len(PAPER_COLUMNS)

    blanks = [body for kind, body in cells if "mx-blank" in kind]
    expected_blanks = sum(
        1
        for dataset in committed["datasets"]
        for flag in dataset["flags"].values()
        if flag is None
    )
    assert len(blanks) == expected_blanks
    # A check with nothing to run on has no result to open, so it is a cell and
    # not a link -- and it still says so out loud.
    assert all("<a " not in body for body in blanks)
    assert all("no result recorded" in body for body in blanks)

    # Colour is never the only signal: every scored cell carries its flag as text.
    for kind, body in cells:
        if "mx-blank" in kind:
            continue
        flag = kind.strip().removeprefix("mx-")
        assert f'<span class="sr-only">{flag}</span>' in body


def test_every_mark_links_to_the_dataset_it_belongs_to(run, committed):
    html = rendered(run)
    slugs = {d["slug"] for d in committed["datasets"]}
    # The cell carries its check, its flag and -- where one exists -- the value
    # the flag was decided from, between the class and the link.
    targets = re.findall(r'<td class="mx-cell[^"]*"[^>]*><a href="datasets/([^"#]+)', html)
    assert len(targets) == len(committed["datasets"]) * len(PAPER_COLUMNS) - sum(
        1
        for dataset in committed["datasets"]
        for flag in dataset["flags"].values()
        if flag is None
    )
    assert {target.removesuffix(".html") for target in targets} <= slugs
