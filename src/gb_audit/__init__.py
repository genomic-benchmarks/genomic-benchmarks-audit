"""One pinned run of `genomic-benchmarks-qc` over the corpus, rendered as a site.

Four repositories, and the boundary between them is what event makes each one
change. A check changes -> `genomic-benchmarks-qc`. A dataset changes ->
`genomic-benchmarks-data`. Someone submits -> `genomic-benchmarks-leaderboard`.
The audit is re-run -> here.

    gb-audit build      # data/ -> docs/data/catalogue.json
    gb-audit render     # docs/ -> site/
    gb-audit fetch      # the report archives, from Zenodo or a local mirror
    gb-audit check      # every generated file is what its inputs build

What this package holds is a measurement, not a corpus and not a score. It reads
one directory -- `data/`, the archived run -- and writes two things: a JSON
document the pages read, and the pages. It imports nothing outside the standard
library and reaches the network from exactly one module, `zenodo`, which is never
on the path that renders a page.

It does **not** depend on `genomic-benchmarks-data`. That is deliberate rather than
incidental: an audit is a statement about a corpus at a moment, and a build that
resolved the corpus live would quietly re-describe an archived run every time the
package moved. The facets, the split names and the sequence columns on these pages
all come from the run's own output.

`VOCABULARY.md` governs every word the site renders, and the constraint that binds
hardest is the symmetric one: a `Pass` establishes only that these ten checks do
not separate the classes, so every separability number here is a lower bound on
what a learned model could recover.
"""

# Recorded in `docs/data/catalogue.json` beside the run labels, so a page can say
# which renderer produced it. A bump is visible in that file's diff.
__version__ = "0.1.0"
