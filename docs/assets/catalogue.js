/* The catalogue table: 93 datasets against ten checks, one panel per row.
 *
 * Tabulator does the scrolling and the sort. This file adds no number: it reads
 * `data/catalogue.json`, which `gb-audit build` writes and CI checks.
 *
 * **The grid is the table.** One row per dataset and one column per check, drawn
 * the way `gb_audit/matrix.py` draws the same grid on the overview and the
 * checks page -- same order, same short headings, same three bands over them, so
 * a reader who learned the shape there is not asked to learn it twice. What this
 * one adds is that the rows sort, filter and open, and that everything else the
 * run measured about a dataset can be put beside the flags a column at a time.
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

/* Which columns the table can show besides the dataset's name, in the order
 * they sit in, and which of them it opens with.
 *
 * It opens as the overview's grid and the flag that rolls up out of it: a name,
 * ten checks, and the worst thing any of them returned. The dozen other facts
 * the run holds about a dataset are one tick away and off until asked for --
 * twelve columns of metadata beside ten of flags is a table nobody can read at
 * any width, and which two of the twelve a reader wants is not a thing this file
 * can know. So it is a control rather than a decision made here.
 *
 * `checks` is the whole block of ten and not a column: they go on and off
 * together, because nine of them on their own is not a view anyone asked for.
 */
const OPTIONAL_COLUMNS = [
  { key: "collection", on: false },
  { key: "task_category_grouped", on: false },
  { key: "task_type", on: false },
  { key: "molecular_level", on: false },
  { key: "species", on: false },
  { key: "total_size", on: false },
  { key: "seq_length", on: false },
  { key: "overall_verdict", on: true },
  { key: "n_checks_failed", on: false },
  { key: "max_probe_auroc", on: false },
  { key: "joint_auroc", on: false },
  { key: "max_leaked_test_pct", on: false },
  { key: "in_core_set", on: false },
  { key: "checks", on: true },
];

const DEFAULT_COLUMNS = OPTIONAL_COLUMNS.filter((c) => c.on).map((c) => c.key);

