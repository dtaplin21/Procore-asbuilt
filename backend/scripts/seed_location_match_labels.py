"""
Load location-match eval labels from JSON into ``location_match_labels``.

Usage (from ``backend/``)::

    cd backend
    ./venv/bin/python scripts/seed_location_match_labels.py
    ./venv/bin/python scripts/seed_location_match_labels.py \\
        --fixture tests/fixtures/location_match_labels.json

Idempotent: upserts by ``label_id``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from database import SessionLocal  # noqa: E402
from models.location_match_label import LocationMatchLabel  # noqa: E402

REQUIRED_FIELDS = (
    "label_id",
    "project_id",
    "master_drawing_id",
    "master_bbox_json",
    "expected_method",
    "expected_match_status",
    "has_coordinate_signal",
    "has_station_signal",
    "has_reference_signal",
    "evidence_kind",
)

DEFAULT_FIXTURE = Path(_BACKEND_ROOT) / "tests/fixtures/location_match_labels.json"


def load_fixture(fixture_path: Path) -> list[dict[str, Any]]:
    with open(fixture_path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array in {fixture_path}, got {type(data).__name__}"
        )
    return data


def validate_entry(entry: dict[str, Any], index: int) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"Fixture entry {index} must be an object")

    for field in REQUIRED_FIELDS:
        if field not in entry:
            raise ValueError(f"Fixture entry {index} missing required field {field!r}")

    label_id = entry["label_id"]
    if not isinstance(label_id, str) or not label_id.strip():
        raise ValueError(f"Fixture entry {index} label_id must be a non-empty string")

    bbox = entry["master_bbox_json"]
    if not isinstance(bbox, dict):
        raise ValueError(f"Fixture entry {index} master_bbox_json must be an object")
    if bbox.get("type") != "rect":
        raise ValueError(
            f"Fixture entry {index} master_bbox_json.type must be 'rect' (got {bbox.get('type')!r})"
        )
    for key in ("x", "y", "width", "height"):
        if key not in bbox:
            raise ValueError(f"Fixture entry {index} master_bbox_json missing {key!r}")


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def upsert_label(session, entry: dict[str, Any]) -> LocationMatchLabel:
    label_id = str(entry["label_id"]).strip()
    row = session.get(LocationMatchLabel, label_id)

    payload = {
        "project_id": int(entry["project_id"]),
        "evidence_id": _optional_int(entry.get("evidence_id")),
        "inspection_run_id": _optional_int(entry.get("inspection_run_id")),
        "master_drawing_id": int(entry["master_drawing_id"]),
        "evidence_fixture_path": entry.get("evidence_fixture_path"),
        "master_bbox_json": dict(entry["master_bbox_json"]),
        "expected_method": str(entry["expected_method"]),
        "expected_match_status": str(entry["expected_match_status"]),
        "rotation_deg": _optional_int(entry.get("rotation_deg")),
        "has_coordinate_signal": bool(entry["has_coordinate_signal"]),
        "has_station_signal": bool(entry["has_station_signal"]),
        "has_reference_signal": bool(entry["has_reference_signal"]),
        "evidence_kind": str(entry["evidence_kind"]),
        "notes": entry.get("notes"),
    }

    if row is None:
        row = LocationMatchLabel(label_id=label_id, **payload)
        session.add(row)
    else:
        for key, value in payload.items():
            setattr(row, key, value)

    return row


def seed_labels_from_fixture(session, fixture_path: Path) -> int:
    entries = load_fixture(fixture_path)
    for index, entry in enumerate(entries):
        validate_entry(entry, index)
        upsert_label(session, entry)
    session.commit()
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help=f"Path to labels JSON (default: {DEFAULT_FIXTURE.relative_to(_BACKEND_ROOT)})",
    )
    args = parser.parse_args()

    fixture_path = args.fixture
    if not fixture_path.is_absolute():
        fixture_path = Path(_BACKEND_ROOT) / fixture_path

    if not fixture_path.exists():
        print(f"Fixture file not found: {fixture_path}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        count = seed_labels_from_fixture(db, fixture_path)
        print(f"Seeded {count} location match labels from {fixture_path}.")
    except ValueError as exc:
        db.rollback()
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
