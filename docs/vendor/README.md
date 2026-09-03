# Vendored

## Tabulator 6.5.2

`tabulator.min.js`, `tabulator.min.css` and its MIT `LICENSE`, copied into this
repository rather than loaded from a CDN.

**Why the file and not the link.** A CDN tag makes rendering this site a
request to a third party at the moment a reader opens it, and this site is an
archive of one measurement run that has to still work years after the run. A
version that silently moves, an integrity hash that stops matching, or a CDN that
stops answering are three ways for an archived page to stop rendering for reasons
that have nothing to do with what it archives. There is also nothing to be gained
in exchange: the site loads two scripts in total.

**Why this version.** 6.5.2 is the last release before the 6.x layout changes,
and the CSS in `docs/assets/site.css` corrects it in a few places. Those
corrections are order-dependent, which is why `base.html` loads a page's own
stylesheet *above* `site.css` and never below it.

**What the site does not use it for.** Sorting a column of measurements. The
table supplies its own sorters, in `docs/assets/catalogue.js`, because
Tabulator's numeric sorter files a `null` with the zeros — and a `null` in this
table means the check had nothing to run on. The default would put every
unmeasured dataset among the lowest-scoring ones and make an absence of
measurement read as a reassuring result. The supplied sorters send missing values
to the end in both directions, which is the only ordering that states nothing.

**Upgrading.** Replace the directory, rename it after the new version, update the
two `<link>`/`<script>` paths in `gb_audit/site.py`, and re-run
`python -m pytest tests/`. This README is not copied into the built site;
`site.build()` deletes it from the output, because it is notes for a maintainer
rather than a page.
