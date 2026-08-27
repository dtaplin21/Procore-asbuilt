#!/usr/bin/env python3
"""Seed manual registration control points for campus plans without N/E OCR.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/seed_master_registration_controls.py
    ./venv/bin/python scripts/seed_master_registration_controls.py --dry-run
    ./venv/bin/python scripts/seed_master_registration_controls.py --rerun-match
"""

from __future__ import annotations

import argparse
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from ai.pipelines.registration_from_survey import (  # noqa: E402
    compute_registration_for_linked_drawings,
    match_control_points,
)
from ai.pipelines.station_range_extractor import (  # noqa: E402
    StationRangeResult,
    extract_station_range_for_drawings,
)
from database import SessionLocal  # noqa: E402
from models.drawing_survey_point import DrawingSurveyPoint  # noqa: E402
from services.evidence_investigation_persistence import (  # noqa: E402
    _apply_registration_transform_to_evidence,
    _apply_station_range_to_evidence,
)
from models.models import EvidenceRecord  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# UCSF run 663 / evidence 665 / master 661 / aux C4.20 install sheet 1501.
MASTER_ID = 661
AUX_ID = 1501
EVIDENCE_ID = 665
RUN_ID = 663
PROJECT_ID = 2
SEED_SOURCE = "manual"

# Golden campus polyline endpoints (ucsf-642-ss-run) + matching aux plan OCR centroids.
_UCSF_MASTER_CONTROLS = (
    {
        "station": "10+00",
        "centroid": (0.451, 0.464),
        "notes": "Campus trench start STA 10+00 (golden eval)",
    },
    {
        "station": "10+90.95",
        "centroid": (0.674, 0.569),
        "notes": "Campus trench end STA 10+90.95 (golden eval)",
    },
)

_UCSF_AUX_CONTROLS = (
    {
        "station": "10+00",
        "centroid": (0.25743055555555555, 0.2),
        "notes": "C4.20 plan trench start (SSMH/STA chain)",
    },
    {
        "station": "10+90.95",
        "centroid": (0.29743055555555553, 0.27156250000000004),
        "notes": "C4.20 plan station label 10+90.95",
    },
)

# Legacy single-point control — removed so 2-point scale+translate fit is used.
_LEGACY_STATIONS_TO_REMOVE = ("11+14.23",)


def _bbox_for_centroid(x: float, y: float, *, half: float = 0.004) -> dict[str, float]:
    return {
        "x0": x - half,
        "y0": y - half,
        "x1": x + half,
        "y1": y + half,
    }


def _remove_legacy_master_controls(session: Session, *, dry_run: bool) -> None:
    for station in _LEGACY_STATIONS_TO_REMOVE:
        rows = (
            session.query(DrawingSurveyPoint)
            .filter(
                DrawingSurveyPoint.drawing_id == MASTER_ID,
                DrawingSurveyPoint.source == SEED_SOURCE,
                DrawingSurveyPoint.station == station,
            )
            .all()
        )
        for row in rows:
            print(f"  remove legacy master {MASTER_ID} station={station} id={row.id}")
            if not dry_run:
                session.delete(row)


def _upsert_manual_control(
    session: Session,
    *,
    drawing_id: int,
    station: str,
    centroid: tuple[float, float],
    notes: str | None,
    dry_run: bool,
) -> int:
    x, y = float(centroid[0]), float(centroid[1])
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
    meta = {
        "seed": "ucsf_trench_registration",
        "pairing": "station",
        "notes": notes,
    }
    if existing is not None:
        print(
            f"  update drawing {drawing_id} station={station} "
            f"id={existing.id} centroid=({x}, {y})"
        )
        if dry_run:
            return 0
        setattr(existing, "label_bbox_json", bbox)
        setattr(existing, "meta_json", meta)
        return 0

    print(f"  insert drawing {drawing_id} station={station} centroid=({x}, {y})")
    if dry_run:
        return 1

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
            meta_json=meta,
        )
    )
    return 1


def seed_registration_controls(*, dry_run: bool) -> int:
    db = SessionLocal()
    inserted = 0
    try:
        _remove_legacy_master_controls(db, dry_run=dry_run)

        for control in _UCSF_MASTER_CONTROLS:
            inserted += _upsert_manual_control(
                db,
                drawing_id=MASTER_ID,
                station=str(control["station"]),
                centroid=control["centroid"],
                notes=control.get("notes"),
                dry_run=dry_run,
            )

        for control in _UCSF_AUX_CONTROLS:
            inserted += _upsert_manual_control(
                db,
                drawing_id=AUX_ID,
                station=str(control["station"]),
                centroid=control["centroid"],
                notes=control.get("notes"),
                dry_run=dry_run,
            )

        if dry_run:
            print(f"Dry run: would upsert {inserted} manual control point(s).")
            return inserted

        db.commit()

        pairs = match_control_points(
            db,
            aux_drawing_id=AUX_ID,
            master_drawing_id=MASTER_ID,
        )
        transform, count, aux_drawing_id = compute_registration_for_linked_drawings(
            db,
            linked_drawing_ids=[AUX_ID],
            master_drawing_id=MASTER_ID,
        )
        print(f"Registration pairs={len(pairs)} count={count} aux={aux_drawing_id}")
        for pair in pairs:
            print(
                f"  pair station={pair.station} method={pair.pairing_method} "
                f"aux={pair.aux_xy} master={pair.master_xy}"
            )
        print(f"Transform: {transform}")

        evidence = db.get(EvidenceRecord, EVIDENCE_ID)
        if evidence is not None and transform is not None:
            _apply_registration_transform_to_evidence(
                evidence,
                linked_drawing_ids=[AUX_ID],
                master_drawing_id=MASTER_ID,
                session=db,
            )
            db.commit()
            meta = evidence.meta if isinstance(evidence.meta, dict) else {}
            print(
                f"Evidence {EVIDENCE_ID} registration_transform persisted: "
                f"{bool(meta.get('registration_transform'))}"
            )

        if evidence is not None:
            inv = (evidence.meta or {}).get("matchInvestigation") or {}
            linked_ids = inv.get("linked_drawing_ids") or [AUX_ID]
            station_range = backfill_evidence_station_range(
                db,
                evidence_id=EVIDENCE_ID,
                linked_drawing_ids=[int(x) for x in linked_ids],
            )
            print(
                f"Evidence {EVIDENCE_ID} station range: "
                f"{station_range.station_from} → {station_range.station_to}"
            )

        return inserted
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def backfill_evidence_station_range(
    session: Session,
    *,
    evidence_id: int,
    linked_drawing_ids: list[int],
) -> StationRangeResult:
    """Re-extract and persist station range when aux drawings finish indexing."""
    station_range = extract_station_range_for_drawings(session, linked_drawing_ids)
    evidence = session.get(EvidenceRecord, evidence_id)
    if evidence is not None:
        _apply_station_range_to_evidence(evidence, station_range)
        session.commit()
    return station_range


def rerun_inspection_match() -> str:
    from services.inspection_matching_jobs import run_inspection_match_job

    db = SessionLocal()
    try:
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
        return str(status)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing.",
    )
    parser.add_argument(
        "--rerun-match",
        action="store_true",
        help="Re-run inspection match for run 663 after seeding.",
    )
    args = parser.parse_args()
    seed_registration_controls(dry_run=args.dry_run)
    if args.rerun_match and not args.dry_run:
        status = rerun_inspection_match()
        print(f"Re-ran match job → {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
