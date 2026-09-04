/* The flag matrix's filter: two groups of chips over rows already on the page.
 *
 * Nothing is fetched, nothing is rebuilt, and no row is created here. `site.py`
 * wrote all 93 of them with a `data-collection` and a `data-verdict`, and this
 * file only decides which are `hidden`. That is deliberate: a filter that
 * re-renders rows from a second copy of the catalogue is a filter that can
 * disagree with the page it is filtering.
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

  /* One set per group. Empty means "no condition from this group", which is what
   * makes the first click a narrowing and not a switch: a reader who wants two
   * collections gets both rather than the second one only. */
  const chosen = { collection: new Set(), verdict: new Set() };

  const matches = (row) =>
    (chosen.collection.size === 0 || chosen.collection.has(row.dataset.collection)) &&
    (chosen.verdict.size === 0 || chosen.verdict.has(row.dataset.verdict));

  function apply() {
    let shown = 0;
    for (const body of bodies) {
      let visible = 0;
      for (const row of body.querySelectorAll("tr[data-collection]")) {
        const keep = matches(row);
        row.hidden = !keep;
        if (keep) visible += 1;
      }
      // The collection's own heading row goes with its members. Hiding the whole
      // `<tbody>` would take the heading too, but leaves the element in the
      // accessibility tree on some engines, so the rows are set individually and
      // the group line is set with them.
      const group = body.querySelector(".mx-groupline");
      if (group !== null) group.hidden = visible === 0;
      shown += visible;
    }

    const narrowed = chosen.collection.size > 0 || chosen.verdict.size > 0;
    countOut.textContent = words.shown
      .replace("{shown}", String(shown))
      .replace("{total}", String(total));
    clear.hidden = !narrowed;
    empty.hidden = shown > 0;
    // Scrolling a region that is now shorter than the scroll position leaves a
    // reader looking at blank space below the last row.
    if (narrowed) figure.querySelector(".mx-scroll").scrollTop = 0;
  }

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
  apply();
})();
