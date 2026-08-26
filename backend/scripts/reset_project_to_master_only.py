#!/usr/bin/env python3
"""Hard-reset a project to master drawing only and wipe the job queue.

Removes all JobQueue rows, deletes every non-master drawing on the project
(via StorageService.delete_drawing_hard), and clears stale evidence
investigation cache on that project.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/reset_project_to_master_only.py --project-id 2
    ./venv/bin/python scripts/reset_project_to_master_only.py --project-id 2 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from database import SessionLocal  # noqa: E402
from models.models import Drawing, EvidenceRecord, JobQueue, Project  # noqa: E402
from services.storage import StorageService  # noqa: E402


def reset_project_to_master_only(
    *,
    project_id: int,
    dry_run: bool,
) -> None:
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")

        master_drawing_id = cast_int(getattr(project, "master_drawing_id", None))
        if master_drawing_id is None:
            raise ValueError(
                f"Project {project_id} has no master_drawing_id; set master before reset."
            )

        master = db.get(Drawing, master_drawing_id)
        if master is None or int(master.project_id) != project_id:
            raise ValueError(
                f"Master drawing {master_drawing_id} missing or not in project {project_id}"
            )

        job_count = db.query(JobQueue).count()
        drawings = (
            db.query(Drawing)
            .filter(Drawing.project_id == project_id)
            .order_by(Drawing.id.asc())
            .all()
        )
        to_delete = [d for d in drawings if int(d.id) != master_drawing_id]
        evidence_rows = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.project_id == project_id)
            .order_by(EvidenceRecord.id.asc())
            .all()
        )

        print(f"Project {project_id} master={master_drawing_id} ({master.name})")
        print(f"  job_queue rows to delete: {job_count}")
        print(f"  drawings to keep: 1")
        print(f"  drawings to delete: {len(to_delete)}")
        for drawing in to_delete:
            print(
                f"    - {drawing.id} {drawing.name!r} "
                f"source={drawing.source} status={drawing.processing_status}/{drawing.index_status}"
            )
        print(f"  evidence rows to clear investigation cache: {len(evidence_rows)}")

        if dry_run:
            print("Dry run — no changes made.")
            return

        deleted_jobs = db.query(JobQueue).delete(synchronize_session=False)
        db.commit()
        print(f"Deleted {deleted_jobs} job_queue row(s).")

        storage = StorageService(db)
        for drawing in to_delete:
            did = int(drawing.id)
            storage.delete_drawing_hard(project_id, did)
            print(f"Deleted drawing {did}.")

        cleared = 0
        for evidence in evidence_rows:
            meta = dict(evidence.meta or {})
            changed = False
            if meta.pop("matchInvestigation", None) is not None:
                changed = True
            if meta.pop("registration_transform", None) is not None:
                changed = True
            if changed:
                evidence.meta = meta  # type: ignore[assignment]
                cleared += 1
        if cleared:
            db.commit()
            print(f"Cleared investigation/registration cache on {cleared} evidence row(s).")

        remaining = (
            db.query(Drawing)
            .filter(Drawing.project_id == project_id)
            .order_by(Drawing.id.asc())
            .all()
        )
        print(f"Done. Project {project_id} now has {len(remaining)} drawing(s):")
        for drawing in remaining:
            print(f"  {drawing.id} {drawing.name!r}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def cast_int(value: object) -> int:
    if value is None:
        raise ValueError("expected int")
    return int(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    reset_project_to_master_only(project_id=args.project_id, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
