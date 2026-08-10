#!/usr/bin/env python3
"""Evaluate location-match orchestrator against PR-G ground-truth labels."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from database import SessionLocal  # noqa: E402
from services.location_match_eval import (  # noqa: E402
    evaluate_labels,
    load_eval_labels_from_db,
    load_eval_labels_from_json,
)

DEFAULT_LABELS = BACKEND_ROOT / "tests/fixtures/location_match_labels.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS,
        help="Path to labels JSON fixture",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Load labels from location_match_labels table instead of JSON",
    )
    parser.add_argument("--min-iou", type=float, default=0.30)
    parser.add_argument("--min-pass-rate", type=float, default=0.80)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON report to this path",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.from_db:
            labels = load_eval_labels_from_db(db)
        else:
            labels_path = args.labels
            if not labels_path.is_absolute():
                labels_path = BACKEND_ROOT / labels_path
            if not labels_path.exists():
                print(f"Labels file not found: {labels_path}", file=sys.stderr)
                return 1
            labels = load_eval_labels_from_json(str(labels_path))

        if not labels:
            print("No labels to evaluate.", file=sys.stderr)
            return 1

        summary = evaluate_labels(
            db,
            labels,
            min_iou=args.min_iou,
            min_pass_rate=args.min_pass_rate,
        )
        report = summary.to_dict()

        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote report to {args.output}")

        print(
            f"Evaluated {summary.evaluated}/{summary.total} labels "
            f"({summary.skipped} skipped); "
            f"pass_rate={summary.pass_rate:.2%} "
            f"(min {summary.min_pass_rate:.0%}); "
            f"coordinate_false_positives={summary.coordinate_false_positives}"
        )

        for result in summary.results:
            if result.skipped:
                print(f"  SKIP {result.label_id}: {result.skip_reason}")
                continue
            status = "PASS" if result.passed else "FAIL"
            iou_text = f" iou={result.iou:.3f}" if result.iou is not None else ""
            print(
                f"  {status} {result.label_id}: "
                f"{result.actual_method}/{result.actual_match_status}{iou_text} "
                f"— {result.notes}"
            )

        print("GATE:", "PASS" if summary.passed_gate else "FAIL")
        return 0 if summary.passed_gate else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
