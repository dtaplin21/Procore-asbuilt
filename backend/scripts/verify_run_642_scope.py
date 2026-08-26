#!/usr/bin/env python3
"""Run #642 sewer scope verification (project 2 / master 661 / aux 1084 / evidence 632).

Usage (from backend/ with venv):
  python scripts/verify_run_642_scope.py
  python scripts/verify_run_642_scope.py --rerun-match
  python scripts/verify_run_642_scope.py --api-base http://127.0.0.1:2000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")

from database import SessionLocal
from models.drawing_overlay import DrawingOverlay
from models.inspection_run import InspectionRun
from models.models import Drawing, EvidenceRecord

PROJECT_ID = 2
EVIDENCE_ID = 632
RUN_ID = 642
MASTER_ID = 661
AUX_ID = 1084

CAMPUS_X_MIN = 0.35
CAMPUS_X_MAX = 0.65
MIN_POLYLINE_POINTS = 3


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def _first_point_x(geometry: dict) -> float | None:
    points = geometry.get("points")
    if not isinstance(points, list) or not points:
        return None
    first = points[0]
    if not isinstance(first, (list, tuple)) or len(first) < 1:
        return None
    try:
        return float(first[0])
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Run #642 sewer scope on master 661")
    parser.add_argument(
        "--api-base",
        default=None,
        help="Optional backend base URL to GET overlays (e.g. http://127.0.0.1:2000)",
    )
    parser.add_argument(
        "--rerun-match",
        action="store_true",
        help="Re-run inspection match job before checks",
    )
    args = parser.parse_args()

    db = SessionLocal()
    all_ok = True
    try:
        if args.rerun_match:
            from services.inspection_matching_jobs import run_inspection_match_job

            status = run_inspection_match_job(
                {
                    "inspection_id": str(EVIDENCE_ID),
                    "drawing_id": MASTER_ID,
                    "page": 1,
                    "inspection_run_id": RUN_ID,
                    "project_id": PROJECT_ID,
                },
                db,
            )
            db.commit()
            print(f"Re-ran match job → {status}\n")

        ev = db.get(EvidenceRecord, EVIDENCE_ID)
        run = db.get(InspectionRun, RUN_ID)
        master = db.get(Drawing, MASTER_ID)
        aux = db.get(Drawing, AUX_ID)

        print("=== Run #642 sewer scope (DB) ===")
        all_ok &= _check("evidence exists", ev is not None, f"id={EVIDENCE_ID}")
        all_ok &= _check("inspection run exists", run is not None, f"id={RUN_ID}")
        all_ok &= _check(
            "master drawing exists",
            master is not None and master.project_id == PROJECT_ID,
            f"id={MASTER_ID}",
        )
        all_ok &= _check("aux drawing exists", aux is not None, f"id={AUX_ID}")

        meta = ev.meta if ev and isinstance(ev.meta, dict) else {}
        reg = meta.get("registration_transform")
        all_ok &= _check(
            "registration_transform present",
            isinstance(reg, dict) and "scale_x" in reg,
            f"keys={list(reg.keys()) if isinstance(reg, dict) else None}",
        )

        overlay = (
            db.query(DrawingOverlay)
            .filter(
                DrawingOverlay.master_drawing_id == MASTER_ID,
                DrawingOverlay.inspection_run_id == RUN_ID,
            )
            .order_by(DrawingOverlay.id.desc())
            .first()
        )
        geom = overlay.geometry if overlay and isinstance(overlay.geometry, dict) else {}
        overlay_meta = overlay.meta if overlay and isinstance(overlay.meta, dict) else {}
        points = geom.get("points") if isinstance(geom.get("points"), list) else []
        first_x = _first_point_x(geom)

        all_ok &= _check("overlay persisted", overlay is not None, f"id={getattr(overlay, 'id', None)}")
        all_ok &= _check(
            "scope_geometry_json.type polyline",
            geom.get("type") == "polyline",
            f"type={geom.get('type')}",
        )
        all_ok &= _check(
            "polyline point count",
            len(points) >= MIN_POLYLINE_POINTS,
            f"count={len(points)} (min {MIN_POLYLINE_POINTS})",
        )
        all_ok &= _check(
            "first point in campus band",
            first_x is not None and CAMPUS_X_MIN <= first_x <= CAMPUS_X_MAX,
            f"x={first_x} expected [{CAMPUS_X_MIN}, {CAMPUS_X_MAX}]",
        )

        match_status = overlay_meta.get("match_status")
        all_ok &= _check(
            "match_status matched",
            match_status == "matched",
            f"status={match_status}",
        )

        if args.api_base:
            url = (
                f"{args.api_base.rstrip('/')}/api/projects/{PROJECT_ID}"
                f"/drawings/{MASTER_ID}/overlays?inspection_run_id={RUN_ID}"
            )
            print(f"\n=== Run #642 overlays API ===\n  GET {url}")
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    body = json.loads(resp.read().decode())
                api_geom = (body[0].get("geometry") if body else {}) or {}
                api_points = api_geom.get("points") if isinstance(api_geom.get("points"), list) else []
                api_first_x = _first_point_x(api_geom)
                all_ok &= _check(
                    "API returns campus polyline",
                    api_geom.get("type") == "polyline"
                    and len(api_points) >= MIN_POLYLINE_POINTS
                    and api_first_x is not None
                    and CAMPUS_X_MIN <= api_first_x <= CAMPUS_X_MAX,
                    f"type={api_geom.get('type')} points={len(api_points)} first_x={api_first_x}",
                )
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                all_ok &= _check("API reachable", False, str(exc))

        print("\n=== Manual (UI) ===")
        print(
            f"  Open /objects?projectId={PROJECT_ID}&drawingId={MASTER_ID}&run={RUN_ID}\n"
            "  Confirm polyline follows sanitary sewer run on campus plan (not bottom-left corner)."
        )
        print(f"\nGATE: {'PASS' if all_ok else 'FAIL'}")
        return 0 if all_ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
