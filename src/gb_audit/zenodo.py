"""Where the QC output is published, and how to reach it before it is published.

What lives on the record is the half of the run too large to commit: the 93 report
archives (90 MB) and `combined_classes_results_full.csv` (343 MB, 2.59 M rows).
This module is the only place in the repository that knows its address, and it is
not on the path that renders a page.

**The record is staged but not published, and those are different facts.** Record
`22288544` exists, holds all 96 files and is in state `unsubmitted`: reachable
through its draft endpoint with a share token, absent from `zenodo.org/records/`
without one. So `RECORD_ID` is a real identifier and `RECORD_REGISTERED` is False,
which answers the narrower question a link on a public page has to answer. Pages
that would need a published record say so rather than linking into a 404.

No DOI. Zenodo reserves one on publish, so the site prints the record ID rather
than a DOI guessed from the accession number.

**Three routes to the same bytes, and a caller is told which one it got.** A local
checkout via `$GENOMIC_BENCHMARKS_LOCAL_MIRROR`; the draft via
`$GENOMIC_BENCHMARKS_ZENODO_TOKEN`; the published record, once there is one. The
token is read from the environment and never written down here: a share token in a
public repository is a published token.

**The committed tables and the record are two routes to the same bytes**, checked
rather than assumed -- `data/provenance.json` carries a SHA-256 per file and both
match the record's copies. `data/reports.csv` does the same for the 93 archives.

**The mirror does not make a result reproducible**: it reads a tree that exists on
one machine. So `mirror_root()` is public, `fetch()` returns its route, and
`site/qc-reports/PROVENANCE.json` records it for the reports page to print.

Publication deletes the branches below: `RECORD_REGISTERED` becomes True in that
same commit, and the token and the mirror stop being set.
"""

from __future__ import annotations

import os
import shutil
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
RECORD_REGISTERED = False

BASE_URL = f"https://zenodo.org/records/{RECORD_ID}"
API_URL = f"https://zenodo.org/api/records/{RECORD_ID}"

# The two summary tables, which are also committed under `data/`.
SUMMARY_TABLES = ("combined_classes_results.csv", "combined_splits_results.csv")

# The one table that is not committed anywhere: 2.59 M rows at 343 MB. Named here
# because a reader who wants the per-position numbers behind a probe needs to be
# told where they are, and this module is where file names live.
FULL_TABLE = "combined_classes_results_full.csv"

LOCAL_MIRROR_ENV = "GENOMIC_BENCHMARKS_LOCAL_MIRROR"
DRAFT_TOKEN_ENV = "GENOMIC_BENCHMARKS_ZENODO_TOKEN"

# Where the mirrored run sits inside a `GenBench2_paper` checkout, and where the
# report archives sit inside it. `published` is a symlink to the dated run
# directory that was uploaded, so resolving through it serves the run the record
# was made from rather than whichever run finished last.
_PUBLISHED_QC = Path("runs") / "dataset_qc" / "published"
_ARCHIVE_DIR = "zenodo"


class RecordUnavailable(RuntimeError):
    """The QC record cannot be reached, and the message says which reason.

    Four of them, and they are not the same problem: nothing is published and no
    token was given, the token was refused, the mirror is not a checkout, or the
    network refused.
    """


def registered() -> bool:
    """Whether `RECORD_ID` resolves for a reader who has no token.

    Not whether the record exists -- it does, and `draft_token()` can reach it.
    This is the question a link on a public page has to answer.
    """
    return RECORD_REGISTERED


def draft_token() -> str | None:
    """The share token that reaches the unpublished draft, or None.

    From the environment only. A token committed to a repository is a token
    published to everyone who clones it, and this one grants read access to a
    record that is deliberately not public yet.
    """
    return os.environ.get(DRAFT_TOKEN_ENV, "").strip() or None


def record_url() -> str:
    """The landing page a reader can open, with the preview link while drafting."""
    token = draft_token()
    if not registered() and token:
        return f"{BASE_URL}?preview=1&token={token}"
    return BASE_URL


def public_record_url() -> str:
    """The landing page as it will read on a page, never carrying a token.

    Separate from `record_url()` because the site prints one and fetches with the
    other, and a token pasted into rendered HTML is a token published.
    """
    return BASE_URL


def file_url(name: str) -> str:
    """The address of one file on the record, by whichever route is open.

    The API's `content` endpoint: the same shape published and draft, differing
    only by the `/draft` segment and the token.
    """
    quoted = urllib.parse.quote(name, safe="")
    token = draft_token()
    if not registered() and token:
        query = urllib.parse.urlencode({"token": token})
        return f"{API_URL}/draft/files/{quoted}/content?{query}"
    return f"{API_URL}/files/{quoted}/content"


