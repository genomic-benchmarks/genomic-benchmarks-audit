# The archived run

Thirteen CSVs and a `provenance.json`. This is the only input the site has: every
number on every page is computed from these files, and nothing here is written by
hand.

They come from three pipelines, not one, and the chain runs one way: `dataset_qc`
measures, `dataset_audit` rolls up, and `core_set` applies the criteria over that
rollup plus a joint model of the same features. `provenance.json` names all three
runs, because a page quoting a Core Set figure and a page quoting a flag are
quoting two different pieces of work.

## Why these are committed and the reports are not

They are small — 340 KB in total, against 90 MB of report archives — and they are
the files a change to a published number shows up in. A diff of
`dataset_level_summary.csv` is a reviewable statement that a flag moved. A diff of
423 rendered HTML documents is not.

Two of them, `combined_classes_results.csv` and `combined_splits_results.csv`, are
**also** on the Zenodo record. That is deliberate duplication, and
`provenance.json` is what makes it checkable rather than merely hopeful: it
records a SHA-256 per file, and both committed copies are byte-identical to the
record's. A copy nothing can be compared against is a copy that has already
drifted.

The third combined table is not here and not going to be.
`combined_classes_results_full.csv` is 343 MB and 2.59 M rows — every
individually scored feature, including every position. It lives on the record
alone, and `gb_audit/zenodo.py` is where its name is written down.

## The files

| File | What it holds |
|---|---|
| `dataset_level_summary.csv` | One row per dataset: the rollup on its reference split. |
| `splits.csv` | One row per split: its flags, its strongest probe. |
| `combined_classes_results.csv` | The class-distribution checks, per split and feature. |
| `combined_splits_results.csv` | The leakage scan, per split pair and direction. |
| `reports.csv` | The manifest of the 93 archives: size, digest, every path inside. |
| `core_set.csv` | The 10 members and their rank. |
| `core_set_candidates.csv` | One row per dataset the selection considered, all 93: whether it met each criterion, the first one it broke, and what the checks' features recover jointly. |
| `core_set_criteria.csv` | The funnel, in the order applied. |
| `core_set_selection_trace.csv` | What the selection picked at each step, and why. |
| `exclusion_summary.csv` | Why 54 curated datasets were not measured. |
| `summary_by_check.csv` | Per-check tallies, over the 92 evaluable datasets. |
| `summary_by_collection.csv` | Per-collection tallies. |
| `summary_by_task_category.csv` | Per-category tallies. |

A note on `summary_by_check.csv`: it counts 92, not 93 — it excludes the one
dataset whose reference split is `test`. The site's own per-check figures are
computed from all 93 datasets' flags instead, so that the checks page and the
dataset pages agree with each other, and the leakage row is shown as 92 scored
plus one blank rather than as a smaller denominator nothing on the page explains.

## The one number here the audit did not compute

`core_set_candidates.csv` carries `joint_auroc`: what a model given all of the ten
checks' features at once reaches on a held-out split. It is the only column in
this directory produced outside the audit, and the reason the Core Set is its own
pipeline rather than a stage of the audit — the criterion reads a score the audit
cannot compute, and a selection made inside the audit would put the two pipelines
each behind the other.

Three of its columns travel together and must not be separated:
`joint_auroc_is_lower_bound`, `joint_auroc_caveat` and the value itself. Where the
position window was capped or the training pool subsampled the figure can only be
too low, and for a criterion that admits a dataset for sitting *under* a ceiling
that is the direction that matters. The site prints a `≥` beside every one of
them.

## Regenerating

`scripts/regenerate_audit_data.py` copies these out of a `GenBench2_paper`
checkout and rewrites `provenance.json`. It is the only thing that should write
into this directory. Re-running it against a different QC run is a new audit run,
not an edit to this one: the run labels in `provenance.json` are what a reader
uses to find these numbers again.
