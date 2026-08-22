"""Tests for location_match_labels fixture and seed script."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from models.location_match_label import LocationMatchLabel
from models.models import Drawing
from scripts.seed_location_match_labels import (
    load_fixture,
    seed_labels_from_fixture,
    validate_entry,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "location_match_labels"
UCSF_FIXTURE_PATH = FIXTURE_DIR / "ucsf.json"
SYNTHETIC_FIXTURE_PATH = FIXTURE_DIR / "synthetic.json"


def test_fixture_has_minimum_eval_rows() -> None:
    entries = load_fixture(UCSF_FIXTURE_PATH)
    assert len(entries) >= 5
    label_ids = {entry["label_id"] for entry in entries}
    assert "ucsf-435-ss-corridor" in label_ids
    assert "ucsf-rotated-detail" in label_ids
    assert "ucsf-no-coords-clue-only" in label_ids
    assert "ucsf-no-coords-unresolved" in label_ids
    assert "ucsf-station-only" in label_ids
    assert all(entry["suite"] == "ucsf" for entry in entries)


def test_synthetic_suite_exists() -> None:
    entries = load_fixture(SYNTHETIC_FIXTURE_PATH)
    assert len(entries) >= 2
    assert all(entry["suite"] == "synthetic" for entry in entries)
    label_ids = {entry["label_id"] for entry in entries}
    assert "synthetic-coord-matched" in label_ids
    assert "synthetic-no-match" in label_ids


def test_ucsf_corridor_label_fields() -> None:
    entries = load_fixture(UCSF_FIXTURE_PATH)
    golden = next(e for e in entries if e["label_id"] == "ucsf-435-ss-corridor")
    assert golden["suite"] == "ucsf"
    assert golden["evidence_id"] == 377
    assert golden["master_drawing_id"] == 661
    assert golden["inspection_run_id"] == 447
    assert golden["rotation_deg"] == 180
    assert golden["expected_method"] == "coordinate_lookup"
    assert golden["expected_match_status"] == "matched"
    bbox = golden["master_bbox_json"]
    assert bbox["type"] == "rect"
    assert bbox["width"] > 0
    scope = golden.get("master_scope_geometry_json")
    assert scope is not None
    assert scope["type"] == "polyline"
    assert scope["scope_kind"] == "utility_line"
    assert len(scope["points"]) >= 2


def test_validate_entry_accepts_polyline_scope_geometry() -> None:
    validate_entry(
        {
            "label_id": "utility-line",
            "suite": "test",
            "project_id": 1,
            "master_drawing_id": 1,
            "master_bbox_json": {
                "type": "rect",
                "page": 1,
                "x": 0.5,
                "y": 0.47,
                "width": 0.05,
                "height": 0.02,
            },
            "master_scope_geometry_json": {
                "type": "polyline",
                "page": 1,
                "points": [[0.51, 0.47], [0.54, 0.48], [0.56, 0.49]],
                "scope_kind": "utility_line",
            },
            "expected_method": "reference_lookup",
            "expected_match_status": "matched",
            "has_coordinate_signal": False,
            "has_station_signal": False,
            "has_reference_signal": True,
            "evidence_kind": "form",
        },
        0,
    )


def test_validate_entry_rejects_invalid_polyline_scope() -> None:
    with pytest.raises(ValueError, match="master_scope_geometry_json invalid"):
        validate_entry(
            {
                "label_id": "bad-polyline",
                "suite": "test",
                "project_id": 1,
                "master_drawing_id": 1,
                "master_bbox_json": {
                    "type": "rect",
                    "page": 1,
                    "x": 0.5,
                    "y": 0.47,
                    "width": 0.05,
                    "height": 0.02,
                },
                "master_scope_geometry_json": {
                    "type": "polyline",
                    "page": 1,
                    "points": [[0.51, 0.47]],
                },
                "expected_method": "reference_lookup",
                "expected_match_status": "matched",
                "has_coordinate_signal": False,
                "has_station_signal": False,
                "has_reference_signal": True,
                "evidence_kind": "form",
            },
            0,
        )


def _sample_label(project_id: int, master_drawing_id: int, **overrides: Any) -> dict[str, Any]:
    payload = {
        "label_id": "test-label-seed",
        "suite": "test",
        "project_id": project_id,
        "evidence_id": None,
        "inspection_run_id": None,
        "master_drawing_id": master_drawing_id,
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
    payload.update(overrides)
    return payload


def _master_drawing(db_session, project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="eval-master.pdf",
        content_type="application/pdf",
        processing_status="pending",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)
    return drawing


def test_seed_location_match_labels_upserts(db_session, project, tmp_path: Path) -> None:
    project_id = cast(int, project.id)
    master_drawing_id = cast(int, _master_drawing(db_session, project).id)
    payload = [_sample_label(project_id, master_drawing_id)]
    fixture_path = tmp_path / "labels.json"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")

    count = seed_labels_from_fixture(db_session, fixture_path)
    assert count == 1

    row = db_session.get(LocationMatchLabel, "test-label-seed")
    assert row is not None
    assert cast(int, row.project_id) == project_id
    assert cast(str, row.suite) == "test"
    assert cast(str, row.expected_method) == "unresolved"

    payload[0]["master_scope_geometry_json"] = {
        "type": "polyline",
        "page": 1,
        "points": [[0.1, 0.2], [0.15, 0.22]],
        "scope_kind": "utility_line",
    }
    payload[0]["notes"] = "updated note"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    seed_labels_from_fixture(db_session, fixture_path)
    db_session.refresh(row)
    assert cast(str, row.notes) == "updated note"
    scope = cast(dict, row.master_scope_geometry_json)
    assert scope["type"] == "polyline"
    assert (
        db_session.query(LocationMatchLabel)
        .filter(LocationMatchLabel.label_id == "test-label-seed")
        .count()
        == 1
    )


def test_seed_loads_directory_with_suite_filter(
    db_session, project, tmp_path: Path
) -> None:
    import uuid

    project_id = cast(int, project.id)
    master_drawing_id = cast(int, _master_drawing(db_session, project).id)
    suite_dir = tmp_path / "location_match_labels"
    suite_dir.mkdir()
    suffix = uuid.uuid4().hex[:8]
    alpha_id = f"alpha-{suffix}"
    beta_id = f"beta-{suffix}"

    alpha = [
        _sample_label(
            project_id,
            master_drawing_id,
            label_id=alpha_id,
            suite="alpha",
        )
    ]
    beta = [
        _sample_label(
            project_id,
            master_drawing_id,
            label_id=beta_id,
            suite="beta",
        )
    ]
    (suite_dir / "alpha.json").write_text(json.dumps(alpha), encoding="utf-8")
    (suite_dir / "beta.json").write_text(json.dumps(beta), encoding="utf-8")

    count = seed_labels_from_fixture(db_session, suite_dir, suite="alpha")
    assert count == 1
    assert db_session.get(LocationMatchLabel, alpha_id) is not None
    assert db_session.get(LocationMatchLabel, beta_id) is None

    count_all = seed_labels_from_fixture(db_session, suite_dir)
    assert count_all == 2
    assert db_session.get(LocationMatchLabel, beta_id) is not None


def test_validate_entry_rejects_missing_bbox_fields() -> None:
    with pytest.raises(ValueError, match="master_bbox_json missing 'width'"):
        validate_entry(
            {
                "label_id": "bad",
                "suite": "test",
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
