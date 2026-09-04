/* The reports table: 423 reports across 93 datasets, narrowed in the browser.
 *
 * The table is rendered by `site.py` and is the whole list whether or not this
 * file runs. Everything here removes rows and report links from what is already
 * on the page: nothing is fetched, nothing is rebuilt from JSON, and no count
 * here can disagree with what was rendered, because every count is taken off the
 * page itself. That is also why the controls start hidden -- with scripting off
 * there is nothing for them to do, and a control that cannot do anything is
 * worse than no control.
 *
 * **The filters live in the URL**, the same as on the catalogue: every facet and
 * the search box are read from the query string on load and written back to it on
 * every change, so a filtered view is a thing you can send someone.
 *
 * Two of the facets narrow rows and two narrow the links inside them. A dataset
 * is a row; a report is one link in that row's last cell. Filtering to the
 * leakage scans has to remove 282 links as well as the rows that have none,
 * because leaving the class reports on screen under a heading that says leakage
 * scan is the page answering a question nobody asked.
 */

const FACETS = [
  { key: "collection", level: "row" },
  { key: "kind", level: "item", order: ["class", "leakage-scan"] },
  /* train, then val, then test: the order a reader holds them in, not the one
   * the alphabet gives. Anything else follows, sorted. */
  { key: "split", level: "item", order: ["train", "val", "test"] },
  { key: "state", level: "row", order: ["unpacked", "linked", "unpublished"] },
];

/** Sort a facet's values, putting the ones it names first and in that order. */
const ordered = (values, order) =>
  [...values].sort((a, b) => {
    const rank = (value) => {
      const at = order === undefined ? -1 : order.indexOf(value);
      return at < 0 ? Number.MAX_SAFE_INTEGER : at;
    };
    return rank(a) - rank(b) || a.localeCompare(b);
  });

/** The values one row or one report link carries for a facet.
 *
 * A leakage scan is about two splits and carries both, space-separated, so
 * filtering to `test` keeps `train vs test` -- the scan is a fact about the test
 * split as much as about the train split.
 */
const valuesOf = (element, key) =>
  (element.dataset[key] ?? "").split(/\s+/).filter(Boolean);

/* ------------------------------------------------------------- url state --- */

function readState() {
  const params = new URLSearchParams(window.location.search);
  const state = { q: "", facets: {} };
  for (const facet of FACETS) state.facets[facet.key] = new Set(params.getAll(facet.key));
  state.q = (params.get("q") ?? "").trim().toLowerCase();
  return state;
}

/** Write the state back, so the address bar always describes what is on screen.
 *
 * `replaceState`, not `pushState`: the search box fires on every keystroke, and a
 * history entry per keystroke makes the back button a way of retyping rather than
 * a way of leaving.
 */
function writeState(state) {
  const params = new URLSearchParams();
  for (const facet of FACETS) {
    for (const value of state.facets[facet.key]) params.append(facet.key, value);
  }
  if (state.q) params.set("q", state.q);
  const query = params.toString();
  window.history.replaceState(
    null, "",
    query
      ? `?${query}${window.location.hash}`
      : window.location.pathname + window.location.hash);
}

/* ---------------------------------------------------------------- build --- */

