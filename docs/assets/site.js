/* What every page on this site shares: the helpers that render a measurement,
 * and the panel that shows one dataset's checks.
 *
 * The panel is here rather than in the catalogue's script because it renders in
 * two places -- the expanded body of a catalogue row, and anywhere else a
 * dataset needs summarising -- and a panel rendered by two implementations is a
 * panel that will eventually say two things about one dataset.
 *
 * Loaded by `templates/base.html` before the page's own script, so the page
 * script can call these directly. Classic scripts, not modules: `Tabulator` is a
 * global from the vendored library, the site has two scripts in total, and a
 * module graph would add a build step to save nothing.
 *
 * Every word rendered from here comes from `copy`, read out of the `#site-copy`
 * block in the page. `tools/vocab_check.py` scans `docs/` for prose and a `.js`
 * file is not prose to it, so a label written here would be the one piece of
 * site copy that could avoid the vocabulary check.
 */

const esc = (value) =>
  String(value).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const num = (value) => value.toLocaleString("en-GB");

const pct = (value) => `${value.toFixed(2)}%`;

/** Offer a line break after the separators in a long identifier.
 *
 * A dataset name is one unbroken token, so a narrow column either truncates it
 * or breaks it mid-word. `<wbr>` gives the line breaker somewhere sensible to do
 * it, and the CSS keeps breaking anywhere as the last resort.
 */
const breakable = (value) => esc(value).replace(/([:_|])/g, "$1<wbr>");

/** How far this page sits below the site root, for links and for the fetch.
 *
 * The catalogue is at the root and a framed report is two directories down, so
 * neither a bare relative path nor a leading slash works for both -- a leading
 * slash would also break the whole site under a project page's `/repo/` prefix.
 * `site.py` knows the depth and writes it onto `<body>`.
 */
const siteRoot = () => document.body.dataset.root ?? "";

/** The words this page renders, and any JSON block a page carries for itself. */
const readJson = (id) => {
  const holder = document.getElementById(id);
  return holder === null ? null : JSON.parse(holder.textContent);
};

const loadCatalogue = () => fetch(`${siteRoot()}data/catalogue.json`).then((r) => r.json());

/** Where one dataset's page lives. The slug is in the catalogue, not derived
 * here: `site.py` writes the file from that same field and refuses a slug that
 * would collide, so deriving it twice is two chances to disagree. */
const datasetHref = (d) => `${siteRoot()}datasets/${encodeURIComponent(d.slug)}.html`;

/** One flag as a chip, with the three absences kept apart.
 *
 * `Unknown` is a check that ran and could not be scored. A `null` is a check
 * that had nothing to run on. Neither is a Pass, and rendering either as one --
 * or as each other -- turns an absence of measurement into a result.
 */
function flagSpan(flag, copy) {
  if (flag === null || flag === undefined) {
    return `<span class="flag flag-blank" title="${esc(copy.flag_help.blank)}">&mdash;</span>`;
  }
  return `<span class="flag flag-${esc(flag)}" title="${esc(copy.flag_help[flag])}">${esc(copy.flags[flag])}</span>`;
}

/** A measured figure, or the word for its absence -- never a stand-in zero. */
function measured(value, format, copy) {
  if (value === null || value === undefined) {
    return `<span class="absent" title="${esc(copy.flag_help.blank)}">&mdash;</span>`;
  }
  return format(value);
}

/* ---------------------------------------------------------------- panel --- */

/** One dataset's checks, probe and split overlaps, as the body of a table row.
 *
 * Every figure in here was measured on the dataset's reference split, and the
 * panel says which split that was rather than leaving a reader to assume. The
 * checks are listed in the order the audit reports them, not sorted by
 * severity: a stable order is what lets a reader compare two panels.
 */
function panelHtml(d, copy, checks) {
  const probe = d.strongest_probe && d.max_probe_auroc !== null
    ? `<p class="headline"><b>${esc(d.strongest_probe)}</b> ${esc(copy.panel.probe_lead)}
       <b>${d.max_probe_auroc.toFixed(3)}</b> ${esc(copy.panel.probe_tail)}</p>`
    : `<p class="headline">${esc(copy.panel.no_probe)}</p>`;

  const caveat = `<p class="caveat">${esc(copy.panel.probe_bound)}</p>`;

  // Which two splits the overlap figure is about, named rather than assumed.
  // The query side is `val` rather than `test` on a quarter of the corpus, so a
  // panel that said "the test split" would describe the wrong split there.
  let leakage;
  if (d.leakage.length === 0) {
    leakage = `<p>${esc(copy.panel.leakage_absent)}</p>`;
  } else if (!d.max_leaked_test_pct) {
    leakage = `<p>${esc(copy.panel.leakage_none)}</p>`;
  } else {
    const worst = d.leakage.reduce((a, b) =>
      (b.leaked_queries_pct ?? 0) > (a.leaked_queries_pct ?? 0) ? b : a);
    const some = copy.panel.leakage_some
      .replace("{query}", `<code>${esc(worst.query_split)}</code>`)
      .replace("{target}", `<code>${esc(worst.target_split)}</code>`);
    const scope = copy.panel.leakage_scope.replace("{n}", String(d.leakage.length));
    leakage = `<p><b>${pct(worst.leaked_queries_pct)}</b> ${some}</p>
               <p class="note">${esc(scope)}</p>`;
  }

  const rows = checks.map((check) => {
    const flag = d.flags[check.name] ?? null;
    return `<tr><td>${esc(check.name)}</td>
            <td class="kind">${esc(copy.kinds[check.kind])}</td>
            <td class="right">${flagSpan(flag, copy)}</td></tr>`;
  }).join("");

  const splits = d.splits.map((s) => {
    const mark = s.is_reference
      ? ` <span class="ref-mark">${esc(copy.panel.reference)}</span>`
      : "";
    return `<li><code>${esc(s.split)}</code>${mark} ${flagSpan(s.rollup.flag, copy)}</li>`;
  }).join("");

  const reference = `<p class="caveat">${esc(copy.panel.reference_lead)}
    <code>${esc(d.reference_split ?? "")}</code> ${esc(copy.panel.reference_tail)}</p>`;

  return `<div class="panel">
    ${probe}${caveat}${reference}
    <div class="panel-grid">
      <div>
        <h3>${esc(copy.panel.checks_heading)}</h3>
        <table>${rows}</table>
      </div>
      <div>
        <h3>${esc(copy.panel.splits_heading)}</h3>
        <ul class="shares">${splits}</ul>
      </div>
      <div>
        <h3>${esc(copy.panel.leakage_heading)}</h3>
        ${leakage}
        <p><a href="${datasetHref(d)}">Open this dataset&rsquo;s page</a></p>
      </div>
    </div>
  </div>`;
}
