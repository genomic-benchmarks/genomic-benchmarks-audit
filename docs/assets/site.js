/* What every page shares: the helpers that render a measurement, and the panel
 * that shows one dataset's checks.
 *
 * The panel is here rather than in the catalogue's script because it renders in
 * more than one place, and two implementations of it would eventually say two
 * things about one dataset.
 *
 * Loaded by `templates/base.html` before the page's own script. Classic scripts,
 * not modules: two files in total, and a module graph would add a build step to
 * save nothing.
 *
 * Every word comes from `copy`, read out of the `#site-copy` block in the page.
 * `tools/vocab_check.py` scans `docs/` for prose and a `.js` file is not prose to
 * it, so a label written here would avoid the vocabulary check.
 */

const esc = (value) =>
  String(value).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const num = (value) => value.toLocaleString("en-GB");

const pct = (value) => `${value.toFixed(2)}%`;

/** Offer a line break after the separators in a long identifier.
 *
 * A dataset name is one unbroken token; `<wbr>` gives the line breaker somewhere
 * sensible to use, and the CSS keeps breaking anywhere as the last resort.
 */
const breakable = (value) => esc(value).replace(/([:_|])/g, "$1<wbr>");

/** How far this page sits below the site root, for links and for the fetch.
 *
 * A framed report is two directories down, and a leading slash would break the
 * site under a project page's `/repo/` prefix. `site.py` knows the depth and
 * writes it onto `<body>`.
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
 * `Unknown` ran and could not be scored; `null` had nothing to run on. Neither is
 * a Pass, and neither is the other.
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
 * Every figure was measured on the reference split, and the panel names it. The
 * checks are in the order the audit reports them rather than sorted by severity,
 * so two panels can be compared.
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

  return `<div class="panel" id="panel-${esc(d.slug)}">
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
        <p><a href="${datasetHref(d)}">${esc(copy.panel.open_dataset)}</a></p>
      </div>
    </div>
  </div>`;
}

/* --------------------------------------------------------------- chrome --- */

/* The theme, the back-to-top button and the copy-the-identifier button. All
 * three are enhancements: with scripting off the light theme applies, the button
 * stays hidden, and the identifier is still there to select by hand.
 */

const THEME_KEY = "gb-audit-theme";

/** The light/dark switch.
 *
 * The attribute is already on `<html>` -- the inline script in `base.html` put it
 * there before the first paint. This only moves it, records the choice, and keeps
 * the button's label describing what a click would do rather than what is
 * currently showing.
 */
function themeToggle(copy) {
  const button = document.getElementById("theme-toggle");
  if (button === null) return;

  const label = () => {
    const dark = document.documentElement.dataset.theme === "dark";
    const words = dark ? copy.chrome.to_light : copy.chrome.to_dark;
    button.setAttribute("aria-label", words);
    button.setAttribute("title", words);
  };

  button.addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    // A stored choice outranks the system preference, which is why the inline
    // script reads this key first.
    try { localStorage.setItem(THEME_KEY, dark ? "light" : "dark"); } catch (error) { /* private mode */ }
    label();
  });

  label();
}

/** Show the back-to-top button once there is something to go back up over. */
function backToTop(copy) {
  const button = document.getElementById("to-top");
  if (button === null) return;
  button.setAttribute("aria-label", copy.chrome.to_top);

  const update = () => button.classList.toggle("shown", window.scrollY > 600);
  window.addEventListener("scroll", update, { passive: true });
  update();
}

/** Put the text of the element a button names on the clipboard.
 *
 * `data-copy` holds the id of the element to read, so the string copied is the
 * string on the page rather than a second copy of it written into an attribute.
 */
function copyButtons(copy) {
  for (const button of document.querySelectorAll("[data-copy]")) {
    const source = document.getElementById(button.dataset.copy);
    if (source === null) continue;
    const original = button.textContent;
    button.addEventListener("click", () => {
      navigator.clipboard.writeText(source.textContent.trim()).then(() => {
        button.textContent = copy.chrome.copied;
        button.classList.add("copied");
        window.setTimeout(() => {
          button.textContent = original;
          button.classList.remove("copied");
        }, 1600);
      });
    });
  }
}

/* Every page loads this file, and every page has the masthead. The catalogue's
 * own script runs after it and does not repeat any of this. */
(function chrome() {
  const copy = readJson("site-copy");
  if (copy === null) return;
  themeToggle(copy);
  backToTop(copy);
  copyButtons(copy);
})();
