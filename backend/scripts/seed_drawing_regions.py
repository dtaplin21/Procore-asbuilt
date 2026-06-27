"""
Bulk-seed tagged regions for a master drawing — demo setup or migrating
known inspectable zones without drawing each one in the editor.

Usage (from ``backend/`` so ``.env`` and imports resolve)::

    cd backend
    ./venv/bin/python scripts/seed_drawing_regions.py <master_drawing_id> <fixture_path>

Fixture: JSON array — see ``tests/fixtures/sample_drawing_regions.json``.
Each entry requires ``geometry``. ``label`` is optional — when omitted it is
derived from the first ``location_tags`` entry, then the first
``inspection_type_tags`` entry, then ``Region N``. Tags may be top-level or
nested under ``tags``.

Legacy pixel fixtures (``x``/``y``/``width``/``height`` plus ``page_width``/
``page_height``) are normalized automatically for one-off migrations.
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
from models.models import Drawing  # noqa: E402
from services.region_storage import create_drawing_region  # noqa: E402


def load_fixture(fixture_path: Path) -> list[dict[str, Any]]:
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array in {fixture_path}, got {type(data).__name__}"
        )
    return data


def _tags_from_entry(entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    nested = entry.get("tags")
    if isinstance(nested, dict):
        type_tags = nested.get("inspection_type_tags") or []
        location_tags = nested.get("location_tags") or []
    else:
        type_tags = entry.get("inspection_type_tags") or []
        location_tags = entry.get("location_tags") or []
    if not isinstance(type_tags, list) or not isinstance(location_tags, list):
        raise ValueError("inspection_type_tags and location_tags must be arrays")
    return [str(t) for t in type_tags], [str(t) for t in location_tags]


def _label_from_entry(
    entry: dict[str, Any],
    index: int,
    inspection_type_tags: list[str],
    location_tags: list[str],
) -> str:
    explicit = entry.get("label")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if location_tags:
        return location_tags[0]
    if inspection_type_tags:
        return inspection_type_tags[0]
    return f"Region {index + 1}"


def _geometry_from_entry(
    entry: dict[str, Any], index: int
) -> tuple[dict[str, Any], list[list[float]] | None]:
    raw = entry.get("geometry")
    if not isinstance(raw, dict):
        raise ValueError(f"Fixture entry {index} requires a geometry object")

    polygon_points_raw = entry.get("polygon_points")
    if polygon_points_raw is None and isinstance(raw.get("polygon_points"), list):
        polygon_points_raw = raw.get("polygon_points")

    if raw.get("type") in ("rect", "polygon"):
        geometry = dict(raw)
        geometry.pop("polygon_points", None)
        return geometry, polygon_points_raw

    # Legacy pixel bbox → normalized rect (+ optional polygon detail)
    try:
        x = float(raw["x"])
        y = float(raw["y"])
        width = float(raw["width"])
        height = float(raw["height"])
        page_width = float(raw["page_width"])
        page_height = float(raw["page_height"])
    except KeyError as exc:
        raise ValueError(
            f"Fixture entry {index} geometry must be normalized (type rect/polygon) "
            f"or legacy pixel fields including {exc.args[0]!r}"
        ) from exc

    if page_width <= 0 or page_height <= 0:
        raise ValueError(f"Fixture entry {index} page_width/page_height must be positive")

    geometry = {
        "type": "rect",
        "x": x / page_width,
        "y": y / page_height,
        "width": width / page_width,
        "height": height / page_height,
    }
    normalized_polygon: list[list[float]] | None = None
    if isinstance(polygon_points_raw, list):
        normalized_polygon = [
            [float(p[0]) / page_width, float(p[1]) / page_height]
            for p in polygon_points_raw
        ]
    return geometry, normalized_polygon


def seed_regions_from_fixture(db, master_drawing_id: int, fixture_path: Path) -> int:
    """Create one DrawingRegion per fixture entry. Raises on first invalid row."""
    drawing = db.query(Drawing).filter(Drawing.id == master_drawing_id).one_or_none()
    if drawing is None:
        raise ValueError(f"Master drawing {master_drawing_id} not found")

    entries = load_fixture(fixture_path)
    created = 0

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Fixture entry {i} must be an object, got {type(entry).__name__}")

        page = entry.get("page", 1)
        if not isinstance(page, int) or page < 1:
            raise ValueError(f"Fixture entry {i} page must be a positive integer")

        geometry, polygon_points = _geometry_from_entry(entry, i)
        inspection_type_tags, location_tags = _tags_from_entry(entry)
        label = _label_from_entry(entry, i, inspection_type_tags, location_tags)

        create_drawing_region(
            db,
            master_drawing_id,
            label=label,
            page=page,
            geometry=geometry,
            polygon_points=polygon_points,
            inspection_type_tags=inspection_type_tags,
            location_tags=location_tags,
        )
        created += 1

    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-seed drawing regions from JSON.")
    parser.add_argument("master_drawing_id", type=int, help="Integer master drawing PK")
    parser.add_argument("fixture_path", type=Path, help="Path to JSON fixture array")
    args = parser.parse_args()

    if not args.fixture_path.exists():
        print(f"Fixture file not found: {args.fixture_path}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        count = seed_regions_from_fixture(db, args.master_drawing_id, args.fixture_path)
        print(
            f"Seeded {count} regions for master drawing {args.master_drawing_id} "
            f"from {args.fixture_path}."
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
