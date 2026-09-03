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
    """Two builds of one commit must produce the same bytes."""
    text = catalogue.render(document)
    assert "generated" not in text.lower()
    for key in document["provenance"]:
        assert "time" not in key and "date" not in key


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
