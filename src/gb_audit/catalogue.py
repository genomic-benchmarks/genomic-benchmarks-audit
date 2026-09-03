"""The catalogue: one JSON document, ninety-three entries, everything the
browse page filters on.

Written at build time from `data/` and read by the browse page as a static
file. Nothing here reaches the network or opens a report archive, so the
catalogue -- and the largest page on the site -- can be built and reviewed on a
machine with no copy of the 91 MB of HTML reports.

**Every entry says which split its numbers were measured on.** The rollup
columns are the values on the dataset's reference split, not a maximum over
splits, and an entry that carried them without `reference_split` beside them
would invite exactly the wrong reading. The per-split figures are here too, so
a reader who wants to know whether a flag holds across splits can see it
without opening the report.

The document has no build timestamp. Everything in it comes from a pinned run,
so two builds of the same commit produce the same bytes and a diff of
`docs/data/catalogue.json` is a diff of what changed rather than of when it
ran. What replaces the timestamp is provenance: the audit run, the QC run and
the Zenodo record the archives come from.
"""

from __future__ import annotations

import json
from typing import Mapping

from . import __version__, audit, reports
from .audit import Dataset, Run

# Bumped when a consumer written for the previous shape would misread this one.
# The browse page is the only consumer today and lives in this repository, so
# this exists for the case where it stops being: a page a browser cached, or a
# script somebody wrote against the JSON.
SCHEMA_VERSION = 1

# The facets the browse page groups and filters by. Chosen because each one
# partitions the corpus in a way a reader is likely to already have a question
# about -- "is this a plant thing?", "is this all one collection?" -- rather
# than because the column happened to be available.
FACETS = (
    "collection",
    "task_category_grouped",
    "molecular_level",
    "task_type",
    "species",
    "overall_verdict",
)


def _split_entry(dataset: Dataset, split: str) -> dict:
    """One split: what it is, and what the checks said on it.

    Row counts are deliberately absent. How many rows a split has is the data
    package's fact and it is versioned there; restating it here would create a
    second copy that nothing keeps in step with the first.
    """
    spec = next((s for s in dataset.splits if s.split == split), None)
    measurements = dataset.measurements_on(split)
    flags = {}
    for check in audit.CLASS_CHECKS:
        found = [m.flag for m in measurements if m.check == check]
        flag = audit.worst_flag(found)
        if flag is None and audit.UNKNOWN in found:
            flag = audit.UNKNOWN
        flags[check] = flag
    strongest = dataset.strongest_probe_on(split)
    return {
        "split": split,
        "is_reference": split == dataset.reference_split,
        "seq_cols": list(spec.seq_cols) if spec else [],
        "label_col": spec.label_col if spec else None,
        "regression": spec.regression if spec else None,
        "num_labels": spec.num_labels if spec else None,
        "flags": flags,
        "rollup": audit.rollup([flags[c] for c in audit.CLASS_CHECKS]),
        "strongest_probe": strongest.check if strongest else None,
        "max_probe_auroc": dataset.probe_auroc_by_split.get(split),
    }


def _leakage_entry(dataset: Dataset) -> list[dict]:
    return [
        {
            "label": comparison.label,
            "query_split": comparison.query_split,
            "target_split": comparison.target_split,
            "flag": comparison.flag,
            "leaked_queries_pct": comparison.leaked_queries_pct,
            "leaked_targets_pct": comparison.leaked_targets_pct,
        }
        for comparison in dataset.leakage
    ]


def _reports_entry(dataset: Dataset, availability: reports.Availability) -> dict:
    """Where this dataset's rendered reports are, and whether they are here yet.

    `state` is the whole point. `unpacked` means the build found the HTML and
    the page links to it; `linked` means the archive is published and the page
    sends the reader to Zenodo; `unpublished` means neither, and the page says
    so instead of emitting a link that will 404. A site built with no network
    still renders every page.
    """
    manifest = dataset.reports
    return {
        "state": availability.state,
        "archive": manifest.archive if manifest else None,
        "bytes": manifest.n_bytes if manifest else None,
        "sha256": manifest.sha256 if manifest else None,
        "n_reports": len(manifest.paths) if manifest else 0,
        "files": [
            {
                "kind": report.kind,
                "title": report.title,
                "split": report.split,
                "seq_col": report.seq_col,
                "pair": list(report.pair) if report.pair else None,
                # The path inside the archive, and the path inside the site. Both,
                # because the first is what names the framed viewer and the second
                # is what the frame loads, and deriving either from the other in a
                # template is a string operation in the wrong place.
                "path": report.path,
                "href": reports.site_path(dataset, report),
            }
            for report in reports.reports_for(dataset)
        ],
    }


