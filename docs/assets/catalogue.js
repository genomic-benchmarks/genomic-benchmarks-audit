/* The catalogue table: 93 datasets, sortable, filterable, one panel per row.
 *
 * Tabulator does the scrolling and the sort. This file adds no number: it reads
 * `data/catalogue.json`, which `gb-audit build` writes and CI checks.
 *
 * **Every sorter is supplied rather than inherited.** Tabulator's numeric sorter
 * files `null` with the zeros, and a null here means the check had nothing to run
 * on -- which would make an absence of measurement look like a low score. Missing
 * values sort last in both directions instead.
 *
 * **The filters live in the URL.** Every facet, the search box, the sort and the
 * two thresholds are read from the query string on load and written back to it on
 * every change. That is what makes a filtered view a thing you can send someone,
 * and it is what lets the rest of the site link *into* this table: the checks
 * page points a count at the datasets it counts, a dataset page points at the
 * rest of its collection, the Core Set page points at its members. Without it
 * every one of those links would have to land here unfiltered and ask the reader
 * to reconstruct the question.
 */

const FACETS = [
  "collection",
  "task_category_grouped",
  "molecular_level",
  "task_type",
  "species",
  "overall_verdict",
];

/* Severity order, for sorting a column of flags. `Unknown` is deliberately not
 * on this ladder -- it is not a fourth degree of severity -- so it sorts to the
 * end with the blanks, where an unscored thing belongs. */
const SEVERITY = { Pass: 0, Warning: 1, Fail: 2 };

/* The four questions this table is opened for often enough to be worth a button.
 * Each one is the set of query parameters it stands for, so a preset and a link
 * from another page are the same mechanism and a pressed preset is just a state
 * the URL already describes. */
const PRESETS = [
  { key: "fail", params: { overall_verdict: ["Fail"] } },
  { key: "core", params: { core: ["1"] } },
  { key: "leakage", params: { leaked_min: ["50"], sort: ["max_leaked_test_pct:desc"] } },
  { key: "probe", params: { probe_min: ["0.7"], sort: ["max_probe_auroc:desc"] } },
];

/** Sort missing values last whichever way the column is pointing.
 *
 * A constant for the missing side would reverse with the direction and put the
 * unmeasured rows on top at the second click.
 */
const lastIfMissing = (compare) => (a, b, rowA, rowB, column, dir) => {
  const aMissing = a === null || a === undefined;
  const bMissing = b === null || b === undefined;
  if (aMissing && bMissing) return 0;
  if (aMissing) return dir === "asc" ? 1 : -1;
  if (bMissing) return dir === "asc" ? -1 : 1;
  return compare(a, b);
};

const numberSort = lastIfMissing((a, b) => a - b);
const severitySort = lastIfMissing((a, b) => (SEVERITY[a] ?? 99) - (SEVERITY[b] ?? 99));

/* ------------------------------------------------------------- url state --- */

/** Read the query string into the shape the filters work in.
 *
 * Facet values are repeated parameters rather than one comma-joined value: a
 * species is `Oryza sativa Indica Group` and a task category can carry a comma of
 * its own, and a separator that appears inside a value is a separator that
 * eventually splits one.
 */
function readState(document_) {
  const params = new URLSearchParams(window.location.search);
  const state = { q: "", facets: {}, core: false, check: null, flag: null,
                  leakedMin: null, probeMin: null, sort: null };

  for (const field of FACETS) state.facets[field] = new Set(params.getAll(field));
  state.q = (params.get("q") ?? "").trim().toLowerCase();
  state.core = params.get("core") === "1";

  // A check filter is two parameters that only mean anything together: which
  // check, and which flag it returned. Either one alone would silently filter on
  // something the reader did not ask for, so both or neither.
  const check = params.get("check");
  const flag = params.get("flag");
  if (check !== null && flag !== null && check in (document_.datasets[0]?.flags ?? {})) {
    state.check = check;
    state.flag = flag;
  }

  const leaked = Number.parseFloat(params.get("leaked_min"));
  if (Number.isFinite(leaked)) state.leakedMin = leaked;
  const probe = Number.parseFloat(params.get("probe_min"));
  if (Number.isFinite(probe)) state.probeMin = probe;

  const sort = params.get("sort");
  if (sort !== null && sort.includes(":")) {
    const [column, dir] = sort.split(":");
    state.sort = { column, dir: dir === "desc" ? "desc" : "asc" };
  }
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
  for (const field of FACETS) {
    for (const value of state.facets[field]) params.append(field, value);
  }
  if (state.q) params.set("q", state.q);
  if (state.core) params.set("core", "1");
  if (state.check !== null) {
    params.set("check", state.check);
    params.set("flag", state.flag);
  }
  if (state.leakedMin !== null) params.set("leaked_min", String(state.leakedMin));
  if (state.probeMin !== null) params.set("probe_min", String(state.probeMin));
  if (state.sort !== null) params.set("sort", `${state.sort.column}:${state.sort.dir}`);

  const query = params.toString();
  window.history.replaceState(
    null, "", query ? `?${query}${window.location.hash}` : window.location.pathname + window.location.hash);
}

