/* Two figures over the rows the catalogue table is currently showing.
 *
 * The table answers "which datasets", one row at a time. These answer the two
 * questions a reader has *about a set of rows* -- which checks flagged them, and
 * how far one feature got on them -- and they answer it about whatever the
 * filters have left, not about the corpus. Narrow to a collection and the shape
 * of that collection is on screen; narrow to one species and so is that.
 *
 * Nothing here is a second copy of the audit. Every count is tallied from the
 * same `datasets` array the table is filtering, so a figure and the row count
 * above it cannot disagree: if they ever did, one of them would be reading a
 * different document.
 *
 * **The first figure is also a control.** Selecting a segment is the same thing
 * as arriving from the checks page on `?check=…&flag=…` -- it sets the filter
 * the table already has, which lands in the address bar with the rest. A figure
 * that can only be looked at, sitting above a table that can be filtered, is a
 * picture of a question the reader then has to re-ask in the search box.
 *
 * Drawn as SVG in the page rather than fetched from a chart library, for the
 * reason `charts.py` gives: this site has no build step and one 40 KB dependency
 * for two figures is a dependency an archived copy has to keep answering for.
 * The palette is the grid's -- read from the stylesheet, so there is one list of
 * flag colours on this site and not three.
 *
 * Every word comes from the `#site-copy` block in the page. `tools/vocab_check.py`
 * scans `docs/` for prose and a `.js` file is not prose to it, so a label written
 * here would slip past the vocabulary check.
 */

/* Wrapped, unlike the two scripts either side of it. `site.js` puts its helpers
 * in the global scope on purpose -- `flagSpan` and `panelHtml` are shared with
 * the catalogue's script and are named for what they are. The names in here are
 * `text`, `legend`, `median`, `chart`: a drawing vocabulary, and exactly the
 * words a library loaded on the same page is likely to want. One export, and the
 * rest stays inside.
 */
