"""The render: that every page is complete, and says nothing it should not."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from gb_audit import site, zenodo

PLACEHOLDER_LEFT = re.compile(r"\{\{[a-z0-9_]+\}\}")


@pytest.fixture(scope="session")
def pages(built):
    return sorted(Path(built["out"]).rglob("*.html"))


def test_every_page_kind_is_written(built):
    out = Path(built["out"])
    for name in (
        "index.html", "catalogue.html", "checks.html", "core-set.html",
        "reports.html", "methods.html", ".nojekyll",
    ):
        assert (out / name).exists(), name
    assert built["dataset_pages"] == 93
    assert built["report_views"] == 423


def test_no_placeholder_survives_into_a_page(built):
    """The failure `TemplateError` exists to prevent, checked on the output too.

    `fill()` raises on a name it has no value for, but a `{{name}}` written into
    a *part* that no page renders, or into a string this module builds by hand,
    would never reach `fill()` at all.
    """
    for page in Path(built["out"]).rglob("*.html"):
        if site.reports.SITE_DIR in page.parts:
            continue  # written by genomic-benchmarks-qc, not from a template
        found = PLACEHOLDER_LEFT.search(page.read_text(encoding="utf-8"))
        assert found is None, f"{page.name}: {found.group(0)}"


def test_the_copy_block_survives_being_filled(built):
    """It is JSON inside HTML, and `fill()` runs over it. It must still parse."""
    for name in ("index.html", "catalogue.html", "methods.html"):
        text = (Path(built["out"]) / name).read_text(encoding="utf-8")
        match = site.COPY_BLOCK.search(text)
        assert match is not None, name
        copy = json.loads(match.group("json"))
        assert "10" in copy["panel"]["checks_heading"]


def test_no_draft_token_is_ever_rendered(built, monkeypatch):
    """A share token in a published page is a published token.

    The build is allowed to read the draft; the site it writes is not allowed to
    say how. `public_record_url()` exists for this and this test is what keeps it
    being the one the templates use.
    """
    assert "token" not in zenodo.public_record_url()
    for page in Path(built["out"]).rglob("*.html"):
        if site.reports.SITE_DIR in page.parts:
            continue
        text = page.read_text(encoding="utf-8")
        assert "preview=1" not in text
        assert "?token=" not in text


def test_every_internal_link_resolves(built):
    """No page links to a file the build did not write."""
    out = Path(built["out"])
    missing = []
    for page in out.rglob("*.html"):
        if site.reports.SITE_DIR in page.parts:
            continue
        text = page.read_text(encoding="utf-8")
        for href in re.findall(r'(?:href|src)="([^"#?:]+)"', text):
            if href.startswith(("http", "//", "mailto:", "data:")):
                continue
            target = (page.parent / href).resolve()
            if not target.exists():
                missing.append(f"{page.relative_to(out)} -> {href}")
    assert not missing, missing[:10]


def test_a_blank_flag_renders_as_a_blank_not_a_pass(copy):
    """The chip for a check with nothing to run on says so and is not Pass."""
    visible = lambda chunk: re.sub(r"<[^>]+>", "", chunk)

    blank = site.flag_chip(None, copy)
    assert 'class="flag flag-blank"' in blank
    assert visible(blank) == "&mdash;"
    assert "nothing to run on" in blank  # in the tooltip, where it belongs

    unknown = site.flag_chip("Unknown", copy)
    assert 'class="flag flag-Unknown"' in unknown
    assert visible(unknown) == "Unknown"
    assert "not a Pass" in unknown


def test_an_absent_measurement_never_renders_as_zero(copy):
    assert "0" not in site.measurement(None, "{:.3f}", copy)
    assert site.measurement(0.0, "{:.3f}", copy) == "0.000"
    assert site.number(None) == "&mdash;"
    assert site.number(0) == "0"


def test_the_build_is_reproducible(run, tmp_path):
    """Two builds of one commit produce the same bytes, or `--check` is noise."""
    first = site.build(tmp_path / "a", run=run)
    second = site.build(tmp_path / "b", run=run)
    for page in ("index.html", "checks.html", "datasets/beacon--crisprontarget.html"):
        assert (Path(first["out"]) / page).read_text() == (
            Path(second["out"]) / page
        ).read_text(), page


def test_a_stale_catalogue_refuses_to_render(run, tmp_path, monkeypatch):
    """The figures come from the run and the tables from the catalogue.

    If those disagree the page shows a picture and a number that contradict each
    other, and neither says which is right -- so the build stops instead.
    """
    stale = tmp_path / "catalogue.json"
    stale.write_text('{"schema_version": 0, "datasets": []}')
    monkeypatch.setattr(site, "CATALOGUE", stale)
    with pytest.raises(site.StaleCatalogue):
        site.build(tmp_path / "site", run=run)


def test_a_template_asking_for_an_unknown_value_raises():
    with pytest.raises(site.TemplateError) as raised:
        site.fill("{{n_widgets}}", {"n_datasets": "93"}, "somewhere")
    assert "n_widgets" in str(raised.value)


def test_report_views_frame_the_raw_file(built, committed):
    """The viewer loads the report; it does not copy or re-parse it."""
    out = Path(built["out"])
    dataset = next(d for d in committed["datasets"] if d["reports"]["files"])
    entry = dataset["reports"]
    stem = entry["archive"].removesuffix(".zip")
    for report in entry["files"]:
        view = out / site.view_path(stem, report["path"])
        assert view.exists(), view
        text = view.read_text(encoding="utf-8")
        raw = f"../../{site.reports.SITE_DIR}/{stem}/{report['path']}"
        assert f'src="{raw}"' in text
        assert (view.parent / raw).resolve().exists()


def test_cardinals_read_as_words_where_prose_needs_them():
    assert site.cardinal(9) == "nine"
    assert site.cardinal(93) == "93"


def test_the_reports_live_in_the_site_and_survive_a_rebuild(built, run):
    """One copy, at the address the pages link to, that a render does not delete."""
    out = Path(built["out"])
    root = site.reports.report_root(out)
    assert built["reports_present"] == 423
    assert (root / "BEACON-CRISPROnTarget" / "class" / "train" / "seq.html").is_file()

    site.build(out, run=run)
    assert (root / "BEACON-CRISPROnTarget" / "class" / "train" / "seq.html").is_file()
    assert not (out / "index.html").is_dir()


def test_a_build_with_no_reports_still_renders_every_page(built_bare):
    """The build must work with no network, and say what it does not have."""
    out = Path(built_bare["out"])
    assert built_bare["reports_present"] == 0
    assert built_bare["dataset_pages"] == 93
    assert built_bare["report_views"] == 0
    assert not site.reports.report_root(out).exists()
    assert "Run" in (out / "reports.html").read_text(encoding="utf-8")


def test_the_catalogue_says_nothing_about_this_machine(run, tmp_path):
    """The committed bytes must not depend on whether the reports were fetched.

    They are 450 MB nobody clones, so a catalogue that recorded their presence
    would be a file a laptop and CI disagree about for the same commit, and
    `gb-audit build --check` would fail on a clean checkout.
    """
    rendered = site.catalogue.render(site.catalogue.build(run))
    assert rendered == site.CATALOGUE.read_text(encoding="utf-8")
    assert "unpacked" not in rendered


def test_render_refuses_a_directory_it_did_not_write(tmp_path, run):
    """`--out` is a path a person types, and `build()` empties what is at it."""
    theirs = tmp_path / "documents"
    theirs.mkdir()
    (theirs / "thesis.tex").write_text("important")
    with pytest.raises(site.NotASite) as raised:
        site.build(theirs, run=run)
    assert "thesis.tex" in str(raised.value)
    assert (theirs / "thesis.tex").is_file()


def test_the_route_note_names_the_route_only_where_it_changes_what_they_are():
    """Bytes from an unpublished draft are not bytes a reader can go and get."""
    assert "unpublished draft" in site.route_note("zenodo_draft", 423)
    assert "local copy" in site.route_note("local_mirror", 423)
    assert site.route_note("zenodo", 423) == ""
    assert site.route_note("zenodo_draft", 0) == ""
