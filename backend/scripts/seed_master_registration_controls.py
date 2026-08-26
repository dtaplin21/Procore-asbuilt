#!/usr/bin/env python3
"""Seed manual master registration control points for campus plans without N/E OCR.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/seed_master_registration_controls.py
    ./venv/bin/python scripts/seed_master_registration_controls.py --dry-run
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
from database import SessionLocal  # noqa: E402
from models.drawing_survey_point import DrawingSurveyPoint  # noqa: E402
from services.evidence_investigation_persistence import (  # noqa: E402
    _apply_registration_transform_to_evidence,
)
from models.models import EvidenceRecord  # noqa: E402

# UCSF Run #642 golden registration control (station-only on master).
MASTER_ID = 661
AUX_ID = 1084
EVIDENCE_ID = 632
SEED_SOURCE = "manual"

_UCSF_642_CONTROLS = (
    {
        "station": "11+14.23",
        "master_centroid": (0.518, 0.472),
        "notes": "Run 642 campus anchor for aux C4.20 station 11+14.23",
    },
)


def _bbox_for_centroid(x: float, y: float, *, half: float = 0.004) -> dict[str, float]:
    return {
        "x0": x - half,
        "y0": y - half,
        "x1": x + half,
        "y1": y + half,
    }


def seed_master_controls(*, dry_run: bool) -> int:
    db = SessionLocal()
    inserted = 0
    try:
        for control in _UCSF_642_CONTROLS:
            station = str(control["station"])
            centroid = control["master_centroid"]
            x, y = float(centroid[0]), float(centroid[1])
            existing = (
                db.query(DrawingSurveyPoint)
                .filter(
                    DrawingSurveyPoint.drawing_id == MASTER_ID,
                    DrawingSurveyPoint.source == SEED_SOURCE,
                    DrawingSurveyPoint.station == station,
                )
                .first()
            )
            bbox = _bbox_for_centroid(x, y)
            if existing is not None:
                print(
                    f"  update master {MASTER_ID} station={station} "
                    f"id={existing.id} bbox={bbox}"
                )
                if not dry_run:
                    setattr(existing, "label_bbox_json", bbox)
                    setattr(
                        existing,
                        "meta_json",
                        {
                            "seed": "ucsf_642_registration",
                            "pairing": "station",
                            "notes": control.get("notes"),
                        },
                    )
                continue

            print(f"  insert master {MASTER_ID} station={station} centroid=({x}, {y})")
            if dry_run:
                inserted += 1
                continue

            db.add(
                DrawingSurveyPoint(
                    drawing_id=MASTER_ID,
                    page=1,
                    northing=0.0,
                    easting=0.0,
                    station=station,
                    label_bbox_json=bbox,
                    source=SEED_SOURCE,
                    ocr_confidence=1.0,
                    meta_json={
                        "seed": "ucsf_642_registration",
                        "pairing": "station",
                        "notes": control.get("notes"),
                    },
                )
            )
            inserted += 1

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
            print(f"Evidence {EVIDENCE_ID} registration_transform persisted: {bool(meta.get('registration_transform'))}")

        return inserted
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing.",
    )
    args = parser.parse_args()
    seed_master_controls(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
