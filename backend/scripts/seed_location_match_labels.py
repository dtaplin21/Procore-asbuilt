"""
Load location-match eval labels from JSON into ``location_match_labels``.

Usage (from ``backend/``)::

    cd backend
    ./venv/bin/python scripts/seed_location_match_labels.py
    ./venv/bin/python scripts/seed_location_match_labels.py --suite ucsf
    ./venv/bin/python scripts/seed_location_match_labels.py \\
        --fixture tests/fixtures/location_match_labels/synthetic.json

Idempotent: upserts by ``label_id``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from database import SessionLocal  # noqa: E402
from models.location_match_label import LocationMatchLabel  # noqa: E402
from services.location_match_label_io import (  # noqa: E402
    REQUIRED_FIELDS,
    list_suite_files,
    load_fixture,
    load_fixture_dir,
    load_fixture_path,
    validate_entry,
)

# Re-export IO helpers for scripts/tests that import from this module.
__all__ = [
    "REQUIRED_FIELDS",
    "DEFAULT_FIXTURE_DIR",
    "list_suite_files",
    "load_fixture",
    "load_fixture_dir",
    "load_fixture_path",
    "validate_entry",
    "upsert_label",
    "seed_labels_from_entries",
    "seed_labels_from_fixture",
    "main",
]

DEFAULT_FIXTURE_DIR = Path(_BACKEND_ROOT) / "tests/fixtures/location_match_labels"


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def upsert_label(session, entry: dict[str, Any]) -> LocationMatchLabel:
    label_id = str(entry["label_id"]).strip()
    row = session.get(LocationMatchLabel, label_id)

    payload = {
        "suite": str(entry["suite"]).strip(),
        "project_id": int(entry["project_id"]),
        "evidence_id": _optional_int(entry.get("evidence_id")),
        "inspection_run_id": _optional_int(entry.get("inspection_run_id")),
        "master_drawing_id": int(entry["master_drawing_id"]),
        "evidence_fixture_path": entry.get("evidence_fixture_path"),
        "master_bbox_json": dict(entry["master_bbox_json"]),
        "master_scope_geometry_json": (
            dict(entry["master_scope_geometry_json"])
            if isinstance(entry.get("master_scope_geometry_json"), dict)
            else None
        ),
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


def seed_labels_from_entries(session, entries: list[dict[str, Any]]) -> int:
    for index, entry in enumerate(entries):
        validate_entry(entry, index)
        upsert_label(session, entry)
    session.commit()
    return len(entries)


def seed_labels_from_fixture(
    session,
    fixture_path: Path,
    *,
    suite: str | None = None,
) -> int:
    entries = load_fixture_path(fixture_path, suite=suite)
    return seed_labels_from_entries(session, entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help=(
            "Path to labels JSON file or suite directory "
            f"(default: {DEFAULT_FIXTURE_DIR.relative_to(_BACKEND_ROOT)})"
        ),
    )
    parser.add_argument(
        "--suite",
        type=str,
        default=None,
        help="Optional suite filter (e.g. ucsf, synthetic)",
    )
    args = parser.parse_args()

    fixture_path = args.fixture
    if not fixture_path.is_absolute():
        fixture_path = Path(_BACKEND_ROOT) / fixture_path

    if not fixture_path.exists():
        print(f"Fixture path not found: {fixture_path}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        count = seed_labels_from_fixture(db, fixture_path, suite=args.suite)
        suite_note = f" suite={args.suite}" if args.suite else ""
        print(f"Seeded {count} location match labels from {fixture_path}{suite_note}.")
    except ValueError as exc:
        db.rollback()
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
