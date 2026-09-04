/* The catalogue table: 93 datasets, sortable, filterable, one panel per row.
 *
 * Tabulator does the scrolling and the sort. This file adds no number: it reads
 * `data/catalogue.json`, which `gb-audit build` writes and CI checks.
 *
 * **Every sorter is supplied rather than inherited.** Tabulator's numeric sorter
 * files `null` with the zeros, and a null here means the check had nothing to run
 * on -- which would make an absence of measurement look like a low score. Missing
 * values sort last in both directions instead.
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

function build(document_, copy) {
  const rows = document_.datasets;
  const checks = document_.checks;
  const counter = document.getElementById("count");

  const flagFormatter = (cell) => flagSpan(cell.getValue() ?? null, copy);
  const measureFormatter = (format) => (cell) =>
    measured(cell.getValue(), format, copy);

  const columns = [
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
    initialSort: [{ column: "benchmark_id", dir: "asc" }],
    rowFormatter: (row) => {
      // The panel is built once and kept, so re-sorting does not rebuild 93 of
      // them, and an open row stays open across a sort.
      const holder = document.createElement("div");
      holder.innerHTML = panelHtml(row.getData(), copy, checks);
      row.getElement().appendChild(holder.firstElementChild);
    },
  });

  table.on("rowClick", (event, row) => {
    // A click on a link is a click on the link, not on the row.
    if (event.target.closest("a")) return;
    row.getElement().classList.toggle("panel-open");
    row.normalizeHeight();
  });

  /* ------------------------------------------------------------ filters --- */

  const state = { q: "", facets: {} };

  const matches = (d) => {
    for (const [field, wanted] of Object.entries(state.facets)) {
      if (wanted.size && !wanted.has(String(d[field]))) return false;
    }
    if (!state.q) return true;
    const hay = [
      d.benchmark_id, d.collection, d.dataset_name, d.species,
      d.task_category, d.task_category_grouped, d.task_type, d.molecular_level,
    ].join(" ").toLowerCase();
    return state.q.split(/\s+/).every((term) => hay.includes(term));
  };

  const apply = () => {
    table.setFilter(matches);
    const shown = table.getDataCount("active");
    counter.textContent = `${shown} of ${rows.length}`;
  };

  const facetHolder = document.getElementById("facets");
  for (const field of FACETS) {
    const values = document_.facets[field];
    if (!values || values.length < 2) continue;
    state.facets[field] = new Set();
    const box = document.createElement("fieldset");
    box.innerHTML = `<legend>${esc(copy.columns[field] ?? field)}</legend>`;
    for (const value of values) {
      const id = `f-${field}-${value}`.replace(/[^\w-]/g, "_");
      const label = document.createElement("label");
      label.innerHTML =
        `<input type="checkbox" id="${id}" value="${esc(value)}"> ${esc(value)}`;
      label.querySelector("input").addEventListener("change", (event) => {
        const set = state.facets[field];
        if (event.target.checked) set.add(value); else set.delete(value);
        apply();
      });
      box.appendChild(label);
    }
    facetHolder.appendChild(box);
  }

  const search = document.getElementById("search");
  search.addEventListener("input", () => {
    state.q = search.value.trim().toLowerCase();
    apply();
  });

  document.getElementById("clear").addEventListener("click", () => {
    search.value = "";
    state.q = "";
    for (const set of Object.values(state.facets)) set.clear();
    for (const input of facetHolder.querySelectorAll("input")) input.checked = false;
    apply();
  });

  table.on("tableBuilt", apply);
  table.on("dataFiltered", () => {
    counter.textContent = `${table.getDataCount("active")} of ${rows.length}`;
  });
}

loadCatalogue().then((document_) => build(document_, readJson("site-copy")));
