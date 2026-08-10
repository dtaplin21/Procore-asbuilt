"""Shared loaders/validators for location-match eval label fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = (
    "label_id",
    "suite",
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


def list_suite_files(fixture_dir: Path) -> list[Path]:
    """Sorted ``*.json`` suite files under ``fixture_dir`` (skips non-json)."""
    if not fixture_dir.is_dir():
        raise ValueError(f"Fixture directory not found: {fixture_dir}")
    return sorted(
        path
        for path in fixture_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".json"
    )


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

    suite = entry["suite"]
    if not isinstance(suite, str) or not suite.strip():
        raise ValueError(f"Fixture entry {index} suite must be a non-empty string")

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


def load_fixture_dir(
    fixture_dir: Path,
    suite: str | None = None,
) -> list[dict[str, Any]]:
    """Load and concatenate suite JSON arrays from a directory."""
    if suite:
        preferred = fixture_dir / f"{suite}.json"
        if preferred.is_file():
            entries = load_fixture(preferred)
            return [
                entry
                for entry in entries
                if str(entry.get("suite", "")).strip() == suite
            ]
        # Fall back to scanning all files and filtering by entry suite.
        files = list_suite_files(fixture_dir)
    else:
        files = list_suite_files(fixture_dir)

    entries: list[dict[str, Any]] = []
    for path in files:
        for entry in load_fixture(path):
            if suite is not None and str(entry.get("suite", "")).strip() != suite:
                continue
            entries.append(entry)
    return entries


def load_fixture_path(
    path: Path,
    *,
    suite: str | None = None,
) -> list[dict[str, Any]]:
    """Load labels from a JSON file or suite directory."""
    if path.is_dir():
        return load_fixture_dir(path, suite=suite)
    if not path.is_file():
        raise ValueError(f"Fixture path not found: {path}")
    entries = load_fixture(path)
    if suite is None:
        return entries
    return [
        entry for entry in entries if str(entry.get("suite", "")).strip() == suite
    ]
