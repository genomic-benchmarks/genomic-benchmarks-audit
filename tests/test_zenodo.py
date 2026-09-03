"""Reaching the record: which route, and what each refusal says."""

from __future__ import annotations

import pytest
from gb_audit import zenodo


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    monkeypatch.delenv(zenodo.LOCAL_MIRROR_ENV, raising=False)
    monkeypatch.delenv(zenodo.DRAFT_TOKEN_ENV, raising=False)


def test_the_record_id_matches_what_the_data_was_generated_against():
    """Two files name this record. They cannot be allowed to drift apart."""
    import json
    from pathlib import Path

    recorded = json.loads(
        (Path(zenodo.__file__).resolve().parents[2] / "data" / "provenance.json")
        .read_text(encoding="utf-8")
    )
    assert recorded["zenodo_record_id"] == zenodo.RECORD_ID
    assert recorded["zenodo_concept_record_id"] == zenodo.CONCEPT_RECORD_ID
    assert recorded["zenodo_record_registered"] == zenodo.registered()


def test_with_nothing_configured_the_route_is_unavailable():
    """The record exists but is not published, and no token is set."""
    assert zenodo.route() == "unavailable"


def test_the_refusal_names_all_three_ways_out(tmp_path):
    with pytest.raises(zenodo.RecordUnavailable) as raised:
        zenodo.fetch("anything.zip", tmp_path / "anything.zip")
    message = str(raised.value)
    assert zenodo.DRAFT_TOKEN_ENV in message
    assert zenodo.LOCAL_MIRROR_ENV in message
    assert "RECORD_REGISTERED" in message


def test_a_token_switches_the_route_and_the_url(monkeypatch):
    monkeypatch.setenv(zenodo.DRAFT_TOKEN_ENV, "a-share-token")
    assert zenodo.route() == "zenodo_draft"
    url = zenodo.file_url("BEACON-CRISPROnTarget.zip")
    assert "/draft/files/" in url and "token=a-share-token" in url


def test_the_public_url_never_carries_a_token(monkeypatch):
    """It is what the site prints. `record_url()` is what the fetch uses."""
    monkeypatch.setenv(zenodo.DRAFT_TOKEN_ENV, "a-share-token")
    assert "token" not in zenodo.public_record_url()
    assert "a-share-token" in zenodo.record_url()


def test_a_mirror_that_is_not_a_run_is_refused_rather_than_fallen_back_from(
    tmp_path, monkeypatch
):
    """A silent fallback to the network presents as the download failure this
    mode exists to get around."""
    monkeypatch.setenv(zenodo.LOCAL_MIRROR_ENV, str(tmp_path))
    with pytest.raises(zenodo.RecordUnavailable) as raised:
        zenodo.mirror_root()
    assert "runs/dataset_qc/published" in str(raised.value).replace("\\", "/")


def test_a_mirror_holding_the_run_resolves_by_name(tmp_path, monkeypatch):
    published = tmp_path / "runs" / "dataset_qc" / "published"
    (published / "zenodo").mkdir(parents=True)
    (published / "combined_splits_results.csv").write_text("a,b\n")
    (published / "zenodo" / "BEACON-Isoform.zip").write_bytes(b"PK")
    monkeypatch.setenv(zenodo.LOCAL_MIRROR_ENV, str(tmp_path))

    assert zenodo.route() == "local_mirror"
    assert zenodo.mirrored("combined_splits_results.csv").is_file()
    assert zenodo.mirrored("BEACON-Isoform.zip").is_file()
    with pytest.raises(zenodo.RecordUnavailable):
        zenodo.mirrored("not-in-the-run.zip")


def test_a_mirrored_file_is_read_where_it_lies(tmp_path, monkeypatch):
    """Not copied. A second copy is a thing that can go stale against the first."""
    published = tmp_path / "runs" / "dataset_qc" / "published"
    published.mkdir(parents=True)
    source = published / "combined_splits_results.csv"
    source.write_text("a,b\n")
    monkeypatch.setenv(zenodo.LOCAL_MIRROR_ENV, str(tmp_path))

    destination = tmp_path / "elsewhere" / "combined_splits_results.csv"
    path, route = zenodo.fetch("combined_splits_results.csv", destination)
    assert path == source and route == "local_mirror"
    assert not destination.exists()


def test_the_archive_name_is_the_one_the_record_uses():
    assert (
        zenodo.archive_name("miRBench", "AGO2_CLASH_Hejret2023")
        == "miRBench-AGO2_CLASH_Hejret2023.zip"
    )
