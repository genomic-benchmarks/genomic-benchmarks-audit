"""The catalogue: what the site fetches, and the one file CI gates."""

from __future__ import annotations

import json

import pytest
from gb_audit import audit, catalogue, site


def test_committed_catalogue_is_what_the_tables_produce(run, committed):
    """The gate itself. Everything else in this suite assumes it holds."""
    assert catalogue.render(catalogue.build(run)) == site.CATALOGUE.read_text(
        encoding="utf-8"
    )


def test_slugs_are_unique_and_url_safe(document):
    slugs = [d["slug"] for d in document["datasets"]]
    assert len(set(slugs)) == len(slugs)
    for slug in slugs:
        assert site.URL_SAFE.fullmatch(slug), slug


def test_every_dataset_names_its_reference_split(document):
    """A rollup with no named split is a number a reader cannot check."""
    for dataset in document["datasets"]:
        reference = dataset["reference_split"]
        assert reference in dataset["split_names"], dataset["benchmark_id"]
        marked = [s["split"] for s in dataset["splits"] if s["is_reference"]]
        assert marked == [reference], dataset["benchmark_id"]


def test_rollup_figures_come_from_the_reference_split_not_the_maximum(document):
    """The rule the whole site rests on, checked rather than trusted.

    A dataset whose strongest probe is on `val` must still quote the `train`
    figure. Taking a maximum would make a dataset look worse for having more
    splits, and would name no split anybody could go and check.
    """
    for dataset in document["datasets"]:
        by_split = {s["split"]: s for s in dataset["splits"]}
        reference = by_split[dataset["reference_split"]]
        assert dataset["max_probe_auroc"] == reference["max_probe_auroc"], (
            dataset["benchmark_id"]
        )
        assert dataset["overall_verdict"] == reference["rollup"]["flag"] or (
            dataset["flags"]["Split leakage"] in ("Warning", "Fail")
        ), dataset["benchmark_id"]


def test_check_counts_are_over_the_per_split_checks_only(document):
    """`n_checks_*` count the nine, not the ten. The tenth is not a per-split check.

    Worth pinning because the number reads like a count over every check on the
    page. The leakage scan compares pairs of splits, so it has no place in a
    count of what was measured *on* the reference split -- and a page that added
    it to these totals would be describing a different denominator from the one
    the tool used.
    """
    for dataset in document["datasets"]:
        per_split = {
            name: flag
            for name, flag in dataset["flags"].items()
            if name != "Split leakage"
        }
        counted = {
            "n_checks_scored": sum(
                1 for f in per_split.values() if f in ("Pass", "Warning", "Fail")
            ),
            "n_checks_unknown": sum(
                1 for f in per_split.values() if f == "Unknown"
            ),
            "n_checks_reported": sum(
                1 for f in per_split.values() if f is not None
            ),
            "n_checks_failed": sum(1 for f in per_split.values() if f == "Fail"),
            "n_checks_warning": sum(
                1 for f in per_split.values() if f == "Warning"
            ),
        }
        for field, expected in counted.items():
            assert dataset[field] == expected, (dataset["benchmark_id"], field)


def test_unknown_is_never_counted_as_a_pass(document):
    """An unscored check must never be summed into a scored total."""
    for dataset in document["datasets"]:
        assert (
            dataset["n_checks_scored"] + dataset["n_checks_unknown"]
            == dataset["n_checks_reported"]
        ), dataset["benchmark_id"]
        for split in dataset["splits"]:
            rollup = split["rollup"]
            flags = split["flags"].values()
            assert rollup["n_unknown"] == sum(1 for f in flags if f == "Unknown")
            assert rollup["n_scored"] == sum(
                1 for f in flags if f in ("Pass", "Warning", "Fail")
            )


def test_a_blank_flag_is_a_none_not_a_zero(document):
    """The one dataset with no leakage scan carries `null`, not `Pass`."""
    blanks = [
        d for d in document["datasets"] if d["flags"]["Split leakage"] is None
    ]
    assert len(blanks) == 1
    assert blanks[0]["max_leaked_test_pct"] is None


def test_no_timestamp_anywhere_in_the_document(document):
    """Two builds of one commit must produce the same bytes.

    Scanned over the document's keys rather than over its rendered text. The text
    scan was the same check until the entries began carrying licence notes, which
    are prose quoted from the sources: one of them says that the group who
    *generated* these measurements published them without restriction. The word is
    the source's and not this build's, and a build that stamped itself would do it
    in a key.
    """

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)

    for key in keys(document):
        lowered = key.lower()
        assert "generated" not in lowered, key
        assert "time" not in lowered and "date" not in lowered, key

    assert catalogue.render(catalogue.build()) == catalogue.render(document)


def test_totals_agree_with_the_rows_they_summarise(document):
    totals = document["totals"]
    datasets = document["datasets"]
    assert totals["n_datasets"] == len(datasets)
    assert totals["core_set_size"] == sum(1 for d in datasets if d["in_core_set"])
    assert totals["n_reports"] == sum(
        d["reports"]["n_reports"] for d in datasets if d["reports"]
    )
    assert totals["n_splits"] == sum(len(d["splits"]) for d in datasets)
    for flag, count in totals["verdicts"].items():
        assert count == sum(1 for d in datasets if d["overall_verdict"] == flag)


def test_render_is_stable(document):
    assert catalogue.render(document) == catalogue.render(document)


# ------------------------------------------------------- licence and credit ---


def test_every_dataset_says_what_it_may_be_used_for(document):
    """The promise the Data availability statement makes, checked per dataset.

    A page that names a collection and nothing else about it cannot republish it
    "with the attribution they require", because it never says what that is.
    """
    for entry in document["datasets"]:
        source = entry["source"]
        assert source is not None, entry["benchmark_id"]
        assert source["licence"], entry["benchmark_id"]
        assert source["doi"].startswith("https://doi.org/"), entry["benchmark_id"]
        assert source["collection_doi"].startswith("https://doi.org/")


def test_redistribution_is_one_of_the_three_answers(document):
    """`unknown` is not `denied`, and a fourth value would be published unread."""
    for entry in document["datasets"]:
        assert entry["source"]["redistribution"] in audit.REDISTRIBUTION


def test_a_dataset_that_may_not_be_republished_says_why(document):
    """A denial names who declined; without that it reads as this project's."""
    withheld = [
        d for d in document["datasets"] if d["source"]["redistribution"] != "permitted"
    ]
    assert len(withheld) == 16
    for entry in withheld:
        assert entry["source"]["licence_note"], entry["benchmark_id"]


def test_the_inherited_doi_is_labelled_as_inherited(document):
    """Two thirds of the corpus has no DOI of its own, and must not look as if
    it does."""
    inheriting = 0
    for entry in document["datasets"]:
        source = entry["source"]
        assert source["inherits_doi"] == (source["doi"] == source["collection_doi"])
        inheriting += source["inherits_doi"]
    assert inheriting == 67


def test_every_split_carries_a_route_back_to_its_file(document):
    """Per split, because that is the grain it varies at.

    For the sixteen datasets this project may not republish it is not a
    convenience: it is the only copy of the data there is.
    """
    seen = 0
    for entry in document["datasets"]:
        for split in entry["splits"]:
            assert split["source_url"].startswith("https://"), entry["benchmark_id"]
            seen += 1
    assert seen == 234