/* ---------------------------------------------------------------- build --- */

function build(document_, copy) {
  const rows = document_.datasets;
  const checks = document_.checks;
  const counter = document.getElementById("count");
  const chipHolder = document.getElementById("chips");
  const state = readState(document_);

  const flagFormatter = (cell) => flagSpan(cell.getValue() ?? null, copy);
  const measureFormatter = (format) => (cell) =>
    measured(cell.getValue(), format, copy);

  const columns = [
    {
      // The disclosure. A column of its own rather than a click handler on the
      // row alone: the panel holds each dataset's ten flags and was reachable
      // with a pointer and by nothing else.
      title: "",
      field: "slug",
      width: 40,
      headerSort: false,
      resizable: false,
      formatter: (cell) => {
        const d = cell.getRow().getData();
        return `<button type="button" class="row-toggle" aria-expanded="false"` +
          ` aria-controls="panel-${esc(d.slug)}" aria-label="${esc(copy.filters.expand)}">` +
          `<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 0l6 5-6 5z"/></svg></button>`;
      },
    },
    {
      title: copy.columns.benchmark_id,
      field: "benchmark_id",
      widthGrow: 3,
      minWidth: 230,
      formatter: (cell) => {
        const d = cell.getRow().getData();
        return `<a class="dataset" href="${datasetHref(d)}">` +
          `<span class="collection-part">${esc(d.collection)}:</span><wbr>` +
          `${breakable(d.dataset_name)}</a>`;
      },
    },
    {
      title: copy.columns.task_category_grouped,
      field: "task_category_grouped",
      tooltip: true,
      widthGrow: 2,
      minWidth: 150,
    },
    { title: copy.columns.molecular_level, field: "molecular_level", width: 78 },
    {
      title: copy.columns.species,
      field: "species",
      tooltip: true,
      widthGrow: 2,
      minWidth: 140,
      formatter: (cell) => esc(cell.getValue() ?? ""),
    },
    {
      title: copy.columns.total_size,
      field: "total_size",
      hozAlign: "right",
      width: 92,
      sorter: numberSort,
      headerTooltip: copy.column_help.total_size,
      formatter: measureFormatter(num),
    },
    {
      title: copy.columns.overall_verdict,
      field: "overall_verdict",
      width: 108,
      sorter: severitySort,
      headerTooltip: copy.column_help.overall_verdict,
      formatter: flagFormatter,
    },
    {
      title: copy.columns.max_probe_auroc,
      field: "max_probe_auroc",
      hozAlign: "right",
      width: 122,
      sorter: numberSort,
      headerTooltip: copy.column_help.max_probe_auroc,
      formatter: measureFormatter((v) => v.toFixed(3)),
    },
    {
      title: copy.columns.max_leaked_test_pct,
      field: "max_leaked_test_pct",
      hozAlign: "right",
      width: 122,
      sorter: numberSort,
      headerTooltip: copy.column_help.max_leaked_test_pct,
      formatter: measureFormatter(pct),
    },
    {
      title: copy.columns.in_core_set,
      field: "in_core_set",
      width: 104,
      hozAlign: "center",
      headerTooltip: copy.column_help.in_core_set,
      sorter: (a, b) => Number(b) - Number(a),
      // The tag says "Core Set" and the column heading says the rest. The panel's
      // longer phrasing did not fit and was being clipped mid-word, which is a
      // label that states something shorter than it means.
      formatter: (cell) =>
        cell.getValue() ? `<span class="tag">${esc(copy.columns.in_core_set)}</span>` : "",
    },
  ];

  const table = new Tabulator("#table", {
    data: rows,
    columns,
    layout: "fitColumns",
    height: "70vh",
    placeholder: esc(copy.empty.no_rows),
    initialSort: [state.sort ?? { column: "benchmark_id", dir: "asc" }],
    rowFormatter: (row) => {
      // The panel is built once and kept, so re-sorting does not rebuild 93 of
      // them, and an open row stays open across a sort.
      const holder = document.createElement("div");
      holder.innerHTML = panelHtml(row.getData(), copy, checks);
      row.getElement().appendChild(holder.firstElementChild);
    },
  });

  /** Open or close one row, keeping the button's state saying which it is. */
  const togglePanel = (row) => {
    const element = row.getElement();
    const open = element.classList.toggle("panel-open");
    const button = element.querySelector(".row-toggle");
    if (button !== null) {
      button.setAttribute("aria-expanded", String(open));
      button.setAttribute("aria-label", open ? copy.filters.collapse : copy.filters.expand);
    }
    row.normalizeHeight();
  };

  table.on("rowClick", (event, row) => {
    // A click on a link is a click on the link, not on the row. The disclosure
    // button is not excluded: pressing it with Enter or the space bar dispatches
    // a click that arrives here, which is how the panel opens from the keyboard.
    if (event.target.closest("a")) return;
    togglePanel(row);
  });

  // Tabulator sorts once while building, before anyone has asked it to. Writing
  // that into the address would give every reader `?sort=benchmark_id:asc` for a
  // sort they did not choose, so the initial one is not recorded -- a sort that
  // came in on the URL is already in `state` and stays there.
  let built = false;

  table.on("dataSorted", (sorters) => {
    const first = sorters[0];
    if (!built || first === undefined) return;
    state.sort = { column: first.field, dir: first.dir };
    writeState(state);
  });

  /* ------------------------------------------------------------ filters --- */

  const matches = (d) => {
    for (const [field, wanted] of Object.entries(state.facets)) {
      if (wanted.size && !wanted.has(String(d[field]))) return false;
    }
    if (state.core && !d.in_core_set) return false;
    if (state.check !== null && (d.flags[state.check] ?? null) !== state.flag) return false;
    // `?? -1` rather than `?? 0`: a dataset that was never scanned has no overlap
    // to compare against a threshold, and treating its absence as zero would file
    // it with the datasets measured at zero.
    if (state.leakedMin !== null && (d.max_leaked_test_pct ?? -1) < state.leakedMin) return false;
    if (state.probeMin !== null && (d.max_probe_auroc ?? -1) < state.probeMin) return false;
    if (!state.q) return true;
    const hay = [
      d.benchmark_id, d.collection, d.dataset_name, d.species,
      d.task_category, d.task_category_grouped, d.task_type, d.molecular_level,
    ].join(" ").toLowerCase();
    return state.q.split(/\s+/).every((term) => hay.includes(term));
  };

  /* --------------------------------------------------------------- chips --- */

  /** Every condition currently narrowing the table, as one removable chip each.
   *
   * A reader who arrives on a link from the checks page is looking at 12 rows of
   * 93 and is owed a statement of why. `undo` is what the chip's button does,
   * which keeps removing a filter and applying one in the same place.
   */
  /** The checkbox for one facet value, so ticking it and removing its chip are
   * the same state. Found by comparing values rather than by building a selector
   * out of one: a species is `Oryza sativa Indica Group`. */
  const facetInput = (field, value) =>
    [...facetHolder.querySelectorAll("input")].find(
      (input) => input.dataset.field === field && input.value === String(value)) ?? null;

  const conditions = () => {
    const list = [];
    for (const field of FACETS) {
      for (const value of state.facets[field]) {
        list.push({
          field: copy.columns[field] ?? field,
          value,
          undo: () => {
            state.facets[field].delete(value);
            const input = facetInput(field, value);
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
    if (state.core) {
      list.push({
        field: copy.filters.core_set,
        value: copy.filters.core_set_value,
        undo: () => { state.core = false; },
      });
    }
    if (state.check !== null) {
      list.push({
        field: copy.filters.check,
        value: `${state.check} — ${copy.flags[state.flag] ?? state.flag}`,
        undo: () => { state.check = null; state.flag = null; },
      });
    }
    if (state.leakedMin !== null) {
      list.push({
        field: copy.filters.leaked_over,
        value: pct(state.leakedMin),
        undo: () => { state.leakedMin = null; },
      });
    }
    if (state.probeMin !== null) {
      list.push({
        field: copy.filters.probe_over,
        value: state.probeMin.toFixed(3),
        undo: () => { state.probeMin = null; },
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

  /** Whether a preset's whole parameter set is what the state currently says. */
  const presetActive = (preset) => {
    for (const [name, values] of Object.entries(preset.params)) {
      if (FACETS.includes(name)) {
        if (!values.every((v) => state.facets[name].has(String(v)))) return false;
      } else if (name === "core") {
        if (!state.core) return false;
      } else if (name === "leaked_min") {
        if (state.leakedMin !== Number.parseFloat(values[0])) return false;
      } else if (name === "probe_min") {
        if (state.probeMin !== Number.parseFloat(values[0])) return false;
      }
      // `sort` is part of what a preset sets but not of what makes it pressed: a
      // reader who re-sorts is still looking at the preset's rows.
    }
    return true;
  };

  const apply = () => {
    table.setFilter(matches);
    counter.textContent = copy.filters.shown
      .replace("{shown}", num(table.getDataCount("active")))
      .replace("{total}", num(rows.length));
    drawChips();
    for (const button of presetHolder.querySelectorAll(".preset")) {
      const preset = PRESETS.find((p) => p.key === button.dataset.preset);
      button.setAttribute("aria-pressed", String(preset !== undefined && presetActive(preset)));
    }
    writeState(state);
  };

  /* -------------------------------------------------------------- facets --- */

  const facetHolder = document.getElementById("facets");
  for (const field of FACETS) {
    const values = document_.facets[field];
    if (!values || values.length < 2) continue;
    const box = document.createElement("fieldset");
    box.innerHTML = `<legend>${esc(copy.columns[field] ?? field)}</legend>`;
    for (const value of values) {
      const id = `f-${field}-${value}`.replace(/[^\w-]/g, "_");
      const label = document.createElement("label");
      const checked = state.facets[field].has(String(value)) ? " checked" : "";
      label.innerHTML =
        `<input type="checkbox" id="${id}" data-field="${esc(field)}" ` +
        `value="${esc(value)}"${checked}> ${esc(value)}`;
      label.querySelector("input").addEventListener("change", (event) => {
        const set = state.facets[field];
        if (event.target.checked) set.add(String(value)); else set.delete(String(value));
        apply();
      });
      box.appendChild(label);
    }
    facetHolder.appendChild(box);
  }

  /* ------------------------------------------------------------- presets --- */

  const presetHolder = document.getElementById("presets");
  const presetLabel = document.createElement("span");
  presetLabel.className = "presets-label";
  presetLabel.textContent = copy.presets.heading;
  presetHolder.appendChild(presetLabel);

  /** Clear everything. Also what the Clear button does, and what a preset does
   * before applying its own conditions, so pressing two presets in turn shows the
   * second rather than both. */
  const clearAll = () => {
    state.q = "";
    search.value = "";
    state.core = false;
    state.check = null;
    state.flag = null;
    state.leakedMin = null;
    state.probeMin = null;
    for (const set of Object.values(state.facets)) set.clear();
    for (const input of facetHolder.querySelectorAll("input")) input.checked = false;
  };

  for (const preset of PRESETS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset";
    button.dataset.preset = preset.key;
    button.setAttribute("aria-pressed", "false");
    button.textContent = copy.presets[preset.key];
    button.addEventListener("click", () => {
      const wasActive = presetActive(preset);
      clearAll();
      if (!wasActive) {
        for (const [name, values] of Object.entries(preset.params)) {
          if (FACETS.includes(name)) {
            for (const value of values) {
              state.facets[name].add(String(value));
              const input = facetInput(name, value);
              if (input !== null) input.checked = true;
            }
          } else if (name === "core") {
            state.core = true;
          } else if (name === "leaked_min") {
            state.leakedMin = Number.parseFloat(values[0]);
          } else if (name === "probe_min") {
            state.probeMin = Number.parseFloat(values[0]);
          } else if (name === "sort") {
            const [column, dir] = values[0].split(":");
            table.setSort(column, dir);
          }
        }
      }
      apply();
    });
    presetHolder.appendChild(button);
  }

  /* -------------------------------------------------------------- search --- */

  const search = document.getElementById("search");
  search.value = state.q;
  search.addEventListener("input", () => {
    state.q = search.value.trim().toLowerCase();
    apply();
  });

  document.getElementById("clear").addEventListener("click", () => {
    clearAll();
    apply();
  });

  table.on("tableBuilt", () => {
    built = true;
    apply();
  });
  table.on("dataFiltered", () => {
    counter.textContent = copy.filters.shown
      .replace("{shown}", num(table.getDataCount("active")))
      .replace("{total}", num(rows.length));
  });
}

loadCatalogue().then((document_) => build(document_, readJson("site-copy")));
