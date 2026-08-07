#!/usr/bin/env python3
"""Verify PR-E golden case: evidence 357 on master 661 (run 435)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, cast

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from ai.pipelines.location_match_orchestrator import (  # noqa: E402
    match_status_from_result,
    resolve_evidence_location,
)
from database import SessionLocal  # noqa: E402
from models.drawing_survey_point import DrawingSurveyPoint  # noqa: E402
from models.models import EvidenceRecord  # noqa: E402
from services.evidence_survey_extraction import (  # noqa: E402
    extract_survey_points_from_evidence,
    persist_evidence_survey_meta,
)
from services.file_storage import get_file_path  # noqa: E402
from services.inspection_matching_jobs import run_inspection_match_job  # noqa: E402
from services.match_candidate_scope import build_match_scope  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-id", type=int, default=357)
    parser.add_argument("--master-drawing-id", type=int, default=661)
    parser.add_argument("--run-id", type=int, default=435)
    parser.add_argument("--refresh-survey", action="store_true")
    parser.add_argument("--persist-match", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        evidence = db.get(EvidenceRecord, args.evidence_id)
        if evidence is None:
            print(f"Evidence {args.evidence_id} not found")
            return 1

        if args.refresh_survey:
            storage_key = cast(str | None, evidence.storage_key)
            if storage_key is None or not storage_key.strip():
                print("Evidence has no storage_key")
                return 1
            path = get_file_path(storage_key)
            points, scale_json = extract_survey_points_from_evidence(db, evidence, path)
            persist_evidence_survey_meta(evidence, points, scale_json)
            db.commit()
            print(f"Refreshed evidence survey_points: {len(points)}")

        scope = build_match_scope(
            db,
            evidence_id=args.evidence_id,
            master_drawing_id=args.master_drawing_id,
        )
        print("sheet_refs:", scope.sheet_refs[:8], "..." if len(scope.sheet_refs) > 8 else "")
        print("auxiliary_drawing_ids:", scope.auxiliary_drawing_ids)

        master_pts = (
            db.query(DrawingSurveyPoint)
            .filter(DrawingSurveyPoint.drawing_id == args.master_drawing_id)
            .count()
        )
        aux_pts = sum(
            db.query(DrawingSurveyPoint)
            .filter(DrawingSurveyPoint.drawing_id == aux_id)
            .count()
            for aux_id in scope.auxiliary_drawing_ids
        )
        print(f"survey_points master={master_pts} auxiliary={aux_pts}")

        meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
        ev_pts = meta.get("survey_points") or []
        print(f"evidence meta survey_points: {len(ev_pts) if isinstance(ev_pts, list) else 0}")

        result = resolve_evidence_location(
            db,
            args.evidence_id,
            args.master_drawing_id,
            page=1,
        )
        status = match_status_from_result(result)
        print("\nresolve_evidence_location:")
        print("  method:", result.method.value)
        print("  confidence:", result.confidence)
        print("  match_status:", status)
        print("  bbox:", result.bbox_fractional)
        print("  notes:", result.notes)

        if args.persist_match:
            job_status = run_inspection_match_job(
                {
                    "inspection_id": str(args.evidence_id),
                    "drawing_id": str(args.master_drawing_id),
                    "page": 1,
                    "inspection_run_id": args.run_id,
                },
                db,
            )
            print("\nrun_inspection_match_job:", job_status)

        passed = (
            result.method.value == "coordinate_lookup"
            and status in ("matched", "needs_review")
        )
        print("\nE-3:", "PASS" if passed else "FAIL")
        return 0 if passed else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
