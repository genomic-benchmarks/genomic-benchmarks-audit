/* Two addresses that were published and no longer hold a page.
 *
 *   catalogue.html   the datasets table, now a section of the overview, which is
 *                    where a reader looking for the data was always going to look
 *                    first. Its query string comes across: a filtered view of that
 *                    table was something this site told people they could send to
 *                    a colleague, so `catalogue.html?collection=BEACON&flag=Fail`
 *                    is a link that exists in other people's notes and should
 *                    still land on those rows.
 *   reports.html     an index of all 423 reports, now listed on the dataset each
 *                    one belongs to. Its query string does not come across --
 *                    those filters narrowed a table that no longer exists, and
 *                    carrying them would be carrying them nowhere -- so it lands
 *                    on the datasets table itself.
 *
 * The destination is read from the visible link rather than written here, so the
 * page a reader without scripting is sent to and the page this file sends them to
 * cannot come apart. Whether the query comes with them is the one thing the page
 * has to say, and it says it as `data-query="keep"`.
 *
 * `replace` rather than `assign`, so the back button goes where the reader came
 * from rather than to a page that immediately forwards them again.
 *
 * Each page renders a working link to the same place first, and this only makes
 * the trip automatic. With scripting off, or if this file never loads, the reader
 * gets a sentence saying where it went and a link that goes there -- which is the
 * whole behaviour, minus the convenience.
 */

(function forward() {
  const link = document.getElementById("forward");
  if (link === null) return;

  const [path, hash] = link.getAttribute("href").split("#");
  const query = link.dataset.query === "keep" ? window.location.search : "";
  const target = `${path}${query}${hash === undefined ? "" : `#${hash}`}`;

  // The visible link carries the query too, so a reader who lands here with
  // scripting off is not silently dropped onto 93 unfiltered rows.
  link.setAttribute("href", target);
  window.location.replace(target);
})();
