"""The catalogue: one JSON document, ninety-three entries, everything the
browse page filters on.

Written at build time from `data/` and read by the browse page as a static
file. Nothing here reaches the network or opens a report archive, so the
catalogue -- and the largest page on the site -- can be built and reviewed on a
machine with no copy of the 91 MB of HTML reports.

**Nothing in it is a fact about the machine that built it**, which is what makes
`gb-audit build --check` a usable gate: one commit, the same bytes on a laptop
holding all 423 reports and in CI holding none. Whether a report can be opened is
resolved by the site while rendering.

**Every entry says which split its numbers were measured on.** The rollup columns
are the values on the reference split, not a maximum over splits; the per-split
figures are here too, so a flag can be checked across splits without opening a
report.

No build timestamp. Everything comes from a pinned run, so two builds of one
commit produce the same bytes. What replaces the timestamp is provenance: the
audit run, the QC run and the Zenodo record.
"""

from __future__ import annotations

import json
from typing import Mapping

from . import __version__, audit, reports
from .audit import Dataset, Run

# Bumped when a consumer written for the previous shape would misread this one:
# a page a browser cached, or a script somebody wrote against the JSON.
#
# 3 adds `probe_auroc` to every entry. A reader on the previous shape is not
# misled by it, but a browser holding the previous shape in cache would hand the
# new browse page six probes with no numbers on them, which is a figure that
# would draw an empty axis rather than say it has nothing.
#
# 4 adds `joint` and `gates` to every entry, and a sixth gate to `gates`. This one
# a stale consumer would actively misread rather than merely miss: the Core Set it
# describes has different members, and a page that showed the previous ten beside
# the new funnel would state a membership no gate in front of it produces.
SCHEMA_VERSION = 4

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

    Row counts are absent on purpose: that is the data package's fact, versioned
    there.
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
        # Where this split's file is served from. Per split because that is where
        # it varies, and on the entry because a reader who wants the data wants
        # the file rather than the collection it belongs to.
        "source_url": spec.source_url if spec else None,
        "flags": flags,
        "rollup": audit.rollup([flags[c] for c in audit.CLASS_CHECKS]),
        "strongest_probe": strongest.check if strongest else None,
        "max_probe_auroc": dataset.probe_auroc_by_split.get(split),
    }


def _probe_auroc(dataset: Dataset) -> dict[str, float | None]:
    """What each of the six probes reached on the reference split.

    `max_probe_auroc` is the strongest of these and answers "how far did one
    feature get". It cannot answer "which feature", across more than one dataset
    at a time: two datasets whose strongest probe reaches 0.83 are the same row
    in that column whether the feature was GC content or sequence length, and
    which of the six carries a corpus is the thing worth being able to ask.

    Every check that ran is a key, `None` included, so a probe that reported no
    AUROC is distinguishable from one that never ran here -- the same distinction
    `flags` keeps between `Unknown` and a blank.
    """
    reference = dataset.reference_split
    if reference is None:
        return {}
    scored = {m.check: m.au_roc for m in dataset.measurements_on(reference)}
    return {check: scored[check] for check in audit.PROBE_CHECKS if check in scored}


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


def _source_entry(dataset: Dataset) -> dict | None:
    """The licence, the DOI, and whether the split files here are ours to serve.

    `inherits_doi` is stated rather than left to be inferred from the two DOIs
    being equal, so a page can write "the collection's DOI" without recomputing
    the comparison and getting the direction wrong.
    """
    source = dataset.source
    if source is None:
        return None
    return {
        "doi": source.doi,
        "collection_doi": source.collection_doi,
        "inherits_doi": source.inherits_doi,
        "licence": source.licence,
        "licence_url": source.licence_url,
        "redistribution": source.redistribution,
        "licence_note": source.licence_note,
    }


