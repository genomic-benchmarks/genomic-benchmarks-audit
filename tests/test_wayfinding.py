"""Where a reader is, and how they get anywhere else.

Four pages of this site are not pages any more. The datasets table is a section
of the overview; the index of reports is gone, with each report listed on the
dataset it belongs to; Methods is gone, with each of its subjects on the page its
question comes up on; and a dataset page carries the whole corpus down its left
side. Every one of those is about a reader knowing where they are, and every one
is the kind of thing that rots silently, because a link to a page that still
exists still resolves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Addresses that were published and are now signposts. None is a section of the
# masthead, none is somewhere this site sends anyone, and all have to keep
# resolving: a published URL that 404s is worse than one that moved.
#
# The first two forward on their own, having one destination each. `methods.html`
# does not: what was on it went to three different pages, so it lists them.
SIGNPOSTS = ("catalogue.html", "reports.html", "methods.html")

# Pages the masthead does not mark. The signposts, because they are addresses
# rather than places to be -- and `cite.html`, because it is one screen naming
# this run, reached from the run labels in the footer of every page rather than
# from a nav item the size of the three sections beside it.
UNMARKED = SIGNPOSTS + ("cite.html",)


def test_the_table_is_on_the_page_a_reader_lands_on(built):
    """Every control the table needs, on the overview rather than behind a click."""
    page = (Path(built["out"]) / "index.html").read_text()
    for element in (
        'id="datasets"', 'id="table"', 'id="search"', 'id="facets"',
        'id="presets"', 'id="picker"', 'id="explore"',
    ):
        assert element in page, element
    assert "tabulator.min.js" in page
    assert "assets/catalogue.js" in page


def test_the_grid_is_not_repeated_where_the_table_already_says_it(built):
    """One surface per statement.

    The table carries a column per check. A 93-by-10 grid of the same flags under
    it is the same statement twice, and two of anything on one page is what makes
    the page feel like it has no shape.
    """
    page = (Path(built["out"]) / "index.html").read_text()
    assert 'id="fig-flag-matrix"' not in page
    assert 'id="fig-flag-matrix"' in (Path(built["out"]) / "checks.html").read_text()


def test_the_old_table_address_still_resolves_and_forwards(built):
    """A published URL that 404s is worse than one that moved.

    `catalogue.html` was linked from a README, from the organisation site and from
    whatever anyone sent a colleague -- with a query string, because filtering the
    table and sending the address is a thing this site invited people to do.
    """
    page = (Path(built["out"]) / "catalogue.html").read_text()
    assert 'id="forward"' in page
    assert "assets/forward.js" in page
    assert 'href="index.html#datasets"' in page


def test_the_report_index_still_resolves_and_says_where_reports_went(built):
    """The other published address, and the one the site's own footer used.

    There is no index of reports any more: a report is the working behind one
    split of one dataset, so it is listed on that dataset. This page has to say
    that rather than 404, and has to send a reader somewhere that says it too.
    """
    page = (Path(built["out"]) / "reports.html").read_text()
    assert 'id="forward"' in page
    assert "assets/forward.js" in page
    assert 'href="index.html#datasets"' in page
    # Its filters narrowed a table that no longer exists. Carrying the query
    # string over would be carrying it nowhere.
    assert 'data-query="keep"' not in page


@pytest.mark.parametrize("moved", SIGNPOSTS)
def test_no_page_sends_a_reader_to_a_page_that_moved(built, pages, moved):
    """Internal links point at where the content went, not at the signpost."""
    for page in pages:
        if "qc-reports" in page.parts or page.name in SIGNPOSTS:
            continue
        text = page.read_text()
        assert not re.search(rf'href="[^"]*{re.escape(moved)}', text), page.name


def test_the_masthead_marks_exactly_one_section_per_page(built, pages):
    """`aria-current` is what says where you are, and it has to say one thing."""
    for page in pages:
        if "qc-reports" in page.parts:
            continue
        nav = re.search(r'<nav aria-label="Sections">(.*?)</nav>', page.read_text(), re.S)
        assert nav is not None, page.name
        marks = nav.group(1).count('aria-current="page"')
        assert marks == (0 if page.name in UNMARKED else 1), page.name


def test_every_long_page_says_which_of_its_sections_a_reader_is_in(built):
    """A page carrying what used to be two or three needs a map of itself.

    The overview absorbed the datasets table; the checks page absorbed what a
    flag is, which split it was measured on and how to read both scales. Each
    carries a jump list, and an entry pointing at an `id` the page does not have
    is a dead link that looks alive.
    """
    carrying = []
    for name in ("index.html", "checks.html"):
        page = (Path(built["out"]) / name).read_text()
        nav = re.search(r'<nav class="jumpnav".*?</nav>', page, re.S)
        assert nav is not None, name
        targets = re.findall(r'href="#([a-z-]+)"', nav.group(0))
        assert targets, name
        for target in targets:
            assert f'id="{target}"' in page, (name, target)
        carrying.append(name)
    assert len(carrying) == 2


def test_every_dataset_page_carries_the_whole_corpus_and_marks_its_place(
    built, committed
):
    """The left column: every dataset, under its collection, this one marked."""
    out = Path(built["out"])
    collections = {d["collection"] for d in committed["datasets"]}
    for dataset in committed["datasets"]:
        page = (out / "datasets" / f"{dataset['slug']}.html").read_text()
        nav = re.search(r'<nav class="dataset-nav".*?</nav>', page, re.S)
        assert nav is not None, dataset["benchmark_id"]
        body = nav.group(0)

        # Every collection is reachable, and every dataset in it.
        for collection in collections:
            assert f"<summary>{collection}<" in body, (dataset["slug"], collection)
        assert body.count("<li>") == len(committed["datasets"]), dataset["slug"]

        # Exactly one entry is the page you are on, and it is this one.
        current = re.findall(r'<a href="([^"]+)" aria-current="page"', body)
        assert current == [f"{dataset['slug']}.html"], dataset["benchmark_id"]

        # The reader's own collection is open; the other six are not.
        opened = re.findall(r'<details class="sb-group" open><summary>([^<]+)<', body)
        assert opened == [dataset["collection"]], dataset["benchmark_id"]


def test_the_sidebar_links_go_where_they_say(built, committed):
    """A relative link from one dataset page to another, resolved on disk."""
    out = Path(built["out"])
    sample = committed["datasets"][0]
    page = (out / "datasets" / f"{sample['slug']}.html").read_text()
    nav = re.search(r'<nav class="dataset-nav".*?</nav>', page, re.S).group(0)
    for href in re.findall(r'<li><a href="([^"]+)"', nav):
        assert (out / "datasets" / href).exists(), href


def test_a_dataset_page_offers_its_reports_before_it_shows_its_working(
    built, committed
):
    """The reports were at the foot of the page. They are the point of the page.

    A reader who wants the working behind a flag had to scroll past every figure
    on the page to find out it existed. So the offer is in the head, above the
    fold, and the list it jumps to sits directly under the summary of what the
    checks returned rather than after the leakage section.
    """
    page = (Path(built["out"]) / "datasets" / "beacon--crisprontarget.html").read_text()

    cta = page.index('class="badge-line reports-cta"')
    assert 'href="#reports"' in page[cta : cta + 400]

    # Above the first figure on the page, and above the per-split table.
    assert cta < page.index('class="stat-grid glance"')
    assert page.index('id="reports"') < page.index('id="checks"')
    assert page.index('id="reports"') < page.index("fig-dataset-probes")


def test_a_framed_report_says_which_dataset_it_is_a_report_of(built, committed):
    """The same trail as the dataset page, one step longer.

    A report opened from a dataset is four levels down and used to name only the
    50-character identifier. It now reads Overview, Datasets, the collection, the
    dataset, this report -- so the way back up is the same at every depth.
    """
    dataset = next(
        d for d in committed["datasets"] if d["benchmark_id"] == "BEACON:CRISPROnTarget"
    )
    report = dataset["reports"]["files"][0]
    stem = dataset["reports"]["archive"].removesuffix(".zip")
    page = (
        Path(built["out"]) / "view" / stem / report["path"].replace("/", "-")
    ).read_text()

    crumb = re.search(r'<nav class="crumb".*?</nav>', page, re.S).group(0)
    links = re.findall(r"<a [^>]*>([^<]+)</a>", crumb)
    assert links == ["Overview", "Datasets", dataset["collection"], dataset["dataset_name"]]
    assert f'<span class="here">{report["title"]}</span>' in crumb


def test_the_citation_is_reachable_from_every_page(built, pages):
    """It is not in the masthead, so the footer is the whole of its findability.

    A page that says what a number on screen belongs to is worth one link from
    every page that shows one. It is in the footer, beside the run labels it
    names, which is the only reason it does not need to be in the masthead.
    """
    for page in pages:
        if "qc-reports" in page.parts:
            continue
        assert "cite.html" in page.read_text(), page.name


def test_methods_says_where_each_of_its_parts_went(built):
    """Six subjects went to three pages, so this one guesses at none of them.

    The other two moved addresses forward on their own, each having one
    destination. This one lists, because a page that picks one of six for a
    reader is wrong five times.
    """
    page = (Path(built["out"]) / "methods.html").read_text()
    for target in (
        "checks.html#flags", "checks.html#reference-split", "checks.html#probes",
        "checks.html#leakage", "core-set.html#joint", "cite.html",
    ):
        assert f'href="{target}"' in page, target

    # Nothing redirects: no anchor for `forward.js` to read, and no `forward.js`.
    assert 'id="forward"' not in page
    assert "assets/forward.js" not in page


def test_every_anchor_this_site_links_to_is_on_the_page_it_names(built, pages):
    """A section that moved pages leaves every `#anchor` at it pointing at nothing.

    Six sections changed page in one go. A link to `methods.html#probes` still
    resolves as a file and lands a reader at the top of a signpost, which is the
    failure this catches and a browser does not.
    """
    out = Path(built["out"])
    ids = {}
    dangling = []
    for page in pages:
        if "qc-reports" in page.parts:
            continue
        text = page.read_text()
        for href in re.findall(r'href="([^":]*#[a-zA-Z0-9_-]+)"', text):
            path, _, anchor = href.partition("#")
            # A link into the table carries its filters. `index.html?core=1` and
            # `index.html` are the same file and the same anchors.
            path = path.partition("?")[0]
            target = (page.parent / path).resolve() if path else page
            if not target.is_file():
                dangling.append(f"{page.name} -> {href}")
                continue
            if target not in ids:
                ids[target] = set(
                    re.findall(r'id="([^"]+)"', target.read_text())
                )
            if anchor not in ids[target]:
                dangling.append(f"{page.name} -> {href}")
    assert not dangling, sorted(set(dangling))[:10]
