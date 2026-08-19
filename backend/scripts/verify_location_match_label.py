#!/usr/bin/env python3
"""Verify one location-match label or evidence/master pair.

Examples (from ``backend/``)::

    ./venv/bin/python scripts/verify_location_match_label.py \\
        --label-id ucsf-435-ss-corridor --from-db
    ./venv/bin/python scripts/verify_location_match_label.py \\
        --label-id ucsf-435-ss-corridor \\
        --labels tests/fixtures/location_match_labels
    ./venv/bin/python scripts/verify_location_match_label.py \\
        --evidence-id 10 --master-drawing-id 20
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
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
from models.location_match_label import LocationMatchLabel  # noqa: E402
from models.models import EvidenceRecord  # noqa: E402
from services.evidence_survey_extraction import (  # noqa: E402
    extract_survey_points_from_evidence,
    persist_evidence_survey_meta,
)
from services.file_storage import get_file_path  # noqa: E402
from services.inspection_matching_jobs import run_inspection_match_job  # noqa: E402
from services.location_match_eval import (  # noqa: E402
    EvalLabel,
    evaluate_label_result,
    eval_label_from_row,
    load_eval_labels_from_json,
)
from services.match_candidate_scope import build_match_scope  # noqa: E402

DEFAULT_LABELS = BACKEND_ROOT / "tests/fixtures/location_match_labels"


def _load_label_by_id(
    *,
    label_id: str,
    from_db: bool,
    labels_path: Path,
    session,
) -> EvalLabel:
    if from_db:
        row = session.get(LocationMatchLabel, label_id)
        if row is None:
            raise ValueError(f"Label {label_id!r} not found in location_match_labels")
        return eval_label_from_row(row)

    labels = load_eval_labels_from_json(labels_path)
    for label in labels:
        if label.label_id == label_id:
            return label
    raise ValueError(f"Label {label_id!r} not found in {labels_path}")


def _ad_hoc_label(
    *,
    evidence_id: int,
    master_drawing_id: int,
    expected_method: str | None,
    expected_match_status: str | None,
) -> EvalLabel:
    return EvalLabel(
        label_id=f"adhoc-{evidence_id}-{master_drawing_id}",
        suite="adhoc",
        project_id=0,
        evidence_id=evidence_id,
        inspection_run_id=None,
        master_drawing_id=master_drawing_id,
        evidence_fixture_path=None,
        master_bbox_json={
            "type": "rect",
            "page": 1,
            "x": 0.0,
            "y": 0.0,
            "width": 0.0,
            "height": 0.0,
        },
        expected_method=expected_method or "coordinate_lookup",
        expected_match_status=expected_match_status or "matched",
        rotation_deg=None,
        has_coordinate_signal=True,
        has_station_signal=False,
        has_reference_signal=False,
        evidence_kind="form",
        notes="Ad-hoc verify (no ground-truth bbox; IoU skipped if area is zero).",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-id", type=str, default=None)
    parser.add_argument("--evidence-id", type=int, default=None)
    parser.add_argument("--master-drawing-id", type=int, default=None)
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS,
        help="JSON file or suite directory when resolving --label-id without --from-db",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Load --label-id from location_match_labels table",
    )
    parser.add_argument("--expected-method", type=str, default=None)
    parser.add_argument("--expected-match-status", type=str, default=None)
    parser.add_argument("--min-iou", type=float, default=0.30)
    parser.add_argument("--refresh-survey", action="store_true")
    parser.add_argument("--persist-match", action="store_true")
    args = parser.parse_args()

    has_label = args.label_id is not None
    has_pair = args.evidence_id is not None and args.master_drawing_id is not None
    if not has_label and not has_pair:
        parser.error("Provide --label-id OR both --evidence-id and --master-drawing-id")
    if has_label and (args.evidence_id is not None or args.master_drawing_id is not None):
        parser.error("Do not mix --label-id with --evidence-id/--master-drawing-id")

    db = SessionLocal()
    try:
        if has_label:
            labels_path = args.labels
            if not labels_path.is_absolute():
                labels_path = BACKEND_ROOT / labels_path
            label = _load_label_by_id(
                label_id=str(args.label_id),
                from_db=args.from_db,
                labels_path=labels_path,
                session=db,
            )
            if label.evidence_id is None:
                print(f"Label {label.label_id!r} has no evidence_id; cannot verify live match")
                return 1
            overrides: dict[str, Any] = {}
            if args.expected_method:
                overrides["expected_method"] = args.expected_method
            if args.expected_match_status:
                overrides["expected_match_status"] = args.expected_match_status
            if overrides:
                label = replace(label, **overrides)
        else:
            label = _ad_hoc_label(
                evidence_id=int(args.evidence_id),
                master_drawing_id=int(args.master_drawing_id),
                expected_method=args.expected_method,
                expected_match_status=args.expected_match_status,
            )

        evidence_id = cast(int, label.evidence_id)
        master_drawing_id = label.master_drawing_id
        evidence = db.get(EvidenceRecord, evidence_id)
        if evidence is None:
            print(f"Evidence {evidence_id} not found")
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
            evidence_id=evidence_id,
            master_drawing_id=master_drawing_id,
        )
        print("label_id:", label.label_id)
        print("suite:", label.suite)
        print("sheet_refs:", scope.sheet_refs[:8], "..." if len(scope.sheet_refs) > 8 else "")
        print("auxiliary_drawing_ids:", scope.auxiliary_drawing_ids)

        master_pts = (
            db.query(DrawingSurveyPoint)
            .filter(DrawingSurveyPoint.drawing_id == master_drawing_id)
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

        page_raw = label.master_bbox_json.get("page", 1)
        page = int(page_raw) if page_raw is not None else 1
        result = resolve_evidence_location(
            db,
            evidence_id,
            master_drawing_id,
            page=page,
        )
        status = match_status_from_result(result)
        print("\nresolve_evidence_location:")
        print("  method:", result.method.value)
        print("  confidence:", result.confidence)
        print("  match_status:", status)
        print("  bbox:", result.bbox_fractional)
        print("  notes:", result.notes)

        if args.persist_match:
            job_payload: dict[str, Any] = {
                "inspection_id": str(evidence_id),
                "drawing_id": str(master_drawing_id),
                "page": page,
            }
            run_id = args.run_id if args.run_id is not None else label.inspection_run_id
            if run_id is not None:
                job_payload["inspection_run_id"] = run_id
            job_status = run_inspection_match_job(job_payload, db)
            print("\nrun_inspection_match_job:", job_status)

        outcome = evaluate_label_result(
            label,
            result,
            status,
            min_iou=args.min_iou,
        )
        print("\nexpected_method:", label.expected_method)
        print("expected_match_status:", label.expected_match_status)
        print("min_iou:", args.min_iou)
        if outcome.iou is not None:
            print("iou:", f"{outcome.iou:.3f}")
        print("notes:", outcome.notes)
        print("VERIFY:", "PASS" if outcome.passed else "FAIL")
        return 0 if outcome.passed else 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
