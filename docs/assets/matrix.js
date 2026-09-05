/* The flag matrix: which rows are on screen, and what colour their cells are.
 *
 * Nothing is fetched, nothing is rebuilt, and no row is created here. `site.py`
 * wrote all 93 of them with a `data-id`, a `data-collection` and a
 * `data-verdict`, and this file only decides which are `hidden` and, when a
 * reader has moved a boundary, which class each cell carries. That is
 * deliberate: a grid that re-renders rows from a second copy of the catalogue is
 * a grid that can disagree with the page it is on.
 *
 * The grid appears on two pages and is driven differently on each:
 *
 *   the checks page   there is no table, so the grid carries its own chips --
 *                     one group of collections, one of flags -- exactly as it
 *                     always has.
 *   the overview      the datasets table is on the same page. Two filters over
 *                     one corpus, sitting a screen apart and disagreeing about
 *                     how many rows there are, is the thing that makes a page
 *                     confusing to be on. So the chips are not rendered, and
 *                     `catalogue.js` drives the grid through `showOnly` instead:
 *                     one filter, two views of its answer.
 *
 * The controls ship `hidden` from the build and are revealed here, so a reader
 * with scripting off gets the whole matrix and no buttons that do nothing.
 *
 * Every word comes from the `#site-copy` block in the page. `tools/vocab_check.py`
 * scans `docs/` for prose and a `.js` file is not prose to it, so a label written
 * here would slip past the vocabulary check.
 */

(function matrix() {
  const figure = document.getElementById("fig-flag-matrix");
  if (figure === null) return;

  const holder = document.getElementById("site-copy");
  if (holder === null) return;
  const copy = JSON.parse(holder.textContent);
  const words = copy.matrix;

  const controls = document.getElementById("matrix-controls");
  const countOut = document.getElementById("matrix-count");
  const clear = document.getElementById("matrix-clear");
  const empty = document.getElementById("matrix-empty");
  const bodies = [...figure.querySelectorAll("tbody")];
  const total = Number(figure.dataset.total);
  const rows = [...figure.querySelectorAll("tr[data-collection]")];

  /* Whether a table is driving this grid. Read from the page rather than passed
   * in, because it is a fact about which page this is and both pages load the
   * same file. */
  const driven = document.getElementById("table") !== null;

  /* One set per group. Empty means "no condition from this group", which is what
   * makes the first click a narrowing and not a switch: a reader who wants two
   * collections gets both rather than the second one only. */
  const chosen = { collection: new Set(), verdict: new Set() };

  const matches = (row) =>
    (chosen.collection.size === 0 || chosen.collection.has(row.dataset.collection)) &&
    (chosen.verdict.size === 0 || chosen.verdict.has(row.dataset.verdict));

  /* Set when a table is driving. `null` means "everything", which is not the same
   * as an empty set: an empty set is a filter that matched nothing, and drawing
   * the two the same way would show all 93 rows at the moment the reader had
   * narrowed to none. */
  let allowed = null;

  const keep = (row) =>
    driven
      ? allowed === null || allowed.has(row.dataset.id)
      : matches(row);

  function apply() {
    let shown = 0;
    for (const body of bodies) {
      let visible = 0;
      for (const row of body.querySelectorAll("tr[data-collection]")) {
        const on = keep(row);
        row.hidden = !on;
        if (on) visible += 1;
      }
      // The collection's own heading row goes with its members. Hiding the whole
      // `<tbody>` would take the heading too, but leaves the element in the
      // accessibility tree on some engines, so the rows are set individually and
      // the group line is set with them.
      const group = body.querySelector(".mx-groupline");
      if (group !== null) group.hidden = visible === 0;
      shown += visible;
    }

    const narrowed = driven
      ? allowed !== null && shown < total
      : chosen.collection.size > 0 || chosen.verdict.size > 0;
    countOut.textContent = words.shown
      .replace("{shown}", String(shown))
      .replace("{total}", String(total));
    if (clear !== null) clear.hidden = !narrowed;
    empty.hidden = shown > 0;
    // Scrolling a region that is now shorter than the scroll position leaves a
    // reader looking at blank space below the last row.
    if (narrowed) figure.querySelector(".mx-scroll").scrollTop = 0;
  }

  if (!driven && controls !== null) {
    for (const chip of controls.querySelectorAll(".mx-chip")) {
      chip.addEventListener("click", () => {
        const set = chosen[chip.dataset.facet];
        const on = set.has(chip.dataset.value);
        if (on) set.delete(chip.dataset.value);
        else set.add(chip.dataset.value);
        chip.setAttribute("aria-pressed", on ? "false" : "true");
        apply();
      });
    }

    clear.addEventListener("click", () => {
      chosen.collection.clear();
      chosen.verdict.clear();
      for (const chip of controls.querySelectorAll(".mx-chip")) {
        chip.setAttribute("aria-pressed", "false");
      }
      apply();
    });

    controls.hidden = false;
  } else if (controls !== null) {
    // The table above is the filter. Its own chips would be a second one.
    controls.remove();
  }

  apply();

  /* What the rest of the page can ask of the grid.
   *
   * `showOnly` is the table's filter arriving; `recolour` is a reader moving a
   * boundary. They are independent on purpose -- narrowing to one collection and
   * asking what its flags would be at a different threshold are two questions,
   * and answering one should not undo the other.
   */
  window.matrixView = {
    showOnly(ids) {
      allowed = ids === null ? null : new Set(ids);
      apply();
    },

    /** Repaint every re-decidable cell from a function of its own number.
     *
     * `decide` is handed the cell's published value and the check it belongs to,
     * and returns a flag name -- or `null` to put the cell back to what the run
     * published. Cells with no number are never passed to it: an integrity check
     * is not decided on a scale, and `Unknown` has no value to compare against.
     */
    recolour(decide) {
      for (const row of rows) {
        for (const cell of row.querySelectorAll(".mx-cell")) {
          const published = cell.dataset.flag;
          if (published === undefined) continue;
          const auroc = cell.dataset.auroc;
          const leaked = cell.dataset.leaked;
          if (auroc === undefined && leaked === undefined) continue;
          const flag =
            decide === null
              ? null
              : decide(
                  cell.dataset.check,
                  auroc === undefined ? null : Number(auroc),
                  leaked === undefined ? null : Number(leaked),
                );
          const shown = flag === null ? published : flag;
          cell.className = `mx-cell mx-${shown}${shown === published ? "" : " mx-moved"}`;
          const label = cell.querySelector(".sr-only");
          if (label !== null) label.textContent = shown;
        }
      }
    },

    /** Every row, as `{ id, collection, cells }`, for a script that has to count.
     *
     * Handed out rather than re-derived, so the thing counting the flags and the
     * thing showing them are reading one set of elements.
     */
    rows() {
      return rows.map((row) => ({
        id: row.dataset.id,
        collection: row.dataset.collection,
        hidden: row.hidden,
        cells: [...row.querySelectorAll(".mx-cell")],
      }));
    },
  };
})();