(function explore() {

  /* The AUROC axis, and the mark on it. 0.5 is a feature that says nothing about
   * the classes and is where the scale starts; 0.7 is the Core Set's cut and is
   * drawn as a line rather than as a boundary between two colours, because it
   * selects datasets and does not describe them. Both match the histogram on the
   * checks page, so the same value sits at the same place on both. */
  const AUROC_LO = 0.5;
  const AUROC_HI = 1.0;
  const AUROC_CUT = 0.7;

  const FLAG_ORDER = ["Pass", "Warning", "Fail", "Unknown"];

  /** The flag fills, read from the stylesheet rather than repeated here.
   *
   * `--flag-fill-*` is where `charts.py` writes its palette for the HTML side of
   * the site, and the grid on the landing page draws from it. A second list in
   * this file would be a third place to change a colour in.
   */
  function flagFills() {
    const style = getComputedStyle(document.documentElement);
    const read = (name) => style.getPropertyValue(`--flag-fill-${name}`).trim();
    return {
      Pass: read("pass"),
      Warning: read("warning"),
      Fail: read("fail"),
      Unknown: read("unknown"),
    };
  }

  /* ------------------------------------------------------------ primitives --- */

  const svgEsc = (value) =>
    String(value).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const f1 = (value) => value.toFixed(1);

  /** A responsive, labelled SVG, laid out in its viewBox exactly as `_svg` does. */
  function chart(width, height, title, desc, body, defs = "") {
    return (
      `<svg class="chart" viewBox="0 0 ${width} ${height}" width="100%" height="auto" ` +
      `preserveAspectRatio="xMinYMin meet" role="img" xmlns="http://www.w3.org/2000/svg">` +
      `<title>${svgEsc(title)}</title><desc>${svgEsc(desc)}</desc>${defs}${body}</svg>`
    );
  }

  const text = (x, y, content, cls = "lab", anchor = "start") =>
    `<text class="${cls}" x="${f1(x)}" y="${f1(y)}" text-anchor="${anchor}">${svgEsc(content)}</text>`;

  const gridline = (x1, y1, x2, y2) =>
    `<line x1="${f1(x1)}" y1="${f1(y1)}" x2="${f1(x2)}" y2="${f1(y2)}" ` +
    `stroke="#e6eae9" stroke-width="1" shape-rendering="crispEdges"/>`;

  /** The `Unknown` texture, with an id of its own.
   *
   * `charts.py` names its pattern `unknown-hatch` and there is already one of those
   * on this page, inside another figure. Two `<defs>` under one id is a document
   * where which hatch you get depends on which figure the browser parsed last.
   */
  const HATCH = "explore-hatch";
  const hatchDef = (ink) =>
    `<defs><pattern id="${HATCH}" width="6" height="6" patternUnits="userSpaceOnUse" ` +
    `patternTransform="rotate(45)"><rect width="6" height="6" fill="#ffffff"/>` +
    `<line x1="0" y1="0" x2="0" y2="6" stroke="${ink}" stroke-width="1.4" opacity="0.55"/>` +
    `</pattern></defs>`;

  /** A key: the swatch and the word, in the order severity runs. */
  function legend(x, y, fills, copy, flags) {
    const parts = [];
    let cursor = x;
    for (const flag of flags) {
      const fill = flag === "Unknown"
        ? `url(#${HATCH})" stroke="${fills.Unknown}" stroke-width="1`
        : fills[flag];
      parts.push(
        `<rect x="${f1(cursor)}" y="${f1(y - 8)}" width="10" height="10" rx="2" fill="${fill}"/>`);
      parts.push(text(cursor + 15, y, copy.flags[flag], "leg"));
      cursor += 26 + copy.flags[flag].length * 5.6;
    }
    return parts.join("");
  }

  /** The table twin a figure ships under a disclosure, in the shape
   * `charts.render` gives the server-drawn ones: the same values as text. The
   * twin is not a fallback -- a reader after the number should not have to hover
   * 930 marks to get it. */
  function foot(headers, rows, tableCaption, copy) {
    const head = headers.map((h, i) =>
      `<th scope="col"${i ? ' class="right"' : ""}>${svgEsc(h)}</th>`).join("");
    const body = rows.map((row) =>
      "<tr>" + row.map((cell, i) =>
        i ? `<td class="right">${svgEsc(cell)}</td>` : `<th scope="row">${svgEsc(cell)}</th>`)
        .join("") + "</tr>").join("");
    return (
      `<figcaption>` +
      `<details class="fig-table"><summary>${svgEsc(copy.explore.table_view)}</summary>` +
      `<table><caption>${svgEsc(tableCaption)}</caption><thead><tr>${head}</tr></thead>` +
      `<tbody>${body}</tbody></table></details></figcaption>`
    );
  }

  const fill = (template, values) =>
    Object.entries(values).reduce((out, [k, v]) => out.replaceAll(`{${k}}`, String(v)), template);

  /* -------------------------------------------------------- flags by check --- */

  /** How the visible rows came out on each of the ten checks, as one bar each.
   *
   * The checks stay in the order the grid puts its columns in, and are not
   * re-sorted by how broadly they flagged: a figure that reorders itself on every
   * keystroke is one a reader has to re-find their row in each time they type.
   */
  function checkFigure(rows, checks, fills, copy) {
    const labelW = 250;
    const plotW = 500;
    const rowH = 20;
    const pitch = 30;
    const top = 42;
    const bottom = 46;
    const width = labelW + plotW + 96;
    const height = top + checks.length * pitch + bottom;
    const total = rows.length;

    const body = [];
    for (let tick = 0; tick <= 100; tick += 25) {
      const x = labelW + (plotW * tick) / 100;
      body.push(gridline(x, top - 8, x, top + checks.length * pitch - 10));
      body.push(text(x, top - 14, `${tick}%`, "tick", "middle"));
    }
    body.push(text(labelW + plotW / 2, 13, fill(copy.explore.flags_axis, { n: total }), "axis", "middle"));

    /* Whether the legend names `Unknown`. Asked of the rows rather than assumed:
     * a filtered view where nothing went unscored should not carry a key to a
     * fill it is not showing. */
    let anyUnknown = false;
    checks.forEach((check, index) => {
      const y = top + index * pitch;
      const flags = rows.map((d) => d.flags[check.name] ?? null);
      const counts = {};
      for (const flag of FLAG_ORDER) counts[flag] = flags.filter((f) => f === flag).length;
      if (counts.Unknown) anyUnknown = true;

      body.push(text(labelW - 12, y + rowH - 5, check.name, "rowlab", "end"));
      let cursor = labelW;
      for (const flag of FLAG_ORDER) {
        const n = counts[flag];
        if (!n) continue;
        const w = (plotW * n) / total;
        const tip = fill(copy.explore.flags_tip, {
          check: check.name, n, total, flag: copy.flags[flag],
        });
        const paint = flag === "Unknown"
          ? `fill="url(#${HATCH})" stroke="${fills.Unknown}" stroke-width="1"`
          : `fill="${fills[flag]}"`;
        body.push(
          `<rect class="cell hit" x="${f1(cursor)}" y="${f1(y)}" width="${f1(Math.max(w - 2, 1))}" ` +
          `height="${rowH}" rx="2" ${paint} data-tip="${svgEsc(tip)}" tabindex="0" role="button" ` +
          `data-check="${svgEsc(check.name)}" data-flag="${svgEsc(flag)}" ` +
          `aria-label="${svgEsc(tip)}"/>`);
        cursor += w;
      }
      const flagged = counts.Warning + counts.Fail;
      body.push(text(labelW + plotW + 10, y + rowH - 5, `${flagged}/${total}`, "val"));
    });

    body.push(legend(labelW, height - 14, fills, copy,
      anyUnknown ? FLAG_ORDER : ["Pass", "Warning", "Fail"]));

    return chart(width, height, copy.explore.flags_title,
      fill(copy.explore.flags_desc, { n: total, checks: checks.length }),
      body.join(""), hatchDef(fills.Unknown));
  }

  /* -------------------------------------------------------- probes by check --- */

  /** A small deterministic offset, so overlapping marks separate the same way
   * every redraw. Derived from the slug rather than drawn at random: a dot that
   * moves when the reader types is a dot they cannot follow. */
  function jitter(slug) {
    let hash = 0;
    for (let i = 0; i < slug.length; i += 1) hash = (hash * 31 + slug.charCodeAt(i)) % 100003;
    return (hash % 1000) / 1000 - 0.5;
  }

  const median = (values) => {
    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  };

  /** Every probe against every visible dataset: one mark per dataset per feature.
   *
   * `max_probe_auroc` -- the column in the table, and the histogram on the checks
   * page -- is the strongest of the six on each dataset, and it cannot say *which*
   * of the six it was for more than one dataset at a time. This can: a row that
   * sits to the right is a feature that separates these classes across this set of
   * rows, which is the thing a reader would otherwise open datasets one at a time
   * to find out.
   *
   * Every mark is a link to that dataset, on the grid's principle. The colour is
   * the flag that check returned, so the two figures share one key.
   */
  function probeFigure(rows, probes, fills, copy, root) {
    const labelW = 250;
    const plotW = 500;
    const band = 26;
    const pitch = 32;
    const top = 44;
    const bottom = 48;
    const width = labelW + plotW + 96;
    const height = top + probes.length * pitch + bottom;
    const x = (value) => labelW + (plotW * (value - AUROC_LO)) / (AUROC_HI - AUROC_LO);

    const body = [];
    for (let tick = AUROC_LO; tick <= AUROC_HI + 1e-9; tick += 0.1) {
      body.push(gridline(x(tick), top - 8, x(tick), top + probes.length * pitch - 8));
      body.push(text(x(tick), top - 14, tick.toFixed(1), "tick", "middle"));
    }
    body.push(text(labelW + plotW / 2, 13, copy.explore.probe_axis, "axis", "middle"));
    body.push(
      `<line x1="${f1(x(AUROC_CUT))}" y1="${top - 8}" x2="${f1(x(AUROC_CUT))}" ` +
      `y2="${top + probes.length * pitch - 8}" stroke="#4a5654" stroke-width="1" ` +
      `stroke-dasharray="3 3"/>`);
    body.push(text(x(AUROC_CUT), top + probes.length * pitch + 4, copy.explore.probe_cut, "sub", "middle"));

    const twinRows = [];
    probes.forEach((check, index) => {
      const y = top + index * pitch;
      const middle = y + band / 2;
      body.push(text(labelW - 12, middle + 4, check.name, "rowlab", "end"));

      const measured = [];
      const dots = [];
      for (const d of rows) {
        const value = d.probe_auroc?.[check.name];
        if (value === undefined || value === null) continue;
        measured.push(value);
        const flag = d.flags[check.name] ?? "Unknown";
        const cy = middle + jitter(d.slug) * (band - 9);
        const tip = fill(copy.explore.probe_tip, {
          dataset: d.benchmark_id, check: check.name,
          value: value.toFixed(3), flag: copy.flags[flag] ?? flag,
        });
        const paint = flag in fills && flag !== "Unknown"
          ? `fill="${fills[flag]}" fill-opacity="0.8"`
          : `fill="none" stroke="${fills.Unknown}" stroke-width="1.2"`;
        dots.push(
          `<a href="${svgEsc(root)}datasets/${encodeURIComponent(d.slug)}.html" ` +
          `aria-label="${svgEsc(tip)}"><circle class="dot" cx="${f1(x(value))}" cy="${f1(cy)}" ` +
          `r="3.4" ${paint} data-tip="${svgEsc(tip)}"/></a>`);
      }

      if (measured.length) {
        const mid = median(measured);
        const tip = fill(copy.explore.probe_median, {
          check: check.name, value: mid.toFixed(3), n: measured.length,
        });
        body.push(
          `<line class="median" x1="${f1(x(mid))}" y1="${f1(middle - band / 2)}" ` +
          `x2="${f1(x(mid))}" y2="${f1(middle + band / 2)}" stroke="#1c2321" stroke-width="2" ` +
          `data-tip="${svgEsc(tip)}" tabindex="0"/>`);
        body.push(...dots);
        body.push(text(labelW + plotW + 10, middle + 4, mid.toFixed(2), "val"));
        twinRows.push([check.name, measured.length, mid.toFixed(3),
          Math.max(...measured).toFixed(3),
          measured.filter((v) => v >= AUROC_CUT).length]);
      } else {
        body.push(...dots);
        twinRows.push([check.name, 0, "", "", ""]);
      }
    });

    body.push(legend(labelW, height - 14, fills, copy, ["Pass", "Warning", "Fail"]));

    const svg = chart(width, height, copy.explore.probe_title,
      fill(copy.explore.probe_desc, { n: rows.length, probes: probes.length }),
      body.join(""), hatchDef(fills.Unknown));
    return svg + foot(
      [copy.explore.col_check, copy.explore.col_measured, copy.explore.col_median,
        copy.explore.col_strongest, copy.explore.col_over_cut],
      twinRows, fill(copy.explore.probe_twin, { n: rows.length, cut: AUROC_CUT.toFixed(2) }), copy);
  }

  /* ------------------------------------------------------------------ wiring --- */

  /** Build both figures and return the handle the catalogue script redraws them by.
   *
   * `select` is how the first figure filters the table: it is handed the check and
   * the flag a segment stands for, and the caller turns that into the state the
   * URL already describes. This file sets no filter itself, so there is one place
   * that decides what the table is showing.
   */
  function buildExplore(document_, copy, select) {
    const section = document.getElementById("explore");
    if (section === null) return null;
    const flagsHolder = document.getElementById("explore-flags");
    const probesHolder = document.getElementById("explore-probes");
    const fills = flagFills();
    const probes = document_.checks.filter((c) => c.kind === "probe");
    // A catalogue from before probe AUROCs were carried per check -- one a browser
    // is holding in cache -- has the flags and not the numbers. The first figure
    // still draws; the second says nothing rather than drawing an empty axis.
    const hasProbes = document_.datasets.some((d) => d.probe_auroc);
    const root = document.body.dataset.root ?? "";

    flagsHolder.addEventListener("click", (event) => {
      const mark = event.target.closest("[data-check]");
      if (mark !== null) select(mark.dataset.check, mark.dataset.flag);
    });
    flagsHolder.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const mark = event.target.closest("[data-check]");
      if (mark === null) return;
      event.preventDefault();
      select(mark.dataset.check, mark.dataset.flag);
    });

    section.hidden = false;
    // Which rows were drawn last. The table calls `apply` on every keystroke and
    // on every sort, and most of those leave the same rows on screen -- a sort
    // reorders the table and changes neither figure. Redrawing 558 marks to
    // produce the same 558 marks is work the reader pays for in the search box.
    let drawn = null;

    return {
      update(rows) {
        const signature = `${rows.length}:${rows.map((d) => d.slug).join()}`;
        if (signature === drawn) return;
        drawn = signature;
        if (rows.length === 0) {
          const empty = `<p class="fig-empty">${svgEsc(copy.empty.no_rows)}</p>`;
          flagsHolder.innerHTML = empty;
          probesHolder.innerHTML = empty;
          return;
        }
        flagsHolder.innerHTML = checkFigure(rows, document_.checks, fills, copy);
        probesHolder.innerHTML = hasProbes
          ? probeFigure(rows, probes, fills, copy, root)
          : "";
        probesHolder.hidden = !hasProbes;
      },
    };
  }

  window.buildExplore = buildExplore;
})();
