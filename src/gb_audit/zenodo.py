"""Where the QC output is published, and how to reach it.

What lives on the record is the half of the run too large to commit: the 93 report
archives (90 MB) and `combined_classes_results_full.csv` (343 MB, 2.59 M rows).
This module is the only place in the repository that knows its address, and it is
not on the path that renders a page.

**The record is published.** Record `22288544`, DOI `10.5281/zenodo.22288544`,
holds all 96 files and resolves for a reader with no token. `RECORD_REGISTERED`
answers the question a link on a public page has to answer; pages that would need
a published record say so rather than linking into a 404 if it is ever False.

**The record is the only source.** Nothing here reads a local checkout: the
regeneration script and `gb-audit fetch` both download from it.

**The committed tables and the record are two routes to the same bytes**, checked
rather than assumed -- `data/provenance.json` carries a SHA-256 per file and both
match the record's copies. `data/reports.csv` does the same for the 93 archives.
"""

from __future__ import annotations

import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# The record the QC output is deposited to, and the concept record that will
# resolve to its latest version. Kept identical to
# `genomic_benchmarks_data._core.qc._QC_ZENODO_RECORD_ID` so that the two
# repositories cannot end up naming different records for one run.
RECORD_ID = "22288544"
CONCEPT_RECORD_ID = "22288543"

# Whether the record resolves for a reader with no token. Not "whether it exists".
RECORD_REGISTERED = True

# Minted by Zenodo on publication, for this version of the record.
DOI = "10.5281/zenodo.22288544"

# The version label the record was published with. Each version of a Zenodo
# record is a record of its own, so this is fixed for `RECORD_ID`.
VERSION = "1.0.0"

BASE_URL = f"https://zenodo.org/records/{RECORD_ID}"
API_URL = f"https://zenodo.org/api/records/{RECORD_ID}"

# The two summary tables, which are also committed under `data/`.
SUMMARY_TABLES = ("combined_classes_results.csv", "combined_splits_results.csv")

# The one table that is not committed anywhere: 2.59 M rows at 343 MB. Named here
# because a reader who wants the per-position numbers behind a probe needs to be
# told where they are, and this module is where file names live.
FULL_TABLE = "combined_classes_results_full.csv"

# Zenodo answers a share of requests with a 502 or 504 that succeeds when asked
# again, so a server error is retried before it is reported.
ATTEMPTS = 3

class RecordUnavailable(RuntimeError):
    """The QC record cannot be reached, and the message says which reason.

    Two of them, and they are not the same problem: the record is not
    published, or the network refused.
    """


def registered() -> bool:
    """Whether `RECORD_ID` resolves for a reader who has no token.

    This is the question a link on a public page has to answer.
    """
    return RECORD_REGISTERED


def public_record_url() -> str:
    """The landing page a reader can open, as the site prints it."""
    return BASE_URL


def file_url(name: str) -> str:
    """The address of one file on the record: the API's `content` endpoint."""
    quoted = urllib.parse.quote(name, safe="")
    return f"{API_URL}/files/{quoted}/content"


def archive_name(collection: str, dataset_name: str) -> str:
    """The report archive for one dataset.

    `<collection>-<dataset>.zip`, which is also the name of the single directory
    inside it. The record is flat, so the filename is the only thing telling 93
    archives apart, and `genomic_benchmarks_data` composes exactly this name.
    """
    return f"{collection}-{dataset_name}.zip"


def route() -> str:
    """Whether a fetch would reach the record right now, without fetching.

    So that a caller can print the answer before spending 90 MB finding it out,
    and so `--dry-run` says something true.
    """
    if registered():
        return "zenodo"
    return "unavailable"


def fetch(name: str, destination: Path, *, timeout: float = 60.0) -> Path:
    """One published file, downloaded from the record to `destination`."""
    if route() == "unavailable":
        raise RecordUnavailable(
            f"cannot fetch {name!r}: Zenodo record {RECORD_ID} is not published, "
            f"so {API_URL}/files/... does not answer."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    url = file_url(name)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                with destination.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
            return destination
        except urllib.error.HTTPError as exc:
            destination.unlink(missing_ok=True)
            if exc.code >= 500 and attempt < ATTEMPTS:
                time.sleep(attempt)
                continue
            raise RecordUnavailable(
                f"fetching {name!r} from record {RECORD_ID} failed: HTTP {exc.code} "
                f"{exc.reason}, after {attempt} attempt(s)."
            ) from exc
        except urllib.error.URLError as exc:
            # Unlinked rather than left behind: a partial download that keeps its
            # name is a file the next run will find, check nothing about, and unpack.
            destination.unlink(missing_ok=True)
            raise RecordUnavailable(
                f"fetching {name!r} from record {RECORD_ID} failed: {exc.reason}"
            ) from exc
    raise AssertionError("unreachable")
