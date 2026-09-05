/* Move the boundaries, and watch which flags depend on them.
 *
 * "Your thresholds are arbitrary" is the first thing anyone says about a flag,
 * and it is not answerable with a paragraph. It is answerable by handing the
 * reader the boundaries and letting them watch 930 cells recolour: the flags
 * that move when you move the line were near it, and the ones that do not were
 * not.
 *
 * **Nothing here re-runs a check.** Every value it compares against a boundary
 * was published by the run and is written on the cell it belongs to -- a probe's
 * AUROC on the reference split, the leakage scan's worst share. Moving a slider
 * re-decides a flag from a number this run measured; it does not recompute the
 * number. That is the same constraint the manuscript's own threshold-sensitivity
 * analysis works under, and it is why three things are held fixed here and said
 * to be held fixed:
 *
 *   the integrity checks   duplicate sequences within a class, duplicate
 *                          sequences across classes, and the alphabet check are
 *                          not decided by a boundary on a scale. There is no
 *                          slider that could move them and no number on the cell
 *                          to move against.
 *   Unknown                a check that could not be scored has no value. It
 *                          stays Unknown at every setting, because a slider that
 *                          could turn it into a Pass would be turning an absence
 *                          of measurement into a result.
 *   a blank                a check with nothing to run on stays blank, for the
 *                          same reason and more so.
 *
 * The page says, whenever a boundary has been moved, that what is on screen is
 * not the shipped setting. A reader who arrives at someone else's screen, or at
 * their own an hour later, should not have to remember.
 *
 * Every word comes from the `#site-copy` block in the page. `tools/vocab_check.py`
 * scans `docs/` for prose and a `.js` file is not prose to it, so a label written
 * here would slip past the vocabulary check.
 */

(function thresholds() {
  const panel = document.getElementById("thresholds");
  if (panel === null) return;
  if (typeof matrixView === "undefined" || matrixView === null) return;

  const holder = document.getElementById("site-copy");
  if (holder === null) return;
  const words = JSON.parse(holder.textContent).thresholds;

  /* What the run shipped. Read off the panel rather than written here, so the
   * page and the script cannot come to disagree about which setting is the
   * published one -- and so that a change to the tool's boundaries moves one
   * value in `site.py` rather than one there and one here. */
  const SHIPPED = {
    warn: Number(panel.dataset.warn),
    fail: Number(panel.dataset.fail),
    leak: Number(panel.dataset.leak),
  };

  const state = { ...SHIPPED };

  const controls = {
    warn: document.getElementById("th-warn"),
    fail: document.getElementById("th-fail"),
    leak: document.getElementById("th-leak"),
  };
  const outputs = {
    warn: document.getElementById("th-warn-out"),
    fail: document.getElementById("th-fail-out"),
    leak: document.getElementById("th-leak-out"),
  };
  const summary = document.getElementById("th-summary");
  const banner = document.getElementById("th-banner");
  const reset = document.getElementById("th-reset");

  const fmt = (value, places) => value.toFixed(places);

  /** The flag a value would be given at the current setting.
   *
   * A probe is two boundaries on one AUROC. The leakage scan is one: any
   * detected match is a Warning and the Fail boundary is a share, which is how
   * the tool decides it -- so a leakage cell never returns Pass unless nothing
   * was found at all.
   */
  function decide(check, auroc, leaked) {
    if (auroc !== null) {
      if (auroc > state.fail) return "Fail";
      if (auroc > state.warn) return "Warning";
      return "Pass";
    }
    if (leaked !== null) {
      if (leaked >= state.leak) return "Fail";
      if (leaked > 0) return "Warning";
      return "Pass";
    }
    return null;
  }

  const moved = () =>
    state.warn !== SHIPPED.warn
    || state.fail !== SHIPPED.fail
    || state.leak !== SHIPPED.leak;

  /** Re-tally the corpus at the current setting.
   *
   * Counted off the cells the grid is showing, not off a second copy of the
   * catalogue: the count under the grid and the colours in it are then two
   * readings of one set of elements, and cannot disagree.
   *
   * A dataset's rollup is the worst flag over its ten cells, with `Unknown` left
   * out of the ordering -- exactly as `audit.py` rolls one up, and for the same
   * reason. A check that could not be scored is neither worse than a Warning nor
   * better than a Pass, and folding it into the order would let it be summarised
   * away.
   */
  function tally() {
    const severity = { Pass: 0, Warning: 1, Fail: 2 };
    const worst = { Pass: 0, Warning: 0, Fail: 0 };
    for (const row of matrixView.rows()) {
      let top = null;
      for (const cell of row.cells) {
        const published = cell.dataset.flag;
        if (published === undefined || published === "Unknown") continue;
        const auroc = cell.dataset.auroc;
        const leaked = cell.dataset.leaked;
        const flag =
          auroc === undefined && leaked === undefined
            ? published
            : decide(
                cell.dataset.check,
                auroc === undefined ? null : Number(auroc),
                leaked === undefined ? null : Number(leaked),
              );
        if (top === null || severity[flag] > severity[top]) top = flag;
      }
      if (top !== null) worst[top] += 1;
    }
    return worst;
  }

  function apply() {
    outputs.warn.textContent = fmt(state.warn, 2);
    outputs.fail.textContent = fmt(state.fail, 2);
    outputs.leak.textContent = `${fmt(state.leak, 1)}%`;

    matrixView.recolour(moved() ? decide : null);

    const worst = tally();
    summary.textContent = words.summary
      .replace("{pass}", String(worst.Pass))
      .replace("{warning}", String(worst.Warning))
      .replace("{fail}", String(worst.Fail));

    banner.hidden = !moved();
    reset.hidden = !moved();
    panel.classList.toggle("is-moved", moved());
  }

  /* The Fail boundary cannot sit below the Warning boundary: "Warning above
   * 0.70, Fail above 0.60" is not a stricter setting, it is an unreadable one.
   * The two sliders push each other rather than refusing, so dragging either one
   * past the other does something predictable instead of sticking. */
  controls.warn.addEventListener("input", () => {
    state.warn = Number(controls.warn.value);
    if (state.fail < state.warn) {
      state.fail = state.warn;
      controls.fail.value = String(state.fail);
    }
    apply();
  });
  controls.fail.addEventListener("input", () => {
    state.fail = Number(controls.fail.value);
    if (state.warn > state.fail) {
      state.warn = state.fail;
      controls.warn.value = String(state.warn);
    }
    apply();
  });
  controls.leak.addEventListener("input", () => {
    state.leak = Number(controls.leak.value);
    apply();
  });

  reset.addEventListener("click", () => {
    Object.assign(state, SHIPPED);
    for (const key of ["warn", "fail", "leak"]) {
      controls[key].value = String(SHIPPED[key]);
    }
    apply();
  });

  panel.hidden = false;
  apply();
})();
