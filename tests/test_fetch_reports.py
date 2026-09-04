"""Fetching the archives: what is verified, and what is refused."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

import fetch_reports
from gb_audit import zenodo


def _archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _entry(name: str, payload: bytes, paths: list[str]) -> dict:
    return {
        "archive": f"{name}.zip",
        "bytes": str(len(payload)),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "reports": "|".join(paths),
    }


def test_the_committed_manifest_describes_every_archive():
    entries = fetch_reports.manifest()
    assert len(entries) == 93
    assert sum(len(fetch_reports.expected_paths(e)) for e in entries) == 423
    for entry in entries:
        assert len(entry["sha256"]) == 64
        assert int(entry["bytes"]) > 0


def test_an_archive_whose_digest_is_wrong_is_not_unpacked(tmp_path, monkeypatch):
    """The failure this guards against is not corruption but *success*: an
    endpoint answering 404 with a readable error page unzips to nothing, and a
    build then renders 93 empty report pages without complaining once."""
    payload = _archive({"D/class/train/seq.html": b"<html></html>"})
    entry = _entry("D", payload, ["class/train/seq.html"])
    entry["sha256"] = "0" * 64

    root = tmp_path / "site" / "qc-reports"

    def serve(name, destination, timeout=60.0):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination, "zenodo"

    monkeypatch.setattr(zenodo, "fetch", serve)
    with pytest.raises(fetch_reports.Refused) as raised:
        fetch_reports.acquire(root, entry, timeout=1.0)
    assert "not what data/reports.csv describes" in str(raised.value)
    assert not (root / "D").exists()


def test_a_member_resolving_outside_the_destination_aborts_the_archive(tmp_path):
    """`extractall` will follow a `..` out of the destination. These archives do
    not, and the check costs nothing next to trusting a 90 MB download."""
    payload = _archive({"../escaped.html": b"x"})
    (tmp_path / "into").mkdir()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        with pytest.raises(fetch_reports.Refused) as raised:
            fetch_reports.safe_members(archive, tmp_path / "into")
    assert "resolves outside" in str(raised.value)
    assert not (tmp_path / "escaped.html").exists()


def test_an_archive_missing_a_listed_report_installs_nothing(tmp_path):
    payload = _archive({"D/class/train/seq.html": b"<html></html>"})
    entry = _entry("D", payload, ["class/train/seq.html", "split/train_test.html"])
    root = tmp_path / "site" / "qc-reports"
    source = tmp_path / "D.zip"
    source.write_bytes(payload)
    with pytest.raises(fetch_reports.Refused) as raised:
        fetch_reports.unpack(root, source, entry)
    assert "split/train_test.html" in str(raised.value)
    assert not (root / "D").exists()


def test_a_good_archive_unpacks_flat_under_its_own_name(tmp_path):
    """The archive holds one top-level directory named after itself; the site
    wants its contents at `<stem>/`, not `<stem>/<stem>/`."""
    payload = _archive({
        "D/class/train/seq.html": b"<html>a</html>",
        "D/split/train_test.html": b"<html>b</html>",
    })
    entry = _entry("D", payload, ["class/train/seq.html", "split/train_test.html"])
    root = tmp_path / "site" / "qc-reports"
    source = tmp_path / "D.zip"
    source.write_bytes(payload)

    fetch_reports.unpack(root, source, entry)
    assert (root / "D" / "class" / "train" / "seq.html").is_file()
    assert not (root / "D" / "D").exists()
    assert fetch_reports.present(root, entry)


def test_a_directory_that_is_short_is_not_called_present(tmp_path):
    """An interrupted unpack leaves a directory that exists and is incomplete."""
    root = tmp_path / "site" / "qc-reports"
    entry = _entry("D", b"x", ["class/train/seq.html", "split/train_test.html"])
    partial = root / "D" / "class" / "train"
    partial.mkdir(parents=True)
    (partial / "seq.html").write_text("<html></html>")
    assert not fetch_reports.present(root, entry)


def test_provenance_records_the_route_and_carries_no_timestamp(tmp_path):
    """The site prints this. Reports fetched from an unpublished draft are not
    reports a reader can go and get for themselves."""
    root = tmp_path / "site" / "qc-reports"
    fetch_reports.write_provenance(root, [], "zenodo_draft")
    recorded = json.loads((root / "PROVENANCE.json").read_text())
    assert recorded["route"] == "zenodo_draft"
    assert recorded["zenodo_record_id"] == zenodo.RECORD_ID
    assert recorded["zenodo_record_registered"] is False
    assert not any("time" in k or "date" in k for k in recorded)
