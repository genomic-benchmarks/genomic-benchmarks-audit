"""Where the QC output is published, and how to reach it before it is published.

The audit's own tables are committed under `data/` and this module is not on the
path that renders a page. What it reaches for is the half of the run that is too
large to commit: the 93 per-dataset report archives (90 MB), and
`combined_classes_results_full.csv` (343 MB, 2.59 M rows -- every individually
scored feature, including every position). Those live on one Zenodo record, and
this module is the only place in the repository that knows its address.

**The record is staged but not published, and those are different facts.** Record
`22288544` exists, holds all 96 files, and is in state `unsubmitted`: reachable
through its draft endpoint with a share token, absent from `zenodo.org/records/`
without one. So `RECORD_ID` is a real identifier rather than a stand-in, and
`RECORD_REGISTERED` is still False -- it answers the narrower question the site
actually asks, which is whether a link printed on a page will resolve for a reader
who has no token. A page that would need a published record says so in the copy
rather than linking into a 404, and `scripts/fetch_reports.py` refuses rather than
downloading an error page and unpacking it.

No DOI is minted here. Zenodo reserves one on publish, and until it does, the
record has none -- so the site prints the record ID and not a DOI it guessed from
the accession number.

**Three routes to the same bytes, and a caller is told which one it got.** A local
checkout via `$GENOMIC_BENCHMARKS_LOCAL_MIRROR`; the draft via
`$GENOMIC_BENCHMARKS_ZENODO_TOKEN`; the published record, once there is one. The
token is read from the environment and never written down here, because a share
token in a public repository is a published token.

**What the record and the checkout agree on.** The two summary tables are on the
record *and* committed under `data/` -- `data/README.md` argues that -- so the
committed copy and the record are two routes to the same bytes. That is a checked
claim, not an assumption: `data/provenance.json` records a SHA-256 per file, and
both committed tables match the record's copies exactly. `data/reports.csv` does
the same job for the 93 archives, listing size, digest, and every path inside, so
the site knows what exists before anything is downloaded.

**What the mirror does not do** is make a result reproducible. It reads a tree that
exists on one machine, so `mirror_root()` is public and returns None when fetches
are going to the network -- the one question a caller has to ask before publishing
anything it produced. `scripts/fetch_reports.py` records which route it took in
`docs/reports/PROVENANCE.json`, and the site prints it.

**What deletes this module's `if` statements.** Publication. Once the draft is
submitted, `RECORD_REGISTERED` becomes True in that same commit, the token and the
mirror stop being set, and the branches below go with them.
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

    Four of them, and they are not the same problem: the record is not published
    and no token was given, the token was refused, the mirror is set to something
    that is not a checkout, or the network refused. Collapsing them into one error
    would send someone hunting for a proxy setting when the answer is that nothing
    has been published and they have no token.
    """


def registered() -> bool:
    """Whether `RECORD_ID` resolves for a reader who has no token.

    Read by the site rather than assumed by it: the pages that would link to a
    report archive say "not published yet" while this is False, which is a
    different page from one whose link is broken. Note what this does *not* ask --
    the record exists; `draft_token()` can reach it. This is the question a link
    on a public page has to answer.
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

    The API's `content` endpoint rather than the landing page's download link: it
    is the one this repository has actually exercised against the record, and it
    is the same shape published and draft, differing only by the `/draft` segment
    and the token.
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

    Resolved by the name the URL ends in, which is the whole mapping needed: the
    QC run writes its combined tables at the top of the directory it publishes and
    the 93 archives in `zenodo/` beside them, and that directory is what became
    the record. So the local tree and the record hold the same names.
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
    The path is returned rather than assumed to be `destination`, because a
    mirrored file is read where it lies: the bytes are already on this disk and a
    second copy is a thing that can go stale against the checkout it came from.

    The route is returned rather than logged, for the reason `mirror_root()` is
    public. A caller that is about to write something a reader will see has to be
    able to say which one it got -- and `zenodo_draft` in particular says the
    bytes came from a record the public cannot yet read.
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
