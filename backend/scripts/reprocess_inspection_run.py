#!/usr/bin/env python3
"""Re-investigate evidence, seed registration, and re-run inspection match.

Usage (from backend/)::

    ./venv/bin/python scripts/reprocess_inspection_run.py --run-id 734
    ./venv/bin/python scripts/reprocess_inspection_run.py --run-id 734 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, cast

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from ai.pipelines.registration_from_survey import (  # noqa: E402
    compute_registration_for_linked_drawings,
    match_control_points,
)
from database import SessionLocal  # noqa: E402
from models.drawing_survey_point import DrawingSurveyPoint  # noqa: E402
from models.inspection_run import InspectionRun  # noqa: E402
from models.models import EvidenceRecord  # noqa: E402
from services.evidence_investigation_persistence import (  # noqa: E402
    _apply_registration_transform_to_evidence,
)
from services.inspection_matching_jobs import run_inspection_match_job  # noqa: E402

SEED_SOURCE = "manual"

# Master station hits from run 734 match candidates; aux from drawing 1872 plan OCR.
_PROJECT_1348_CONTROLS: tuple[tuple[int, str, tuple[float, float], str], ...] = (
    (
        1722,
        "10+90.95",
        (0.2084375, 0.8378472),
        "Master profile station label (run 734 station_lookup winner bbox)",
    ),
    (
        1722,
        "11+14.23",
        (0.2797917, 0.69),
        "Master profile station label (run 734 rank-2 station_lookup bbox)",
    ),
    (
        1872,
        "10+90.95",
        (0.1621528, 0.2084375),
        "Aux plan SSMH label bbox centroid (drawing 1872 auto_index)",
    ),
    (
        1872,
        "11+14.23",
        (0.3409028, 0.2760417),
        "Aux plan station label centroid (auto_index_station row)",
    ),
)


def _bbox_for_centroid(x: float, y: float) -> dict[str, float]:
    pad = 0.008
    return {"x0": x - pad, "y0": y - pad, "x1": x + pad, "y1": y + pad}


def _upsert_manual_control(
    session,
    *,
    drawing_id: int,
    station: str,
    centroid: tuple[float, float],
    notes: str,
    dry_run: bool,
) -> None:
    x, y = centroid
    existing = (
        session.query(DrawingSurveyPoint)
        .filter(
            DrawingSurveyPoint.drawing_id == drawing_id,
            DrawingSurveyPoint.source == SEED_SOURCE,
            DrawingSurveyPoint.station == station,
        )
        .first()
    )
    bbox = _bbox_for_centroid(x, y)
    meta_json = {"seed": "project_1348_reprocess", "pairing": "station", "notes": notes}
    if existing is not None:
        print(f"  update drawing {drawing_id} station={station} id={existing.id}")
        if dry_run:
            return
        setattr(existing, "label_bbox_json", bbox)
        setattr(existing, "meta_json", meta_json)
        return
    print(f"  insert drawing {drawing_id} station={station} centroid=({x:.4f}, {y:.4f})")
    if dry_run:
        return
    session.add(
        DrawingSurveyPoint(
            drawing_id=drawing_id,
            page=1,
            northing=0.0,
            easting=0.0,
            station=station,
            label_bbox_json=bbox,
            source=SEED_SOURCE,
            ocr_confidence=1.0,
            meta_json=meta_json,
        )
    )


def seed_project_1348_registration(session, *, dry_run: bool) -> None:
    print("Seeding manual registration controls (project 1348)...")
    for drawing_id, station, centroid, notes in _PROJECT_1348_CONTROLS:
        _upsert_manual_control(
            session,
            drawing_id=drawing_id,
            station=station,
            centroid=centroid,
            notes=notes,
            dry_run=dry_run,
        )
    if dry_run:
        return
    session.flush()
    pairs = match_control_points(session, aux_drawing_id=1872, master_drawing_id=1722)
    transform, count, aux_id = compute_registration_for_linked_drawings(
        session,
        linked_drawing_ids=[1872],
        master_drawing_id=1722,
    )
    print(f"Registration pairs={len(pairs)} control_count={count} aux={aux_id} transform={transform}")


def reprocess_run(
    *,
    run_id: int,
    dry_run: bool,
    skip_match: bool,
) -> int:
    db = SessionLocal()
    try:
        run = db.get(InspectionRun, run_id)
        if run is None:
            print(f"Inspection run {run_id} not found")
            return 1
        evidence_id = cast(int | None, run.evidence_id)
        master_id = cast(int, run.master_drawing_id)
        project_id = cast(int, run.project_id)
        if evidence_id is None:
            print(f"Run {run_id} has no evidence_id")
            return 1

        print(
            f"Run {run_id}: evidence={evidence_id} master={master_id} project={project_id}"
        )

        seed_project_1348_registration(db, dry_run=dry_run)

        if dry_run:
            print("Dry run — skipping match job.")
            return 0

        db.commit()

        evidence = db.get(EvidenceRecord, evidence_id)
        if evidence is not None:
            _apply_registration_transform_to_evidence(
                evidence,
                linked_drawing_ids=[1870, 1871, 1872],
                master_drawing_id=master_id,
                session=db,
            )
            db.commit()
            meta = evidence.meta if isinstance(evidence.meta, dict) else {}
            print(
                "Evidence registration_transform persisted:",
                bool(meta.get("registration_transform")),
            )

        if skip_match:
            print("Skipping inspection match (--skip-match).")
            return 0

        status = run_inspection_match_job(
            {
                "inspection_id": str(evidence_id),
                "drawing_id": master_id,
                "page": 1,
                "inspection_run_id": run_id,
                "project_id": project_id,
                "force_investigate": True,
            },
            db,
        )
        db.commit()
        print(f"Match job finished with status={status}")

        evidence = db.get(EvidenceRecord, evidence_id)
        if evidence is not None:
            print("text_content length:", len(evidence.text_content or ""))
            meta = cast(dict[str, Any], evidence.meta or {})
            print("merged_text_length meta:", meta.get("merged_text_length"))

        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, default=734)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-match",
        action="store_true",
        help="Only seed registration; do not re-run match (investigation runs at match time).",
    )
    args = parser.parse_args()
    return reprocess_run(run_id=args.run_id, dry_run=args.dry_run, skip_match=args.skip_match)


if __name__ == "__main__":
    raise SystemExit(main())
