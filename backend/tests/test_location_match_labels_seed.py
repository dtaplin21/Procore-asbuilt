"""Tests for location_match_labels fixture and seed script."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from models.location_match_label import LocationMatchLabel
from scripts.seed_location_match_labels import (
    load_fixture,
    seed_labels_from_fixture,
    validate_entry,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "location_match_labels.json"


def test_fixture_has_minimum_eval_rows() -> None:
    entries = load_fixture(FIXTURE_PATH)
    assert len(entries) >= 5
    label_ids = {entry["label_id"] for entry in entries}
    assert "ucsf-435-ss-corridor" in label_ids
    assert "ucsf-rotated-detail" in label_ids
    assert "ucsf-no-coords-clue-only" in label_ids
    assert "ucsf-no-coords-unresolved" in label_ids
    assert "ucsf-station-only" in label_ids


def test_golden_label_points_at_ucsf_evidence_and_master() -> None:
    entries = load_fixture(FIXTURE_PATH)
    golden = next(e for e in entries if e["label_id"] == "ucsf-435-ss-corridor")
    assert golden["evidence_id"] == 357
    assert golden["master_drawing_id"] == 661
    assert golden["inspection_run_id"] == 435
    assert golden["rotation_deg"] == 180
    assert golden["expected_method"] == "coordinate_lookup"
    assert golden["expected_match_status"] == "matched"
    bbox = golden["master_bbox_json"]
    assert bbox["type"] == "rect"
    assert bbox["width"] > 0


def _sample_label(project_id: int) -> dict[str, Any]:
    return {
        "label_id": "test-label-seed",
        "project_id": project_id,
        "evidence_id": None,
        "inspection_run_id": None,
        "master_drawing_id": 661,
        "evidence_fixture_path": "tests/fixtures/evidence/ucsf-field-photo.jpg",
        "master_bbox_json": {
            "type": "rect",
            "page": 1,
            "x": 0.1,
            "y": 0.2,
            "width": 0.05,
            "height": 0.04,
        },
        "expected_method": "unresolved",
        "expected_match_status": "no_match",
        "rotation_deg": None,
        "has_coordinate_signal": False,
        "has_station_signal": False,
        "has_reference_signal": False,
        "evidence_kind": "photo",
        "notes": "seed test row",
    }


def test_seed_location_match_labels_upserts(db_session, project, tmp_path: Path) -> None:
    project_id = cast(int, project.id)
    payload = [_sample_label(project_id)]
    fixture = tmp_path / "labels.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    count = seed_labels_from_fixture(db_session, fixture)
    assert count == 1

    row = db_session.get(LocationMatchLabel, "test-label-seed")
    assert row is not None
    assert cast(int, row.project_id) == project_id
    assert cast(str, row.expected_method) == "unresolved"

    payload[0]["notes"] = "updated note"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    seed_labels_from_fixture(db_session, fixture)
    db_session.refresh(row)
    assert cast(str, row.notes) == "updated note"
    assert (
        db_session.query(LocationMatchLabel)
        .filter(LocationMatchLabel.label_id == "test-label-seed")
        .count()
        == 1
    )


def test_validate_entry_rejects_missing_bbox_fields() -> None:
    with pytest.raises(ValueError, match="master_bbox_json missing 'width'"):
        validate_entry(
            {
                "label_id": "bad",
                "project_id": 1,
                "master_drawing_id": 1,
                "master_bbox_json": {"type": "rect", "x": 0, "y": 0, "height": 1},
                "expected_method": "unresolved",
                "expected_match_status": "no_match",
                "has_coordinate_signal": False,
                "has_station_signal": False,
                "has_reference_signal": False,
                "evidence_kind": "photo",
            },
            0,
        )
