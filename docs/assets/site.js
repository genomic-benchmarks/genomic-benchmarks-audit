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

/* The one check that is not about a single split. It runs on a pair of them, and
 * in the panel it is the whole of the right-hand column rather than a row in the
 * left-hand one. Matched on by kind, the way `site.py` counts the other nine, so
 * a check added to either side lands in the right column without being told. */
const LEAKAGE_KIND = "leakage scan";

/** One dataset's checks and split overlaps, as the body of a table row.
 *
 * Two columns, because the ten checks ask two questions. Nine run on one split
 * and ask whether the classes inside it can be told apart; the tenth runs on a
 * pair of splits and asks whether they share sequences. A check answers one or
 * the other and never both, so the kind stopped being a word repeated down a
 * column -- nine rows saying "probe" or "integrity" beside the name that already
 * implies it -- and became the section the check sits in.
 *
 * Every figure on the left was measured on the reference split, and the panel
 * names it above the grid. The checks are in the order the audit reports them
 * rather than sorted by severity, so two panels can be compared.
 */
function panelHtml(d, copy, checks) {
  const probe = d.strongest_probe && d.max_probe_auroc !== null
    ? `<p class="headline"><b>${esc(d.strongest_probe)}</b> ${esc(copy.panel.probe_lead)}
       <b>${d.max_probe_auroc.toFixed(3)}</b> ${esc(copy.panel.probe_tail)}</p>`
    : `<p class="headline">${esc(copy.panel.no_probe)}</p>`;

  const caveat = `<p class="caveat">${esc(copy.panel.probe_bound)}</p>`;

  const reference = `<p class="caveat">${esc(copy.panel.reference_lead)}
    <code>${esc(d.reference_split ?? "")}</code> ${esc(copy.panel.reference_tail)}</p>`;

  /* --------------------------------------------------- the per-split checks --- */

  /* One section per kind, in the order the audit reports them. Which kinds there
   * are is read off the checks rather than written here, so a seventh probe or a
   * fourth integrity check needs nothing from this file.
   *
   * Which section gets the AUROC column is asked of the data too. A probe is the
   * check that answers "how far does one feature get" as a number, and
   * `probe_auroc` is where those numbers are, so a section has the column when
   * its checks are in there. The others leave the cell empty rather than filling
   * it with an em-dash: that mark is this site's word for a measurement that was
   * not made, and an integrity check has no AUROC to have failed to report.
   */
  const auroc = d.probe_auroc ?? {};
  const kinds = [];
  for (const check of checks) {
    if (check.kind === LEAKAGE_KIND) continue;
    if (!kinds.includes(check.kind)) kinds.push(check.kind);
  }

  const sections = kinds.map((kind) => {
    const members = checks.filter((check) => check.kind === kind);
    const scored = members.some((check) => check.name in auroc);
    const heading = copy.panel.sections[kind] ?? copy.kinds[kind] ?? kind;
    // The section heading doubles as the header row, so the one column that
    // needs naming gets a name without a header band over two that do not: a
    // check is named by its own row and a flag chip carries its own word.
    const head = scored
      ? `<th class="right" scope="col">${esc(copy.panel.auroc)}</th><td></td>`
      : `<td colspan="2"></td>`;
    const rows = members.map((check) => {
      const cell = scored
        ? `<td class="right num">${measured(auroc[check.name] ?? null, (v) => v.toFixed(3), copy)}</td>`
        : "<td></td>";
      return `<tr><td>${esc(check.name)}</td>${cell}` +
        `<td class="right">${flagSpan(d.flags[check.name] ?? null, copy)}</td></tr>`;
    }).join("");
    return `<tbody><tr class="group-head">` +
      `<th scope="colgroup">${esc(heading)}</th>${head}</tr>${rows}</tbody>`;
  }).join("");

  /* ------------------------------------------------------ the split overlaps --- */

  const splits = d.splits.map((s) => {
    const mark = s.is_reference
      ? ` <span class="ref-mark">${esc(copy.panel.reference)}</span>`
      : "";
    return `<li><code>${esc(s.split)}</code>${mark} ${flagSpan(s.rollup.flag, copy)}</li>`;
  }).join("");

  /* Every comparison the scan made, and both directions of each one.
   *
   * This used to be the largest overlap and a note saying how many comparisons
   * there were, which is a sentence that tells a reader a number exists and then
   * declines to show it -- and on the 49 datasets with two comparisons it also
   * left the other one unnamed. Two is the most any dataset here has, and each is
   * two figures, so all of them fit.
   *
   * Both ways round because they are two facts, not one stated twice. The share
   * of the held-out split found in train says how much of what a model is scored
   * on it has already seen; the share of train found in the held-out split says
   * how much of what it was trained on is being scored again. A small split
   * inside a large one makes the first large and the second small.
   *
   * Which two splits, named rather than assumed: the query side is `val` rather
   * than `test` on a quarter of the corpus.
   */
  const share = (value, from, to) =>
    `<li>${measured(value, (v) => `<b>${pct(v)}</b>`, copy)} ` +
    copy.panel.pair_share
      .replace("{from}", `<code>${esc(from)}</code>`)
      .replace("{to}", `<code>${esc(to)}</code>`) +
    `</li>`;

  const pairs = d.leakage.length === 0
    ? `<p class="note">${esc(copy.panel.leakage_absent)}</p>`
    : `<ul class="pairs">${d.leakage.map((pair) =>
        `<li><div class="pair-head">` +
        `<span><code>${esc(pair.target_split)}</code> ${esc(copy.panel.pair_vs)} ` +
        `<code>${esc(pair.query_split)}</code></span>` +
        `${flagSpan(pair.flag, copy)}</div>` +
        `<ul class="pair-nums">` +
        share(pair.leaked_queries_pct, pair.query_split, pair.target_split) +
        share(pair.leaked_targets_pct, pair.target_split, pair.query_split) +
        `</ul></li>`).join("")}</ul>`;

  return `<div class="panel" id="panel-${esc(d.slug)}">
    ${probe}${caveat}${reference}
    <div class="panel-grid">
      <div>
        <h3>${esc(copy.panel.checks_heading)}</h3>
        <table class="checks">${sections}</table>
      </div>
      <div>
        <h3>${esc(copy.panel.splits_heading)}</h3>
        <ul class="shares">${splits}</ul>
        <h4>${esc(copy.panel.overlap_heading)}</h4>
        ${pairs}
      </div>
    </div>
    <p class="panel-more"><a href="${datasetHref(d)}">${esc(copy.panel.open_dataset)}</a></p>
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

/** The hover readout every figure on this site was already written for.
 *
 * `charts.py` puts the sentence a mark stands for in `data-tip` and gives the
 * mark `tabindex="0"`, on every bar, cell and dot it draws -- and nothing was
 * reading it, so the text existed in the markup and appeared nowhere. This is
 * the missing half: one element, delegated listeners, and no per-figure code.
 *
 * Pointer and keyboard both, because a mark that is focusable and says nothing
 * when focused is a tab stop that wastes a reader's time. `role="status"` rather
 * than `role="tooltip"`, so the text is announced when focus reaches the mark
 * instead of waiting for a description request that never comes.
 */
function markReadout() {
  const readout = document.createElement("div");
  readout.className = "readout";
  readout.setAttribute("role", "status");
  readout.hidden = true;
  document.body.appendChild(readout);

  const hide = () => { readout.hidden = true; };

  const show = (mark) => {
    readout.textContent = mark.dataset.tip;
    readout.hidden = false;
    // Measured after the text is in, because the box is as wide as its sentence.
    const box = mark.getBoundingClientRect();
    const self = readout.getBoundingClientRect();
    const margin = 8;
    // Above the mark, or below it when the mark is near the top of the viewport.
    const above = box.top - self.height - margin > 0;
    readout.style.top = `${(above ? box.top - self.height - margin : box.bottom + margin) + window.scrollY}px`;
    // Clamped to the viewport, so a mark at the right edge does not put its
    // sentence off the page.
    const left = Math.min(
      Math.max(margin, box.left + box.width / 2 - self.width / 2),
      document.documentElement.clientWidth - self.width - margin);
    readout.style.left = `${left + window.scrollX}px`;
  };

  const from = (event) => event.target.closest?.("[data-tip]") ?? null;

  // `pointerover`/`focusin` rather than `mouseenter`: these bubble, so one pair
  // of listeners covers every mark on the page including the ones drawn later.
  document.addEventListener("pointerover", (event) => {
    const mark = from(event);
    if (mark !== null) show(mark);
  });
  document.addEventListener("focusin", (event) => {
    const mark = from(event);
    if (mark !== null) show(mark);
  });
  document.addEventListener("pointerout", (event) => { if (from(event) !== null) hide(); });
  document.addEventListener("focusout", (event) => { if (from(event) !== null) hide(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") hide(); });
  // A readout positioned against the viewport goes stale the moment it moves.
  window.addEventListener("scroll", hide, { passive: true });
  window.addEventListener("resize", hide);
}

/** Mark which section of a long page the reader is in.
 *
 * The overview is one page carrying what used to be two, so "where am I" stops
 * being answered by the masthead alone. The jump list answers it, but only if it
 * says which of its entries is the one on screen.
 *
 * `IntersectionObserver` rather than a scroll handler: the question is which
 * sections are in view, which is what it reports, and a scroll listener would
 * have to ask the layout for a rectangle on every frame to find out.
 *
 * The nav is rendered by the build and works as anchors without any of this. All
 * this adds is the mark, so a browser without the observer loses a highlight
 * rather than a way of getting around.
 */
function jumpNav() {
  const nav = document.getElementById("jumpnav");
  if (nav === null || typeof IntersectionObserver !== "function") return;

  const links = new Map();
  for (const link of nav.querySelectorAll("a[href^='#']")) {
    const target = document.getElementById(link.getAttribute("href").slice(1));
    if (target !== null) links.set(target, link);
  }
  if (links.size === 0) return;

  const seen = new Set();
  const mark = () => {
    // The topmost section currently in view. Sections are taller than the
    // viewport, so several can intersect at once and "the last one to enter" is
    // whichever the reader scrolled past most recently rather than the one they
    // are looking at.
    let best = null;
    for (const target of links.keys()) {
      if (!seen.has(target)) continue;
      if (best === null || target.offsetTop < best.offsetTop) best = target;
    }
    for (const [target, link] of links) {
      if (target === best) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
  };

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) seen.add(entry.target);
        else seen.delete(entry.target);
      }
      mark();
    },
    // Discount the masthead and the nav itself, which sit over the top of the
    // page: without this a section is "in view" while hidden behind them.
    { rootMargin: "-140px 0px -55% 0px" },
  );
  for (const target of links.keys()) observer.observe(target);
}

/* Every page loads this file, and every page has the masthead. The catalogue's
 * own script runs after it and does not repeat any of this. */
(function chrome() {
  const copy = readJson("site-copy");
  if (copy === null) return;
  themeToggle(copy);
  backToTop(copy);
  copyButtons(copy);
  markReadout();
  jumpNav();
})();