def archive_name(collection: str, dataset_name: str) -> str:
    """The report archive for one dataset.

    `<collection>-<dataset>.zip`, which is also the name of the single directory
    inside it. The record is flat, so the filename is the only thing telling 93
    archives apart, and `genomic_benchmarks_data` composes exactly this name.
    """
    return f"{collection}-{dataset_name}.zip"


def mirror_root() -> Path | None:
    """The checkout fetches are being served from, or None for the network.

    Public, and meant to be called from outside this module: it is the one
    question a caller has to ask to know whether what it just fetched is
    reproducible off this machine. None is the published answer.
    """
    raw = os.environ.get(LOCAL_MIRROR_ENV, "").strip()
    if not raw:
        return None
    return _checked_root(Path(raw).expanduser())


def _checked_root(root: Path) -> Path:
    """Resolve a configured mirror, or say why it is not a run to serve from.

    Refused outright rather than falling back to the network, because a silent
    fallback presents as the download failure this mode exists to get around.
    """
    root = root.resolve()
    if not root.is_dir():
        raise RecordUnavailable(
            f"${LOCAL_MIRROR_ENV} is {root}, which is not a directory. It wants a "
            f"checkout of GenBench2_paper, whose {_PUBLISHED_QC} holds the QC run "
            f"this record was made from."
        )
    if not (root / _PUBLISHED_QC).is_dir():
        raise RecordUnavailable(
            f"${LOCAL_MIRROR_ENV} is {root}, which has no {_PUBLISHED_QC}. That is "
            f"the published QC run -- normally a symlink to the dated run "
            f"directory -- and without it there is nothing local to serve."
        )
    return root


def mirrored(name: str) -> Path:
    """The mirrored copy of one published file, or a message saying it is absent.

    Resolved by name: the directory the QC run publishes is what became the
    record, so the local tree and the record hold the same names.
    """
    root = mirror_root()
    if root is None:
        raise RecordUnavailable(
            f"nothing to mirror from: ${LOCAL_MIRROR_ENV} is not set."
        )
    published = root / _PUBLISHED_QC
    for candidate in (published / name, published / _ARCHIVE_DIR / name):
        if candidate.is_file():
            return candidate
    raise RecordUnavailable(
        f"no file named {name!r} in the local mirror: it is neither "
        f"{published / name} nor {published / _ARCHIVE_DIR / name}."
    )


def route() -> str:
    """Which of the three routes a fetch would take right now, without fetching.

    So that a caller can print the answer before spending 90 MB finding it out,
    and so `--dry-run` says something true.
    """
    if mirror_root() is not None:
        return "local_mirror"
    if registered():
        return "zenodo"
    if draft_token() is not None:
        return "zenodo_draft"
    return "unavailable"


def fetch(name: str, destination: Path, *, timeout: float = 60.0) -> tuple[Path, str]:
    """One published file, from wherever it can be had, and which route that was.

    Returns the path and one of `"local_mirror"`, `"zenodo"`, `"zenodo_draft"`.
    The path rather than `destination`, because a mirrored file is read where it
    lies. The route, because a caller about to write something a reader will see
    has to be able to say which one it got.
    """
    taken = route()
    if taken == "local_mirror":
        return mirrored(name), taken

    if taken == "unavailable":
        raise RecordUnavailable(
            f"cannot fetch {name!r}: Zenodo record {RECORD_ID} is staged but not "
            f"published, so {API_URL}/files/... does not answer. Set "
            f"${DRAFT_TOKEN_ENV} to the record's share token to read the draft, "
            f"set ${LOCAL_MIRROR_ENV} to a GenBench2_paper checkout to serve the "
            f"run from disk, or flip RECORD_REGISTERED in gb_audit/zenodo.py in "
            f"the commit that publishes the record."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    url = file_url(name)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except urllib.error.HTTPError as exc:
        destination.unlink(missing_ok=True)
        # Reported without the URL, which carries the token when drafting.
        raise RecordUnavailable(
            f"fetching {name!r} from record {RECORD_ID} failed: HTTP {exc.code} "
            f"{exc.reason}."
            + (
                f" The draft token in ${DRAFT_TOKEN_ENV} may have expired."
                if taken == "zenodo_draft" and exc.code in (401, 403, 404)
                else ""
            )
        ) from exc
    except urllib.error.URLError as exc:
        # Unlinked rather than left behind: a partial download that keeps its
        # name is a file the next run will find, check nothing about, and unpack.
        destination.unlink(missing_ok=True)
        raise RecordUnavailable(
            f"fetching {name!r} from record {RECORD_ID} failed: {exc.reason}"
        ) from exc
    return destination, taken
