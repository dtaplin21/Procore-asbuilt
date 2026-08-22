#!/usr/bin/env python3
"""V-1 golden case verification (project 2 / master 661 / evidence 377 / run 447).

Usage (from backend/ with venv):
  python scripts/verify_v1_golden.py
  python scripts/verify_v1_golden.py --api-base http://127.0.0.1:2000
  python scripts/verify_v1_golden.py --rerun-match
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
EVIDENCE_ID = 377
RUN_ID = 447
MASTER_ID = 661


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify V-1 golden inspection location case")
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

        print("=== V-1 golden case (DB) ===")
        all_ok &= _check(
            "evidence exists",
            ev is not None,
            f"id={EVIDENCE_ID}",
        )
        all_ok &= _check(
            "inspection run exists",
            run is not None,
            f"id={RUN_ID} status={getattr(run, 'status', None)}",
        )
        all_ok &= _check(
            "master drawing exists",
            master is not None and master.project_id == PROJECT_ID,
            f"id={MASTER_ID}",
        )

        meta = ev.meta if ev and isinstance(ev.meta, dict) else {}
        survey = meta.get("survey_points") if isinstance(meta.get("survey_points"), list) else []
        pdf_follow = meta.get("pdfLinkFollow") if isinstance(meta.get("pdfLinkFollow"), dict) else {}
        fetched = int(pdf_follow.get("followed") or pdf_follow.get("fetched_pdf_count") or 0)
        all_ok &= _check(
            "survey_points present",
            len(survey) > 0,
            f"count={len(survey)}",
        )
        # Links may 403 without Procore auth — informational only
        _check(
            "pdf_link_follow fetched (when links present)",
            fetched > 0 or not pdf_follow,
            f"fetched={fetched} meta={json.dumps(pdf_follow)[:120]}",
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

        all_ok &= _check("overlay persisted", overlay is not None, f"id={getattr(overlay, 'id', None)}")
        all_ok &= _check(
            "geometry.type polyline",
            geom.get("type") == "polyline",
            f"type={geom.get('type')}",
        )
        all_ok &= _check(
            "polyline has points",
            len(points) >= 2,
            f"count={len(points)}",
        )
        match_status = overlay_meta.get("match_status")
        all_ok &= _check(
            "match_status matched or needs_review",
            match_status in {"matched", "needs_review"},
            f"status={match_status}",
        )

        if args.api_base:
            url = (
                f"{args.api_base.rstrip('/')}/api/projects/{PROJECT_ID}"
                f"/drawings/{MASTER_ID}/overlays?inspection_run_id={RUN_ID}"
            )
            print(f"\n=== V-1 overlays API ===\n  GET {url}")
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    body = json.loads(resp.read().decode())
                api_geom = (body[0].get("geometry") if body else {}) or {}
                api_points = api_geom.get("points") if isinstance(api_geom.get("points"), list) else []
                all_ok &= _check(
                    "API returns polyline overlay",
                    api_geom.get("type") == "polyline" and len(api_points) >= 2,
                    f"type={api_geom.get('type')} points={len(api_points)}",
                )
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                all_ok &= _check("API reachable", False, str(exc))

        print("\n=== Manual (UI) ===")
        print(
            "  Open project 2 → master drawing 661 → run 447 in workspace.\n"
            "  Confirm a POLYLINE (not just a rect) renders along the SS corridor."
        )
        print(f"\nGATE: {'PASS' if all_ok else 'FAIL'}")
        return 0 if all_ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
