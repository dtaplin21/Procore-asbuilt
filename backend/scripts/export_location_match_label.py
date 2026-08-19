#!/usr/bin/env python3
"""Export one location-match eval label to a suite JSON file (no DB).

Examples (from ``backend/``)::

    ./venv/bin/python scripts/export_location_match_label.py \\
      --suite acme --label-id acme-corridor-1 --project-id 3 \\
      --master-drawing-id 12 --evidence-id 99 \\
      --expected-method coordinate_lookup --expected-match-status matched \\
      --bbox-x 0.5 --bbox-y 0.4 --bbox-width 0.05 --bbox-height 0.04 \\
      --evidence-kind form --has-coordinate-signal \\
      --out tests/fixtures/location_match_labels/acme.json
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

from services.location_match_label_io import validate_entry  # noqa: E402


def build_label(args: argparse.Namespace) -> dict[str, Any]:
    label: dict[str, Any] = {
        "label_id": args.label_id.strip(),
        "suite": args.suite.strip(),
        "project_id": int(args.project_id),
        "evidence_id": int(args.evidence_id) if args.evidence_id is not None else None,
        "inspection_run_id": (
            int(args.inspection_run_id) if args.inspection_run_id is not None else None
        ),
        "master_drawing_id": int(args.master_drawing_id),
        "evidence_fixture_path": args.evidence_fixture_path,
        "master_bbox_json": {
            "type": "rect",
            "page": int(args.page),
            "x": float(args.bbox_x),
            "y": float(args.bbox_y),
            "width": float(args.bbox_width),
            "height": float(args.bbox_height),
        },
        "expected_method": str(args.expected_method),
        "expected_match_status": str(args.expected_match_status),
        "rotation_deg": int(args.rotation_deg) if args.rotation_deg is not None else None,
        "has_coordinate_signal": bool(args.has_coordinate_signal),
        "has_station_signal": bool(args.has_station_signal),
        "has_reference_signal": bool(args.has_reference_signal),
        "evidence_kind": str(args.evidence_kind),
        "notes": args.notes,
    }
    validate_entry(label, 0)
    return label


def write_label(out_path: Path, label: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        with open(out_path, encoding="utf-8") as handle:
            existing = json.load(handle)
        if not isinstance(existing, list):
            raise ValueError(f"{out_path} must contain a JSON array")
        label_id = label["label_id"]
        if any(
            isinstance(entry, dict) and entry.get("label_id") == label_id
            for entry in existing
        ):
            raise ValueError(f"Duplicate label_id {label_id!r} already in {out_path}")
        existing.append(label)
        payload = existing
    else:
        payload = [label]

    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--label-id", required=True)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--master-drawing-id", type=int, required=True)
    parser.add_argument("--evidence-id", type=int, default=None)
    parser.add_argument("--inspection-run-id", type=int, default=None)
    parser.add_argument("--expected-method", required=True)
    parser.add_argument("--expected-match-status", required=True)
    parser.add_argument("--bbox-x", type=float, required=True)
    parser.add_argument("--bbox-y", type=float, required=True)
    parser.add_argument("--bbox-width", type=float, required=True)
    parser.add_argument("--bbox-height", type=float, required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--evidence-kind", required=True)
    parser.add_argument("--evidence-fixture-path", default=None)
    parser.add_argument("--has-coordinate-signal", action="store_true")
    parser.add_argument("--has-station-signal", action="store_true")
    parser.add_argument("--has-reference-signal", action="store_true")
    parser.add_argument("--rotation-deg", type=int, default=None)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        label = build_label(args)
        out_path = args.out
        if not out_path.is_absolute():
            out_path = Path(_BACKEND_ROOT) / out_path
        write_label(out_path, label)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(label, indent=2))
    print(f"Wrote label {label['label_id']!r} to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
