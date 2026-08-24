#!/usr/bin/env python3
"""Remove synthetic PRE-2 eval survey seeds from drawing_survey_points.

These rows were inserted manually to unblock coordinate_lookup eval when master
661 had no OCR-indexed N/E pairs. They must not drive production placement.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/remove_baseline_survey_seeds.py
    ./venv/bin/python scripts/remove_baseline_survey_seeds.py --yes
"""

from __future__ import annotations

import argparse
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from database import SessionLocal  # noqa: E402
from models.drawing_survey_point import DrawingSurveyPoint  # noqa: E402

_UNTRUSTED_SOURCES = ("pre2_baseline_seed",)


def remove_baseline_seeds(*, dry_run: bool) -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(DrawingSurveyPoint)
            .filter(DrawingSurveyPoint.source.in_(_UNTRUSTED_SOURCES))
            .order_by(DrawingSurveyPoint.id.asc())
            .all()
        )
        if not rows:
            print("No baseline survey seeds found.")
            return 0

        for row in rows:
            print(
                f"  drawing_id={row.drawing_id} id={row.id} "
                f"N={row.northing} E={row.easting} source={row.source!r}"
            )

        if dry_run:
            print(f"Dry run: would delete {len(rows)} row(s).")
            return len(rows)

        deleted = (
            db.query(DrawingSurveyPoint)
            .filter(DrawingSurveyPoint.source.in_(_UNTRUSTED_SOURCES))
            .delete(synchronize_session=False)
        )
        db.commit()
        print(f"Deleted {deleted} baseline survey seed row(s).")
        return deleted
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Delete without confirmation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List rows that would be deleted.",
    )
    args = parser.parse_args()

    if args.dry_run:
        remove_baseline_seeds(dry_run=True)
        return 0

    if not args.yes:
        try:
            confirm = input(
                "Delete pre2_baseline_seed survey rows from this database? [y/N]: "
            ).strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("y", "yes"):
            print("Aborted.")
            return 1

    remove_baseline_seeds(dry_run=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