/** Whether a chosen set of columns is exactly the one the table opens with. */
const sameColumns = (chosen, base) =>
  chosen.size === base.length && base.every((key) => chosen.has(key));

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
  { key: "joint", params: { joint_min: ["0.8"], sort: ["joint_auroc:desc"] } },
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
                  leakedMin: null, probeMin: null, jointMin: null, sort: null };

  for (const field of FACETS) state.facets[field] = new Set(params.getAll(field));
  state.q = (params.get("q") ?? "").trim().toLowerCase();
  state.core = params.get("core") === "1";

  /* Which columns are on screen, comma-joined and not repeated: unlike a facet
   * value, a column key is chosen in this file and cannot carry a separator of
   * its own. An unknown key is dropped rather than carried, so a hand-edited
   * address cannot ask for a column that does not exist -- and an absent
   * parameter is the default set, which is not the same thing as an empty one. */
  const known = new Set(OPTIONAL_COLUMNS.map((c) => c.key));
  state.cols = params.has("cols")
    ? new Set(params.get("cols").split(",").filter((key) => known.has(key)))
    : new Set(DEFAULT_COLUMNS);

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
  const joint = Number.parseFloat(params.get("joint_min"));
  if (Number.isFinite(joint)) state.jointMin = joint;

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
  // In the list's own order rather than the order they were ticked, so two
  // readers who put the same columns on send the same address. Left out entirely
  // when it is the set the table opens with: a default is not a condition.
  if (!sameColumns(state.cols, DEFAULT_COLUMNS)) {
    params.set(
      "cols",
      OPTIONAL_COLUMNS.filter((c) => state.cols.has(c.key)).map((c) => c.key).join(","));
  }
  if (state.check !== null) {
    params.set("check", state.check);
    params.set("flag", state.flag);
  }
  if (state.leakedMin !== null) params.set("leaked_min", String(state.leakedMin));
  if (state.probeMin !== null) params.set("probe_min", String(state.probeMin));
  if (state.jointMin !== null) params.set("joint_min", String(state.jointMin));
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

  /* Tabulator sorts and filters by field, and a field is a key it looks up on
   * the row. The ten flags arrive under `d.flags`, keyed by the check's full
   * name -- which Tabulator would read as a path the moment a name carried a
   * dot. Each check gets a flat key of its own instead, made from its position
   * in the order the run publishes them rather than from the name. */
  const checkField = (index) => `check_${index}`;
  for (const d of rows) {
    checks.forEach((check, index) => { d[checkField(index)] = d.flags[check.name] ?? null; });
    /* The joint reading arrives as an object, because the value is not separable
     * from whether it is a lower bound. Tabulator sorts on a field, so the value
     * gets a flat key here while the object stays where the formatter reads the
     * caveat off it -- one copy of the number in the file, two ways in. */
    d.joint_auroc = d.joint === null ? null : d.joint.auroc;
  }

  /* One column per check, drawn as the overview's grid draws it: a fill, not a
   * word. Ten words of Pass and Fail across a row is ten things to read; ten
   * fills is one shape, and the flag is still there in the tooltip and to a
   * screen reader. The three fills are `--flag-fill-*`, whose lightness orders
   * the severity, so the ordering survives colour vision deficiency. */
  const checkColumns = checks.map((check, index) => {
    const short = copy.check_short[check.name] ?? [check.name, ""];
    const word = (flag) => copy.flags[flag] ?? flag;
    return {
      title: check.name,
      field: checkField(index),
      /* Room to grow, but not much. `fitColumns` hands the slack to whatever
       * will take it, and with only the name column asking, the name column got
       * five hundred pixels for a thirty-character string while the grid beside
       * it stayed at the width it needs on a phone. A ceiling on the cell is
       * what keeps the ten reading as a grid rather than as ten bars. */
      width: 50,
      minWidth: 44,
      maxWidth: 66,
      widthGrow: 1,
      resizable: false,
      hozAlign: "center",
      headerHozAlign: "center",
      headerTooltip: check.name,
      cssClass: "check-cell",
      sorter: severitySort,
      /* Two short lines rather than the check's own name: "Per position reversed
       * nucleotide content" over fifty pixels is a heading no width this table
       * has to spare can render. The pair is the one the overview's grid and the
       * manuscript's supplementary figure both use, so a reader with one open
       * beside the other finds a column in the same place. */
      titleFormatter: () =>
        `<span class="ch-line">${esc(short[0])}</span>` +
        `<span class="ch-line">${esc(short[1])}</span>`,
      formatter: (cell) => {
        const flag = cell.getValue() ?? null;
        /* Three absences kept apart, as everywhere else on this site: a scored
         * flag is a fill, `Unknown` is an outline, and a check with nothing to
         * run on is an empty cell that is still a cell. */
        if (flag === null) {
          return `<span class="cflag cflag-blank" title="${esc(check.name)}: ` +
            `${esc(copy.matrix.blank)}"><span class="sr-only">` +
            `${esc(copy.matrix.blank)}</span></span>`;
        }
        return `<span class="cflag cflag-${esc(flag)}" title="${esc(check.name)}: ` +
          `${esc(word(flag))}"><span class="sr-only">${esc(word(flag))}</span></span>`;
      },
    };
  });

  /* The three families, as a band over their columns -- the same row the grid on
   * the overview carries. Built by walking the checks in the order they arrive
   * rather than from a table of positions: the run publishes each family in one
   * unbroken run, so a band built this way cannot end up over a check from
   * another one, and a check added to a family needs nothing here. */
  const bands = [];
  checks.forEach((check, index) => {
    const last = bands[bands.length - 1];
    if (last !== undefined && last.kind === check.kind) last.columns.push(checkColumns[index]);
    else bands.push({ kind: check.kind, columns: [checkColumns[index]] });
  });

  /** The columns a reader can put on and take off, one definition each. Kept
   * apart from `OPTIONAL_COLUMNS` so that the list up there stays a statement
   * about order and defaults, which is the part of this that gets edited. */
  const defs = {
    collection: {
      title: copy.columns.collection,
      field: "collection",
      widthGrow: 1,
      minWidth: 116,
    },
    task_category_grouped: {
      title: copy.columns.task_category_grouped,
      field: "task_category_grouped",
      tooltip: true,
      widthGrow: 2,
      minWidth: 150,
    },
    task_type: {
      title: copy.columns.task_type,
      field: "task_type",
      widthGrow: 1,
      minWidth: 118,
    },
    molecular_level: {
      title: copy.columns.molecular_level,
      field: "molecular_level",
      width: 78,
    },
    species: {
      title: copy.columns.species,
      field: "species",
      tooltip: true,
      widthGrow: 2,
      minWidth: 140,
      formatter: (cell) => esc(cell.getValue() ?? ""),
    },
    total_size: {
      title: copy.columns.total_size,
      field: "total_size",
      hozAlign: "right",
      width: 92,
      sorter: numberSort,
      headerTooltip: copy.column_help.total_size,
      formatter: measureFormatter(num),
    },
    seq_length: {
      /* Two numbers in one column, sorted on the shorter. A dataset of fixed
       * 23-mers and one running 23 to 6000 are different things to hold, and
       * they are read together or not at all -- so a column each would spend
       * twice the width on half a fact. */
      title: copy.columns.seq_length,
      field: "min_seq_length",
      hozAlign: "right",
      width: 118,
      sorter: numberSort,
      headerTooltip: copy.column_help.seq_length,
      formatter: (cell) => {
        const d = cell.getRow().getData();
        const low = d.min_seq_length ?? null;
        const high = d.max_seq_length ?? null;
        if (low === null || high === null) return measured(null, num, copy);
        return low === high
          ? esc(num(low))
          : `${esc(num(low))}&ndash;${esc(num(high))}`;
      },
    },
    overall_verdict: {
      title: copy.columns.overall_verdict,
      field: "overall_verdict",
      width: 108,
      sorter: severitySort,
      headerTooltip: copy.column_help.overall_verdict,
      formatter: flagFormatter,
    },
    n_checks_failed: {
      title: copy.columns.n_checks_failed,
      field: "n_checks_failed",
      hozAlign: "right",
      width: 116,
      sorter: numberSort,
      headerTooltip: copy.column_help.n_checks_failed,
      formatter: measureFormatter(num),
    },
    max_probe_auroc: {
      title: copy.columns.max_probe_auroc,
      field: "max_probe_auroc",
      hozAlign: "right",
      width: 122,
      sorter: numberSort,
      headerTooltip: copy.column_help.max_probe_auroc,
      formatter: measureFormatter((v) => v.toFixed(3)),
    },
    /* The one column here measured somewhere other than the reference split, and
     * the one the ten checks cannot produce between them. Beside the
     * strongest-probe column on purpose: the pair is the whole argument -- the
     * checks read separately, and the same features read together. */
    joint_auroc: {
      title: copy.columns.joint_auroc,
      field: "joint_auroc",
      hozAlign: "right",
      width: 122,
      sorter: numberSort,
      headerTooltip: copy.column_help.joint_auroc,
      formatter: (cell) => {
        const joint = cell.getRow().getData().joint;
        if (joint === null || joint === undefined) return `<span class="dash">&mdash;</span>`;
        const shown = joint.auroc.toFixed(3);
        // The mark travels with the number. A capped or subsampled figure can
        // only be too low, so a reader comparing it against a ceiling needs to
        // know that at the point of comparison and not in a footnote.
        if (!joint.lower_bound) return shown;
        const tip = copy.joint.lower_bound_tip.replace("{caveat}", joint.caveat ?? "");
        return `${shown}<abbr class="lb" title="${esc(tip)}">${esc(copy.joint.lower_bound_mark)}</abbr>`;
      },
    },
    max_leaked_test_pct: {
      title: copy.columns.max_leaked_test_pct,
      field: "max_leaked_test_pct",
      hozAlign: "right",
      width: 122,
      sorter: numberSort,
      headerTooltip: copy.column_help.max_leaked_test_pct,
      formatter: measureFormatter(pct),
    },
    in_core_set: {
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
  };

  /** Every field one picker entry stands for. The check block stands for ten. */
  const fieldsOfKey = (key) =>
    key === "checks" ? checkColumns.map((column) => column.field) : [defs[key].field];

  /** The picker entry a field belongs to, for the other direction: something is
   * about to sort by this column and needs to know whether it is on screen. */
  const keyOfField = new Map();
  for (const entry of OPTIONAL_COLUMNS) {
    for (const field of fieldsOfKey(entry.key)) keyOfField.set(field, entry.key);
  }

  /** Put a column on screen because something is about to sort by it.
   *
   * A sort arriving on the address, or a quick view that sets one, names a
   * column the reader may have turned off -- and a table ordered by a column
   * that is not on it is a table in an order nothing on screen explains.
   */
  const showFor = (field) => {
    const key = keyOfField.get(field);
    if (key === undefined || state.cols.has(key)) return false;
    state.cols.add(key);
    return true;
  };

  if (state.sort !== null) showFor(state.sort.column);

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
      /* Frozen with the name beside it. Once the table is wider than the screen,
       * a row scrolled halfway along is a line of fills with nothing at the left
       * saying whose they are. */
      frozen: true,
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
      frozen: true,
      widthGrow: 3,
      minWidth: 230,
      formatter: (cell) => {
        const d = cell.getRow().getData();
        return `<a class="dataset" href="${datasetHref(d)}">` +
          `<span class="collection-part">${esc(d.collection)}:</span><wbr>` +
          `${breakable(d.dataset_name)}</a>`;
      },
    },
    ...OPTIONAL_COLUMNS
      .filter((entry) => entry.key !== "checks")
      .map((entry) => ({ ...defs[entry.key], visible: state.cols.has(entry.key) })),
    ...bands.map((band) => ({
      title: copy.bands[band.kind] ?? band.kind,
      headerHozAlign: "center",
      cssClass: "check-band",
      columns: band.columns.map(
        (column) => ({ ...column, visible: state.cols.has("checks") })),
    })),
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
    /* The panel is a child of the row, so a click inside it is a click on the
     * row as far as Tabulator is concerned -- and the row closed under whatever
     * the reader had just reached into it for. Selecting a species name,
     * following a flag chip's tooltip, or missing a link by three pixels all
     * shut the thing being read. The line in the table opens and closes it;
     * what it opens onto is not a second copy of that control.
     *
     * A click on a link is a click on the link, not on the row. The disclosure
     * button is not excluded: pressing it with Enter or the space bar dispatches
     * a click that arrives here, which is how the panel opens from the keyboard.
     */
    if (event.target.closest(".panel")) return;
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
    if (state.jointMin !== null && (d.joint_auroc ?? -1) < state.jointMin) return false;
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
    if (state.jointMin !== null) {
      list.push({
        field: copy.filters.joint_over,
        value: state.jointMin.toFixed(3),
        undo: () => { state.jointMin = null; },
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
      } else if (name === "joint_min") {
        if (state.jointMin !== Number.parseFloat(values[0])) return false;
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
    paintDrawer();
    // The two figures under the table are about the rows the table is showing,
    // so they are redrawn from the same predicate rather than from whatever
    // Tabulator happens to have finished filtering.
    if (explore !== null) explore.update(rows.filter(matches));
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
    box.className = "facet";
    box.innerHTML = `<legend>${esc(copy.columns[field] ?? field)}</legend>`;
    /* The options go in a box of their own rather than straight into the
     * fieldset. The long facets scroll, and a `legend` inside the element that
     * scrolls goes with it: seventeen species names with nothing left on screen
     * saying they are species. The heading stays, the list under it moves. */
    const list = document.createElement("div");
    list.className = "facet-list";
    box.appendChild(list);
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
      list.appendChild(label);
    }
    facetHolder.appendChild(box);
  }

  /* -------------------------------------------------------------- drawer --- */

  /* The facets are the tallest thing in this panel and the least often reached
   * for: most readers sort a column, type into the search, or take a quick
   * view. So they ship closed, behind one button, and what stays on show is the
   * state -- the quick views, the chips, the count of rows.
   *
   * The button carries the number of boxes that are ticked. A closed drawer can
   * be narrowing the table, and while the chips above say which conditions
   * those are, the button is the only thing that can say there is anything
   * inside it at all.
   *
   * It does not open itself for a reader who arrives on a filtered link. That
   * reader followed the link to see rows, and the chips already state which
   * subset they are looking at; opening six groups of checkboxes over the top
   * would push the rows they came for down the page. */

  const facetToggle = document.getElementById("facet-toggle");

  const paintDrawer = () => {
    const on = Object.values(state.facets).reduce((total, set) => total + set.size, 0);
    facetToggle.innerHTML =
      `<span class="drawer-caret" aria-hidden="true"></span>` +
      `<span>${esc(copy.filters.drawer)}</span>` +
      (on > 0 ? `<span class="drawer-count">${num(on)}</span>` : "");
    /* The count is a glyph set beside the word, so the accessible name says it
     * in words rather than leaving a screen reader to read out "Filter by
     * column 2" and let the listener work out what the 2 was counting. */
    if (on > 0) {
      facetToggle.setAttribute("aria-label", copy.filters.drawer_count.replace("{n}", num(on)));
    } else {
      facetToggle.removeAttribute("aria-label");
    }
  };

  facetToggle.addEventListener("click", () => {
    const open = facetHolder.hidden;
    facetHolder.hidden = !open;
    facetToggle.setAttribute("aria-expanded", String(open));
  });
  // Nothing to open if no column had two values to choose between.
  facetToggle.hidden = facetHolder.children.length === 0;
  paintDrawer();

  /* ------------------------------------------------------------- columns --- */

  /* The picker: which columns are on screen, in the open above the table rather
   * than behind a menu on it. Two reasons for that rather than Tabulator's own
   * column menu -- what is available to add is visible without a click, and what
   * is already added is visible without a memory. The set is written into the
   * address with the filters and the sort, so a table someone else set up the
   * way they read it arrives set up that way.
   */

  const picker = document.getElementById("picker");
  const pickerList = document.getElementById("picker-list");
  const pickerReset = document.getElementById("picker-reset");

  const paintPicker = () => {
    for (const input of pickerList.querySelectorAll("input")) {
      input.checked = state.cols.has(input.dataset.col);
    }
    // Nothing to reset to while this *is* the set the table opens with.
    pickerReset.hidden = sameColumns(state.cols, DEFAULT_COLUMNS);
  };

  const applyColumns = () => {
    /* Thirteen entries, and up to ten columns behind one of them. Left to
     * itself Tabulator would recalculate every width once per column; blocking
     * the redraw makes the whole change one relayout. */
    table.blockRedraw();
    for (const entry of OPTIONAL_COLUMNS) {
      const on = state.cols.has(entry.key);
      for (const field of fieldsOfKey(entry.key)) {
        if (on) table.showColumn(field); else table.hideColumn(field);
      }
    }
    table.restoreRedraw();
    paintPicker();
    // After the relayout, not during it: the widths the scroller reads are the
    // ones the browser has actually laid out.
    window.requestAnimationFrame(measureTable);
    writeState(state);
  };

  for (const entry of OPTIONAL_COLUMNS) {
    const label = document.createElement("label");
    label.innerHTML =
      `<input type="checkbox" id="col-${esc(entry.key)}" data-col="${esc(entry.key)}"> ` +
      `${esc(copy.columns[entry.key] ?? entry.key)}`;
    const help = copy.column_help[entry.key];
    if (help !== undefined) label.title = help;
    label.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) state.cols.add(entry.key);
      else state.cols.delete(entry.key);
      applyColumns();
    });
    pickerList.appendChild(label);
  }

  pickerReset.addEventListener("click", () => {
    state.cols = new Set(DEFAULT_COLUMNS);
    applyColumns();
  });

  paintPicker();
  picker.hidden = false;

  /* ------------------------------------------------------------ sideways --- */

  /* Once enough columns are on, the table is wider than the screen. A wheel and
   * a trackpad can already move it; these two buttons are for the pointer that
   * has neither, and for the keyboard, which otherwise has no way at all to
   * reach a column off the right-hand edge. They appear only when there is
   * something off the edge to reach.
   */

  const scroller = document.getElementById("scroller");
  const goLeft = document.getElementById("scroll-left");
  const goRight = document.getElementById("scroll-right");
  const tableBox = document.getElementById("table");
  const holderOf = () => tableBox.querySelector(".tabulator-tableholder");

  const measureTable = () => {
    const box = holderOf();
    if (box === null) return;
    /* The panel a row opens is a child of that row, so it is as wide as every
     * column put together -- and at any scroll position but the first it opens
     * off the left of the screen. It is pinned there instead, and this is the
     * width it is pinned to: what the reader can see, not what the table
     * measures. */
    tableBox.style.setProperty("--table-view", `${box.clientWidth}px`);

    const over = box.scrollWidth - box.clientWidth;
    // A pixel of overflow is a rounding error, not a column off the edge.
    scroller.hidden = over <= 1;
    goLeft.disabled = box.scrollLeft <= 0;
    goRight.disabled = box.scrollLeft >= over - 1;
  };

  const nudge = (direction) => {
    const box = holderOf();
    if (box === null) return;
    // Most of a screenful rather than all of it, so the column that was at the
    // edge is still on screen to compare the new ones against.
    const step = Math.max(180, Math.round(box.clientWidth * 0.7));
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.scrollBy({ left: direction * step, behavior: still ? "auto" : "smooth" });
  };

  goLeft.addEventListener("click", () => nudge(-1));
  goRight.addEventListener("click", () => nudge(1));
  window.addEventListener("resize", measureTable);

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
    state.jointMin = null;
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
          } else if (name === "joint_min") {
            state.jointMin = Number.parseFloat(values[0]);
          } else if (name === "sort") {
            const [column, dir] = values[0].split(":");
            // Two of the four views sort by a column that is off by default.
            if (showFor(column)) applyColumns();
            table.setSort(column, dir);
          }
        }
      }
      apply();
    });
    presetHolder.appendChild(button);
  }

  /* ------------------------------------------------------------- figures --- */

  /* `assets/explore.js` draws; this decides what the table is showing. Selecting
   * a segment of the flags figure sets the same two parameters a link from the
   * checks page arrives on, and selecting the segment that is already the filter
   * takes it off again -- so the figure is a way in and a way back out.
   *
   * Guarded on the function existing, because the figures are an addition to
   * this page rather than a part of it: if the file is not loaded the table
   * behaves exactly as it did.
   */
  const explore = typeof buildExplore === "function"
    ? buildExplore(document_, copy, (check, flag) => {
        const same = state.check === check && state.flag === flag;
        state.check = same ? null : check;
        state.flag = same ? null : flag;
        apply();
      })
    : null;

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
    const box = holderOf();
    if (box !== null) box.addEventListener("scroll", measureTable, { passive: true });
    measureTable();
    apply();
  });
  table.on("dataFiltered", () => {
    counter.textContent = copy.filters.shown
      .replace("{shown}", num(table.getDataCount("active")))
      .replace("{total}", num(rows.length));
  });
}

loadCatalogue().then((document_) => build(document_, readJson("site-copy")));