def _reports_entry(dataset: Dataset) -> dict:
    """Which reports this dataset has, and what each one is.

    What the run produced, and nothing about whether the files are on the machine
    reading this -- which is what lets a dataset page name a file it cannot
    open. Whether it can be opened is `reports.state()`.
    """
    manifest = dataset.reports
    return {
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


def _joint_entry(dataset: Dataset) -> dict | None:
    """What the checks' features recover together, with the caveat attached.

    `lower_bound` and `caveat` are not separable from the value: where the window
    was capped or the pool subsampled the measurement can only be too low, and a
    consumer that took the number alone would read a capped 0.79 as clearing a
    ceiling it may not clear.
    """
    joint = dataset.joint
    if joint is None:
        return None
    return {
        "auroc": joint.au_roc,
        "lo": joint.lo,
        "hi": joint.hi,
        "split": joint.split,
        "n_held_out": joint.n_held_out,
        "lower_bound": joint.lower_bound,
        "caveat": joint.caveat,
    }


def entry(dataset: Dataset) -> dict:
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
        # The strongest probe by split, and every probe on the reference split.
        # The first is how a flag was decided; the second is what the browse page
        # draws one mark per dataset per probe from.
        "probe_auroc_by_split": dict(sorted(dataset.probe_auroc_by_split.items())),
        "probe_auroc": _probe_auroc(dataset),
        # The same features the ten checks use, read together rather than one at a
        # time, on a held-out split. It is the only number on an entry the audit
        # did not compute -- it comes from the Core Set run -- and the only one
        # measured somewhere other than the reference split, so it carries its own
        # split name rather than borrowing the entry's.
        "joint": _joint_entry(dataset),
        # Each gate's own verdict, and the first one the dataset broke. Carried per
        # dataset so a page can say why a dataset is not in the Core Set without
        # re-deriving it from six numbers and getting the order wrong.
        "gates": {name: dataset.gates.get(name) for name in audit.GATES},
        "excluded_by": dataset.excluded_by,
        "split_names": splits,
        "splits": [_split_entry(dataset, split) for split in splits],
        "leakage": _leakage_entry(dataset),
        "reports": _reports_entry(dataset),
        # Not a measurement, and the only block here the audit did not produce:
        # read out of the corpus metadata record, which is where the curation
        # wrote down what each collection may be republished under and who it
        # credits. Carried per dataset because the licence is resolved per dataset
        # -- eleven override their collection's.
        "source": _source_entry(dataset),
    }


def slug(dataset: Dataset) -> str:
    """The dataset's page name. One entry, one file, one stable URL.

    Derived from the benchmark id, and asserted unique in `build()`: a collision
    would silently overwrite one dataset's page with another's.
    """
    return (
        dataset.benchmark_id.replace(":", "--")
        .replace("_", "-")
        .replace("/", "-")
        .replace(" ", "-")
        .lower()
    )


def build(run: Run | None = None) -> dict:
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
        entries.append(entry(dataset))

    gates = [
        {
            "step": gate.step,
            "criterion": gate.criterion,
            "requirement": gate.requirement,
            "threshold": gate.threshold,
            "n_in": gate.n_in,
            "n_removed": gate.n_removed,
            "n_out": gate.n_out,
            "note": gate.note,
        }
        for gate in sorted(run.gates, key=lambda g: g.step)
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": provenance(run),
        # In reading order, not file order: this list is what the checks table and
        # the catalogue's row panel iterate, and the grid is laid out from
        # `audit.DISPLAY_CHECKS` in Python. One order for the ten checks
        # everywhere a reader meets them, whichever end renders them.
        "checks": [
            {"name": name, "kind": audit.check_kind(name)}
            for name in audit.DISPLAY_CHECKS
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
        "zenodo_record_id": recorded.get("zenodo_record_id"),
        "zenodo_concept_record_id": recorded.get("zenodo_concept_record_id"),
        "zenodo_record_version": recorded.get("zenodo_record_version"),
        "zenodo_record_registered": recorded.get("zenodo_record_registered"),
    }


def totals(run: Run) -> dict:
    """The corpus-level counts the pages quote, computed in one place.

    Every headline number comes from here, so no page can disagree with the
    catalogue and a re-pinned run changes every page at once.
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
    joint = sorted(d.joint.au_roc for d in datasets if d.joint is not None)
    clean_but_joint = [d for d in datasets if d.clean_but_joint]

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
        # The joint reading, over the datasets a joint model could be scored on.
        # `n_clean_but_joint` is the count this site exists to be able to state:
        # datasets on which no check returned Fail and the same features together
        # recovered the label anyway.
        "n_joint_scored": len(joint),
        "median_joint_auroc": _median(joint),
        "n_joint_over_0_8": sum(1 for value in joint if value >= 0.8),
        "n_joint_lower_bound": sum(
            1 for d in datasets if d.joint is not None and d.joint.lower_bound
        ),
        "n_clean_but_joint": len(clean_but_joint),
        "core_set_size": gates[-1].n_out if gates else 0,
        "n_gates": sum(1 for gate in gates if gate.criterion in audit.GATES),
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
