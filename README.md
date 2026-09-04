# genomic-benchmarks-audit

One pinned run of [`genomic-benchmarks-qc`][qc] over 93 genomic benchmark
datasets, rendered as a browsable site: what ten checks returned on each dataset,
how far a single sequence feature gets, which sequences appear in two splits, and
the 423 reports the tool wrote while measuring.

**The site is the deliverable and the numbers are the argument.** Every figure
opens a table of the same values underneath it, every figure names the split it
was measured on, and no page states a number that this repository did not compute
from a committed file.

[qc]: https://github.com/katarinagresova/genomic-benchmarks-qc

---

## What is here

| | |
|---|---|
| `data/` | The archived run: twelve CSVs and a digest for each. The only input. |
| `docs/data/catalogue.json` | Built from `data/`. Committed, gated in CI, fetched by the table. |
| `docs/templates/` | The pages, with `{{placeholders}}` where numbers go. |
| `docs/assets/` | One stylesheet, two classic scripts. No framework, no webfont request. |
| `docs/vendor/` | Tabulator 6.5.2, a file rather than a CDN call. |
| `src/gb_audit/` | The renderer: `audit`, `catalogue`, `charts`, `reports`, `site`, `zenodo`. |
| `tools/` | The vocabulary checker, and its rules. |
| `VOCABULARY.md` | How this project is allowed to describe what was measured. |

Not here, and deliberately: `site/`, which holds both the render and the 450 MB
of reports fetched into `site/qc-reports/`. Both are reproducible from what is
committed; neither is reviewed by being diffed.

## Building it

```sh
pip install -e '.[dev]'

gb-audit build      # data/*.csv        -> docs/data/catalogue.json
gb-audit fetch      # Zenodo or mirror  -> site/qc-reports/
gb-audit render     # the above         -> site/
gb-audit render --fetch --serve
```

`build` and `render` need no network. `fetch` is the only step that does, and the
site renders without it — every report page has an honest state for "not in this
build" rather than a link that 404s.

`fetch` downloads into the site directory the render serves from, and `render`
leaves that directory alone. So there is one copy of those 450 MB on disk, at the
address the pages already link to, and it is fetched once and rendered around
many times.

`gb-audit check` is what CI runs: it rebuilds the catalogue in memory, compares it
to the committed file, and renders the whole site to a temporary directory,
writing nothing into the checkout.

## The reports

`genomic-benchmarks-qc` writes a self-contained HTML report for every unit it
measures — one per split per sequence column for the nine class-distribution
checks, one per split pair for the leakage scan. There are 423, and they are
published on Zenodo rather than committed: 90 MB of archives that unpack to about
450 MB.

`data/reports.csv` is the manifest — name, size, SHA-256 and every path inside
each archive — so the site knows exactly what exists before anything is
downloaded, and `gb-audit fetch` verifies each archive against its digest before
unpacking it. On the site each report is framed inside the site's own navigation,
rendered exactly as the tool wrote it, with the raw file one click away.

Whether a report can be opened is resolved while rendering, from the directory
being rendered into. The committed catalogue does not record it: that would be a
file recording whoever last ran the build, and CI — which fetches nothing — would
disagree with a laptop about the same commit.

### Reaching the record

The record is **staged but not published**. Three routes, and whichever one a
fetch takes is recorded in `site/qc-reports/PROVENANCE.json` and printed on the
reports page, because bytes from a draft or from a local checkout are not bytes a
reader can go and get for themselves:

```sh
# the published record, once it is published
gb-audit fetch

# the draft, with the record's share token
GENOMIC_BENCHMARKS_ZENODO_TOKEN=... gb-audit fetch

# a GenBench2_paper checkout, serving the same run from disk
GENOMIC_BENCHMARKS_LOCAL_MIRROR=/path/to/GenBench2_paper gb-audit fetch
```

The token is read from the environment and never written into this repository: a
share token in a public repository is a published token.

## What the site does not claim

A flag is the output of one check on one split. `Pass` is the narrowest of the
four: this check did not separate the classes. It certifies nothing about the
data, and no combination of the ten flags does either.

`Unknown` means a check ran and could not be scored. A blank means it had nothing
to run on. Neither is a `Pass`, and the figures keep all three apart — `Unknown`
is drawn as a hatch rather than a fourth colour, and a blank is drawn as nothing.

Every separability number is a **lower bound** on what a model could recover.

`VOCABULARY.md` states the rest, and `tools/vocab_check.py` enforces the
machine-checkable part of it over every page in `docs/`.

## Conventions worth knowing before changing anything

- **No number in the copy is typed.** Templates carry `{{placeholders}}`;
  `site.counts()` computes what goes in them. `fill()` raises on a placeholder it
  has no value for, so a misspelling fails the build rather than publishing
  `{{n_fail}}` to a reader.
- **No word in the copy lives in a script.** Everything the renderer and the
  browser scripts print comes from the `#site-copy` block in
  `docs/templates/base.html`, because `vocab_check.py` reads `.html` and does not
  read `.js` or `.py`.
- **No timestamps anywhere.** Two builds of one commit produce the same bytes;
  SVG element ids come from `zlib.crc32`, not `hash()`, which is salted per
  process.
- **The standard library, and nothing else.** See `pyproject.toml` for why.

## Tests

```sh
python -m pytest tests/ tools/
python tools/vocab_check.py --strict
```

The suite checks the things that would be silent if they broke: that the
committed catalogue is what the tables produce, that every rollup figure comes
from the reference split rather than from a maximum over splits, that no
placeholder or share token survives into a page, that every internal link
resolves, that an archive failing its digest is not unpacked, and that the flag
palette stays distinguishable under all three simulated colour vision
deficiencies.
