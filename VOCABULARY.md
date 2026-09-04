# Vocabulary

How this project describes what `genomic-benchmarks-qc` measured. In this
repository it binds every page of the audit site — the overview, the dataset
pages, the checks and Core Set pages, the methods page and the framed report
viewers — along with the templates they are rendered from, the copy block in
`docs/templates/base.html`, and this repository's own README and docs.
`CONTRACT.md` §9 states the obligation; this file is how you meet it.

**What it does not bind.** The 423 reports under `site/qc-reports/` are written
by `genomic-benchmarks-qc`, not by this repository, and the site publishes them
unchanged. Rewording a tool's output to satisfy a convention would make the copy
of a report on this site say something the report does not. `tools/vocabulary.toml`
excludes them for exactly that reason.

**Source of truth.** The convention was agreed for the manuscript on 2026-08-11
and lives in `Manuscript_vocabulary.md` in the `GenBench2_paper` repository.
This file is its site-facing subset — the rules, without the running record of
which manuscript section was brought into line on which date. A change to a
shared rule belongs in both. A rule that only ever applies to a web page can
live only here.

The site matters more than it looks. It is about to become the most-read
surface describing QC output, and if it and the paper describe the same flag
differently, the site is the one that gets quoted.

---

## The core principle

**Claim what was measured, not what caused it.**

A probe measures that a class label is recoverable from one simple sequence
feature. It does *not* establish that the dataset is defective — a
compositional difference between classes may be genuine biology. The claim we
are entitled to make is about what a benchmark score can be interpreted as, and
it is *stronger* than the claim we are not entitled to make.

### The shape that always holds

> L% of labels are recoverable from feature F alone; a score on this benchmark
> therefore cannot distinguish a model that has learned biology from one that
> computes F.

This survives the obvious objection. Promoters genuinely are GC-rich — calling
a promoter benchmark `biased` because GC separates its classes invites *that's
real biology* and loses the argument. The separability is real, its origin is
undetermined, and either way the benchmark cannot measure what it claims.

---

## Three tiers of finding

**Tier 1 — assert plainly, no hedge.** No biological reading is possible:
train–test leakage (`Split leakage`), duplicate sequences across classes
(`Duplicate Sequences between Labels`), shared-alphabet violation
(`Unique bases`). Permitted here: *defect*, *error*, *contamination*,
*label noise*, *must be fixed*.

**Tier 2 — a dataset property, no causal claim.** Duplicate sequences within a
class (`Sequence Duplications within Labels`) is *redundancy* or *duplication*;
it inflates effective sample size. Not an error unqualified.

**Tier 3 — report the measurement, hedge the cause.** The six probes — sequence
length, GC content, nucleotide content, dinucleotide content, per-position 5′,
per-position 3′. Report the number; do not assert its origin.

---

## Canonical terms

- **separability** — the measured quantity: how well one hand-crafted feature
  recovers the class label. "Separable at AUROC 0.90 by GC content alone."
  Qualify as *compositional*, *positional* or *single-feature*.
- **probe** — one hand-crafted feature used as a single-feature classifier.
- **check** — one of the ten tests. Six **probe checks** and three **integrity
  checks** together make the nine **class-distribution checks** run by
  `evaluate-classes`; the tenth is the **leakage scan** run by
  `evaluate-splits`. Say "integrity checks", not "structural checks".
- **flag** — the tool's output. `Pass` / `Warning` / `Fail` / `Unknown`,
  capitalised, always the tool's flag and never a judgement about the dataset.
  "Flagged `Fail` on dinucleotide content", not `failed the dinucleotide check`.
- **leakage** / **train–test leakage** — Tier 1; assert freely.
- **exploitable** — safe modifier: it claims a model *can use* the signal, not
  that the signal is artefactual.
- **regularity** — neutral noun for the pattern itself.
- **Core Set** — the subset of the audited corpus that no check flagged `Fail`,
  chosen to span the corpus. Name the criterion, and let the name state only
  the set's role.
- **AUROC** — one word, no hyphen.
- **`genomic-benchmarks-qc`** — the tool's only name.

---

## Restricted words

