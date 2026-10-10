"""Reaching the record: which route, and what each refusal says."""

from __future__ import annotations

import pytest
from gb_audit import zenodo


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
    assert recorded["zenodo_record_version"] == zenodo.VERSION
    assert recorded["zenodo_record_registered"] == zenodo.registered()


def test_with_nothing_configured_the_route_is_the_published_record():
    assert zenodo.route() == "zenodo"
    assert zenodo.file_url("BEACON-CRISPROnTarget.zip") == (
        f"{zenodo.API_URL}/files/BEACON-CRISPROnTarget.zip/content"
    )


def test_an_unpublished_record_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(zenodo, "RECORD_REGISTERED", False)
    assert zenodo.route() == "unavailable"
    with pytest.raises(zenodo.RecordUnavailable) as raised:
        zenodo.fetch("anything.zip", tmp_path / "anything.zip")
    assert "not published" in str(raised.value)


def test_the_archive_name_is_the_one_the_record_uses():
    assert (
        zenodo.archive_name("miRBench", "AGO2_CLASH_Hejret2023")
        == "miRBench-AGO2_CLASH_Hejret2023.zip"
    )