def entry(dataset: Dataset, availability: reports.Availability) -> dict:
    """One catalogue row: the facets, the rollup, and where to read more."""
    splits = list(dataset.split_names)
    return {
        "benchmark_id": dataset.benchmark_id,
        "collection": dataset.collection,
        "dataset_name": dataset.dataset_name,
        "slug": slug(dataset),
        "task_category": dataset.task_category,
        "task_category_grouped": dataset.task_category_grouped,
        "molecular_level": dataset.molecular_level,
        "task_type": dataset.task_type,
        "species": dataset.species,
        "n_species": dataset.n_species,
        "train_size": dataset.train_size,
        "total_size": dataset.total_size,
        "min_seq_length": dataset.min_seq_length,
        "max_seq_length": dataset.max_seq_length,
        "in_core_set": dataset.in_core_set,
        "core_set_rank": dataset.core_set_rank,
        # Every figure below was measured here. Named on the entry rather than
        # implied by it.
        "reference_split": dataset.reference_split,
        "overall_verdict": dataset.overall_verdict,
        "worst_class_flag": dataset.worst_class_flag,
        "n_checks_failed": dataset.n_checks_failed,
        "n_checks_warning": dataset.n_checks_warning,
        "n_checks_unknown": dataset.n_checks_unknown,
        "n_checks_reported": dataset.n_checks_reported,
        "n_checks_scored": dataset.n_checks_scored,
        "strongest_probe": dataset.strongest_probe,
        "max_probe_auroc": dataset.max_probe_auroc,
        "max_probe_accuracy": dataset.max_probe_accuracy,
        "max_leaked_test_pct": dataset.max_leaked_test_pct,
        "max_leaked_train_pct": dataset.max_leaked_train_pct,
        "worst_leakage_comparison": dataset.worst_leakage_comparison,
        "n_split_comparisons": dataset.n_split_comparisons,
        "flags": {check: dataset.flags[check] for check in audit.CHECKS},
        "probe_auroc_by_split": dict(sorted(dataset.probe_auroc_by_split.items())),
        "split_names": splits,
        "splits": [_split_entry(dataset, split) for split in splits],
        "leakage": _leakage_entry(dataset),
        "reports": _reports_entry(dataset, availability),
    }


def slug(dataset: Dataset) -> str:
    """The dataset's page name. One entry, one file, one stable URL.

    Derived from the benchmark id rather than stored, and asserted unique in
    `build()`: a slug collision would silently overwrite one dataset's page
    with another's, which is the kind of failure a reader cannot see.
    """
    return (
        dataset.benchmark_id.replace(":", "--")
        .replace("_", "-")
        .replace("/", "-")
        .replace(" ", "-")
        .lower()
    )


def build(run: Run | None = None, unpacked_root=None) -> dict:
    """The whole document, ready to serialise."""
    run = audit.run() if run is None else run
    entries = []
    seen: dict[str, str] = {}
    for benchmark_id in sorted(run.datasets):
        dataset = run.datasets[benchmark_id]
        name = slug(dataset)
        if name in seen:
            raise ValueError(
                f"{benchmark_id} and {seen[name]} both slug to {name!r}, so one "
                f"would overwrite the other's page. Change slug()."
            )
        seen[name] = benchmark_id
        entries.append(entry(dataset, reports.availability(dataset, unpacked_root)))

    gates = [
        {
            "step": gate.step,
            "criterion": gate.criterion,
            "requirement": gate.requirement,
            "threshold": gate.threshold,
            "n_in": gate.n_in,
            "n_removed": gate.n_removed,
            "n_out": gate.n_out,
        }
        for gate in sorted(run.gates, key=lambda g: g.step)
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": provenance(run),
        "checks": [
            {"name": name, "kind": audit.check_kind(name)} for name in audit.CHECKS
        ],
        "flags": list(audit.FLAGS),
        "totals": totals(run),
        "gates": gates,
        "exclusions": [dict(row) for row in run.exclusions],
        "facets": {
            facet: sorted(
                {value for row in entries if (value := row[facet]) is not None}
            )
            for facet in FACETS
        },
        "datasets": entries,
    }


def provenance(run: Run) -> dict:
    """Which run this is, and where its archives live. No timestamp."""
    recorded = run.provenance
    return {
        "package_version": __version__,
        "audit_run": recorded.get("audit_run"),
        "qc_run": recorded.get("qc_run"),
        "zenodo_record_id": recorded.get("zenodo_record_id"),
        "zenodo_concept_record_id": recorded.get("zenodo_concept_record_id"),
        "zenodo_record_registered": recorded.get("zenodo_record_registered"),
    }


def totals(run: Run) -> dict:
    """The corpus-level counts the pages quote, computed in one place.

    Every headline number on the site comes from here, so a page cannot quote a
    figure that disagrees with the catalogue -- and a figure that changes when
    the run is re-pinned changes on every page at once.
    """
    datasets = list(run.datasets.values())
    verdicts = {flag: 0 for flag in audit.FLAGS}
    for dataset in datasets:
        if dataset.overall_verdict in verdicts:
            verdicts[dataset.overall_verdict] += 1

    probed = sorted(d.max_probe_auroc for d in datasets if d.max_probe_auroc is not None)
    leaked = sorted(
        d.max_leaked_test_pct for d in datasets if d.max_leaked_test_pct is not None
    )
    excluded = sum(int(row.get("n_datasets", 0) or 0) for row in run.exclusions)
    gates = sorted(run.gates, key=lambda g: g.step)

    return {
        "n_datasets": len(datasets),
        "n_collections": len({d.collection for d in datasets}),
        "n_splits": run.n_splits,
        "n_reports": run.n_reports,
        "n_excluded": excluded,
        "n_exclusion_reasons": len(run.exclusions),
        "n_curated": len(datasets) + excluded,
        "verdicts": verdicts,
        "n_probed": len(probed),
        "median_max_probe_auroc": _median(probed),
        "n_probe_auroc_over_0_7": sum(1 for value in probed if value > 0.7),
        "n_leakage_scanned": len(leaked),
        "n_with_any_leakage": sum(1 for value in leaked if value > 0),
        "n_leakage_over_50_pct": sum(1 for value in leaked if value > 50),
        "median_max_leaked_test_pct": _median(leaked),
        "core_set_size": gates[-1].n_out if gates else 0,
        "n_reports_unpacked": None,  # filled by the site build, which knows
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def render(document: Mapping) -> str:
    """The file's text. Two-space indent and a trailing newline, so it diffs."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