function build(copy) {
  const table = document.querySelector(".reports-table");
  const controls = document.getElementById("controls");
  if (table === null || controls === null) return;
  // The card is what gets hidden when nothing matches: a bordered box holding a
  // header row and no rows is a table pretending it still has an answer.
  const card = table.closest(".table-card") ?? table;

  const words = copy.report_filters;
  const entries = [...table.querySelectorAll("tbody tr")].map((row) => ({
    row,
    items: [...row.querySelectorAll("li.report")],
    search: row.dataset.search ?? "",
  }));
  const totalReports = entries.reduce((n, entry) => n + entry.items.length, 0);
  const state = readState();

  const counter = document.getElementById("count");
  const chipHolder = document.getElementById("chips");
  const facetHolder = document.getElementById("facets");
  const empty = document.getElementById("empty");
  const search = document.getElementById("search");

  /* ------------------------------------------------------------ filters --- */

  const keeps = (element, level) => {
    for (const facet of FACETS) {
      if (facet.level !== level) continue;
      const wanted = state.facets[facet.key];
      if (!wanted.size) continue;
      if (!valuesOf(element, facet.key).some((value) => wanted.has(value))) return false;
    }
    return true;
  };

  const rowMatches = (entry) => {
    if (!keeps(entry.row, "row")) return false;
    if (!state.q) return true;
    return state.q.split(/\s+/).every((term) => entry.search.includes(term));
  };

  const apply = () => {
    let shownReports = 0;
    let shownRows = 0;
    for (const entry of entries) {
      const wanted = rowMatches(entry);
      let visible = 0;
      for (const item of entry.items) {
        const on = wanted && keeps(item, "item");
        item.hidden = !on;
        if (on) visible += 1;
      }
      // A row every one of whose reports was filtered out is a row about
      // nothing here. The dataset has not stopped existing; this view is a view
      // of reports, and it has none of them to show for this one.
      const show = wanted && (entry.items.length === 0 || visible > 0);
      entry.row.hidden = !show;
      if (show) {
        shownRows += 1;
        shownReports += visible;
      }
    }

    counter.textContent = words.shown
      .replace("{shown}", num(shownReports))
      .replace("{total}", num(totalReports))
      .replace("{datasets}", num(shownRows))
      .replace("{n}", num(entries.length));
    empty.textContent = words.no_rows;
    empty.hidden = shownRows > 0;
    card.hidden = shownRows === 0;

    drawChips();
    writeState(state);
  };

  /* --------------------------------------------------------------- chips --- */

  /** What one facet value is called on screen. The raw value is what the filter
   * matches on and what goes in the URL; this is only what a reader is shown. */
  const label = (facet, value) => {
    if (facet.key === "kind") {
      return value === "class" ? copy.reports.class_kind : copy.reports.leakage_kind;
    }
    if (facet.key === "state") return words[`state_${value}`] ?? value;
    return value;
  };

  /** The checkbox for one facet value, so ticking it and removing its chip are
   * the same state. Found by comparing values rather than by building a selector
   * out of one, because a value is not guaranteed to be selector-safe. */
  const facetInput = (key, value) =>
    [...facetHolder.querySelectorAll("input")].find(
      (input) => input.dataset.facet === key && input.value === String(value)) ?? null;

  /** Every condition currently narrowing the table, as one removable chip each.
   *
   * A reader who arrives on a filtered link is looking at 141 reports of 423 and
   * is owed a statement of why. `undo` is what the chip's button does, which
   * keeps removing a filter and applying one in the same place.
   */
  const conditions = () => {
    const list = [];
    for (const facet of FACETS) {
      for (const value of state.facets[facet.key]) {
        list.push({
          field: words[facet.key] ?? facet.key,
          value: label(facet, value),
          undo: () => {
            state.facets[facet.key].delete(value);
            const input = facetInput(facet.key, value);
            if (input !== null) input.checked = false;
          },
        });
      }
    }
    if (state.q) {
      list.push({
        field: copy.filters.search,
        value: state.q,
        undo: () => { state.q = ""; search.value = ""; },
      });
    }
    return list;
  };

  const drawChips = () => {
    chipHolder.textContent = "";
    const list = conditions();
    if (list.length === 0) return;
    const heading = document.createElement("span");
    heading.className = "chip-heading fine";
    heading.textContent = copy.filters.heading;
    chipHolder.appendChild(heading);
    for (const condition of list) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML =
        `<span class="chip-field">${esc(condition.field)}</span>` +
        `<span>${esc(condition.value)}</span>` +
        `<button type="button" aria-label="${esc(copy.filters.remove)}">&times;</button>`;
      chip.querySelector("button").addEventListener("click", () => {
        condition.undo();
        apply();
      });
      chipHolder.appendChild(chip);
    }
  };

  /* -------------------------------------------------------------- facets --- */

  /* Built from the table rather than from a list written beside it. The facet
   * then offers exactly the values the page carries: a build with no reports
   * fetched has one state and gets no state facet, and a collection that leaves
   * the corpus leaves this control with it. */
  for (const facet of FACETS) {
    const found = new Set();
    for (const entry of entries) {
      const sources = facet.level === "row" ? [entry.row] : entry.items;
      for (const source of sources) {
        for (const value of valuesOf(source, facet.key)) found.add(value);
      }
    }
    // One value is not a choice: every row has it, and ticking it would filter
    // nothing while suggesting it had.
    if (found.size < 2) continue;

    const box = document.createElement("fieldset");
    box.innerHTML = `<legend>${esc(words[facet.key] ?? facet.key)}</legend>`;
    for (const value of ordered(found, facet.order)) {
      const id = `f-${facet.key}-${value}`.replace(/[^\w-]/g, "_");
      const item = document.createElement("label");
      const checked = state.facets[facet.key].has(value) ? " checked" : "";
      item.innerHTML =
        `<input type="checkbox" id="${id}" data-facet="${esc(facet.key)}" ` +
        `value="${esc(value)}"${checked}> ${esc(label(facet, value))}`;
      item.querySelector("input").addEventListener("change", (event) => {
        const set = state.facets[facet.key];
        if (event.target.checked) set.add(value); else set.delete(value);
        apply();
      });
      box.appendChild(item);
    }
    facetHolder.appendChild(box);
  }

  /* -------------------------------------------------------------- search --- */

  search.value = state.q;
  search.addEventListener("input", () => {
    state.q = search.value.trim().toLowerCase();
    apply();
  });

  const clearAll = () => {
    state.q = "";
    search.value = "";
    for (const set of Object.values(state.facets)) set.clear();
    for (const input of facetHolder.querySelectorAll("input")) input.checked = false;
  };

  document.getElementById("clear").addEventListener("click", () => {
    clearAll();
    apply();
  });

  controls.hidden = false;
  apply();
}

build(readJson("site-copy"));