| Avoid unqualified | Use instead |
|---|---|
| `bias` | separability — `exploitable bias` is fine where exploitability is the point, and the statistical sense (an estimator `biased` upward) is a different word |
| `shortcut` | separability — reserve `shortcut learning` for prior work about **models**, and for generated data where the alternative route was deliberately constructed |
| `trivial` / `trivially separable` | separable from a single feature |
| `artefact` | only with evidence of the construction step that produced it |
| `problem` / `flaw` / `broken` | flagged, or name the check |
| `verdict` (on a dataset) | the worst flag received across the ten checks |
| `the dataset failed X` | the dataset was flagged `Fail` on X |
| `spurious correlation` | avoid entirely |
| `is the signature of` | is consistent with |
| `is caused by` / `is the consequence of` | would be expected if — **unless** the construction step is documented, in which case assert it |
| `golden set` / `gold standard` / `high-quality` | Core Set, and name the criterion |
| `the splits we drew` / `our splits` | splits generated from the collection's own splitting function — see below |

`overall_verdict` keeps its name: it is a column in an archived table, an
identifier rather than prose. The checker does not read code spans, so
identifiers never trip a rule.

---

## `Pass` never licenses `clean`

The convention says a great deal about not over-reading `Fail` and had to be
made symmetric. A `Fail` establishes that a simple rule suffices. A `Pass`
establishes only that these ten checks do not separate the classes.

So every separability number is a **lower bound** on what a learned model could
recover, and a dataset that passes every check is unscreened with respect to
everything the checks do not measure. This is the reasoning the Core Set's name
already rests on, and it is why every figure on this site ships a table of the
same numbers underneath it and names the split it measured them on: a result is
read against what the checks found *and* against what they cannot see.

The constraint is measured, not hypothetical: the ten Core Set datasets are
separable at a median AUROC of 0.740 by the same ten checks read jointly, and
`splice_sites_donors` reaches 0.997.

---

## Split provenance: mRNABench

One collection releases a splitting **function** instead of fixed partition
files. Its splits were materialised by calling `mrna_bench`'s `get_splits` at
the package's own defaults — `split_ratios=(0.7, 0.15, 0.15)`,
`random_seed=2541` — with the per-dataset `split_type` its own catalogue
records. Every argument is the collection's.

- **Say** "the collection defines its splits by code rather than by file",
  "splits generated from the package's own splitting function", "the split a
  user of that package gets".
- **Never say** `the splits we drew`, `splits drawn here`, or `our splits`. It
  is a factual error, and it hands a reader a weakness this project does not
  have: those datasets leak because of the collection's own default splitting
  rule, and that is the finding.
- Where the six `mrl-sample-*` datasets leak 82–100%, attribute it to the
  collection's default random split applied to a massively parallel reporter
  library.
- **The one caveat that is ours is the seed.** The partition is a single
  realisation of a seeded draw. Removing the collection outright leaves
  leakage prevalence at 81.5% and *raises* median separability, so no headline
  rests on it.

---

## Running the check

```
tools/vocab_check.py              # the paths configured in tools/vocabulary.toml
tools/vocab_check.py docs/        # anything specific
tools/vocab_check.py --strict     # warnings fail too
tools/vocab_check.py --list-rules
```

Twelve rules are literal string matches and are **errors** — they are wrong in
every sentence a page could write. Seven are **warnings**, because whether
`bias` or `clean` is acceptable depends on the sentence and only a person can
say. Run it locally before publishing copy; there is no CI for it, because
the checker is not part of the published repository.

Only prose is scanned. Fenced blocks, code spans, link targets and URLs are
blanked before matching.

**Allowing a word to stand.** An HTML comment carrying a reason:

```
<!-- vocab-ok: shortcut # citing Geirhos et al. 2020, prior work about models -->
```

Alone on its line it governs the next line; trailing on a line of prose it
governs that line. **One line, not the paragraph** — in hard-wrapped prose the
word is often not on the line you would naturally end the comment on, so put
the comment on the line the word is on. The reason is required. A suppression that stops matching
anything is reported, so the allowlist cannot quietly outlive the sentence that
needed it — which is the failure mode of every word list that came before it.

**Adding a rule** means adding a `[[rule]]` block to `tools/vocabulary.toml`
and, if it is a shared rule rather than a site-only one, the same row to
`Manuscript_vocabulary.md`. A rule that fires on prose the convention permits
is a bug in the rule, not in the prose: narrow the pattern, or move it to
`warn`.

The same checker runs over the manuscript:

```
tools/vocab_check.py ../GenBench2_paper/manuscript/
```
