<!-- The generic Genomic Benchmarks wordmark, to be replaced by an audit-specific
     one. Referenced by raw URL rather than a relative path so it also renders
     where the file is not checked out beside the README; it resolves once the
     repository is public. -->
<img src="https://github.com/genomic-benchmarks/genomic-benchmarks-audit/blob/main/assets/genomic-benchmarks-text.png?raw=True" alt="Genomic Benchmarks logo" width="500" />

[![CI](https://github.com/genomic-benchmarks/genomic-benchmarks-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/genomic-benchmarks/genomic-benchmarks-audit/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Site](https://img.shields.io/badge/site-genomic--benchmarks.github.io-1f6fd0)](https://genomic-benchmarks.github.io/genomic-benchmarks-audit/)

### Read the benchmark before you beat it.

[`genomic-benchmarks-qc`][qc] measured **93 genomic benchmark datasets** from seven
collections — 234 splits, 19 species — and wrote 423 reports doing it. This
repository is that one pinned run, rendered as a site you can browse dataset by
dataset: what ten checks returned on each one, how far a single sequence feature
gets, which sequences appear in two splits, and every report the tool produced.

**→ [Open the site](https://genomic-benchmarks.github.io/genomic-benchmarks-audit/).**
A README has no room for what it holds: a sortable [catalogue](https://genomic-benchmarks.github.io/genomic-benchmarks-audit/catalogue.html)
of all 93, a page per dataset with its ten flags and its probe curve, [each check](https://genomic-benchmarks.github.io/genomic-benchmarks-audit/checks.html)
taken in turn across the corpus, and the 423 reports themselves, framed and
readable.

If you are about to train on one of these datasets, its page is the thing to read
first — not because a flag disqualifies it, but because the number a new method is
compared against is on that page.

[qc]: https://github.com/genomic-benchmarks/genomic-benchmarks-qc

## What the run found

Every number below is measured on each dataset's **reference split**, and every
one of them is computed from a committed file in [`data/`](data/README.md):

- **Most of the corpus is flagged somewhere.** **57 of the 93** datasets returned
  `Fail` on at least one of the ten checks. Another 31 had `Warning` as their worst
  flag. **Five** returned `Pass` on all ten.
- **One hand-crafted feature already gets a long way.** The strongest single
  sequence feature reaches a median **AUROC 0.666**, and **34 datasets reach 0.700
  or more** from one feature alone —
  [`nucleotide_benchmarks:promoter_no_tata`](https://genomic-benchmarks.github.io/genomic-benchmarks-audit/datasets/nucleotide-benchmarks--promoter-no-tata.html)
  reaches **0.900** from per-sequence GC content by itself. That is the number a
  model is actually being compared against, and it is a lower bound.
- **The usual winner is dinucleotide composition.** On **50 of 93** datasets the
  strongest of the six probes is per-sequence dinucleotide content. Sequence
  length — the one everybody checks — wins on four.
- **Sequences turn up in more than one split.** **75 of the 92** scanned datasets
  share at least one sequence between two splits. Six have more than half of one
  split present in another, and **five have all of it**.
- **Ten datasets clear every gate.** Of 147 curated datasets, 93 could be measured
  — 54 were excluded, for 14 reasons the site
  [lists](https://genomic-benchmarks.github.io/genomic-benchmarks-audit/catalogue.html)
  rather than summarises — and ten clear all five
  [Core Set](https://genomic-benchmarks.github.io/genomic-benchmarks-audit/core-set.html)
  gates.

## What the site does not claim

This is the part worth reading before quoting any of the above.

A flag is the output of one check on one split. `Pass` is the narrowest of the
four: this check did not separate the classes. It certifies nothing about the
data, and no combination of the ten flags does either.

`Unknown` means a check ran and could not be scored. A blank means it had nothing
to run on. Neither is a `Pass`, and the figures keep all three apart — `Unknown`
is drawn as a hatch rather than a fourth colour, and a blank is drawn as nothing.

Every separability number is a **lower bound** on what a model could recover.

[`tools/vocabulary.toml`](tools/vocabulary.toml) states the rest, and
[`tools/vocab_check.py`](tools/vocab_check.py) enforces it over every page —
including this one.

## Where the numbers come from

**The site is the deliverable and the numbers are the argument.** Every figure
opens a table of the same values underneath it, every figure names the split it
was measured on, and no page states a number that this repository did not compute
from a committed file.

| | |
|---|---|
| [`data/`](data/README.md) | The archived run: twelve CSVs and a digest for each. The only input. |
| `docs/data/catalogue.json` | Built from `data/`. Committed, gated in CI, fetched by the table. |
| `docs/templates/` | The pages, with `{{placeholders}}` where numbers go. |
| `docs/assets/` | One stylesheet, two classic scripts. No framework, no webfont request. |
| `docs/vendor/` | Tabulator 6.5.2, a file rather than a CDN call. |
| `src/gb_audit/` | The renderer: `audit`, `catalogue`, `charts`, `reports`, `site`, `zenodo`. |
| [`tools/vocabulary.toml`](tools/vocabulary.toml) | How this project is allowed to describe what was measured. |

Not here, and deliberately: `site/`, which holds both the render and the 450 MB of
reports fetched into `site/qc-reports/`. Both are reproducible from what is
committed; neither is reviewed by being diffed.

## Citation

The instrument, the corpus, this audit and the leaderboard are described in one
manuscript, **in preparation**:

> **Automated quality control for genomic sequence benchmarks
> reveals pervasive single-feature separability and train–test leakage.**
> In preparation.

Until it has a DOI, the four repositories stand on their own:

| | |
|---|---|
| [`genomic-benchmarks-qc`](https://github.com/genomic-benchmarks/genomic-benchmarks-qc) | The instrument: ten checks, their thresholds and flags, the report renderer |
| `genomic-benchmarks-data` | The corpus: datasets, splits, sequence IDs, versions and ground truth |
| `genomic-benchmarks-audit` | Here: one pinned run of the instrument over all 93 datasets, with browsable reports |
| `genomic-benchmarks-leaderboard` | Submissions, scoring, published results — each table headed by what this audit measured |

<!-- TODO: replace the manuscript entry with its DOI and BibTeX on publication,
     and add a CITATION.cff. Held until there is a DOI to point at -- a citation
     block that resolves to nothing is worse than the repository URL it
     replaced. -->

## Contributions & Support

Corrections to a number, and questions about how one was measured, are both
welcome — open an
[issue](https://github.com/genomic-benchmarks/genomic-benchmarks-audit/issues/new).
A number on this site is wrong in exactly one way that matters: if it disagrees
with the tables under `data/`, which is what CI checks on every commit.

## License

MIT — see [LICENSE](LICENSE).
