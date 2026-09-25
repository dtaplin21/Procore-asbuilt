#!/usr/bin/env python3
"""Re-index master drawings with Document AI (Phase 6 backfill).

Runs the same pipeline as ``run_drawing_index_job`` for each drawing id.
Requires ``DOCUMENT_AI_ENABLED=true``, GCP config, and ``processing_status=ready``.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/backfill_document_ai_index.py --project-id 688 --drawing-ids 1691
    ./venv/bin/python scripts/backfill_document_ai_index.py --project-id 688 --all-masters
    ./venv/bin/python scripts/backfill_document_ai_index.py --project-id 688 --drawing-ids 1691 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

from config import document_ai_configured, settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models.models import Drawing, Project  # noqa: E402
from services.drawing_index_jobs import run_drawing_index_job  # noqa: E402


def _parse_drawing_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return ids


def _master_drawing_ids(session, project_id: int) -> list[int]:
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")
    master_id = cast(int | None, project.master_drawing_id)
    if master_id is not None:
        return [master_id]
    rows = (
        session.query(Drawing)
        .filter(Drawing.project_id == project_id)
        .order_by(Drawing.id.asc())
        .all()
    )
    return [cast(int, row.id) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill master drawing index with Document AI.")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument(
        "--drawing-ids",
        type=str,
        default="",
        help="Comma-separated drawing ids (default: project master_drawing_id)",
    )
    parser.add_argument(
        "--all-masters",
        action="store_true",
        help="Index every drawing row in the project (not only canonical master)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not settings.document_ai_enabled:
        print("DOCUMENT_AI_ENABLED is false — enable before backfill.", file=sys.stderr)
        return 1
    if not document_ai_configured():
        print("Document AI GCP env vars incomplete (see Notes/ai google implementation.md).", file=sys.stderr)
        return 1
    if not settings.drawing_index_enabled:
        print("DRAWING_INDEX_ENABLED is false.", file=sys.stderr)
        return 1

    session = SessionLocal()
    try:
        if args.drawing_ids:
            drawing_ids = _parse_drawing_ids(args.drawing_ids)
        elif args.all_masters:
            rows = (
                session.query(Drawing)
                .filter(Drawing.project_id == int(args.project_id))
                .order_by(Drawing.id.asc())
                .all()
            )
            drawing_ids = [cast(int, row.id) for row in rows]
        else:
            drawing_ids = _master_drawing_ids(session, int(args.project_id))

        if not drawing_ids:
            print("No drawings to index.", file=sys.stderr)
            return 1

        print(f"Project {args.project_id}: {len(drawing_ids)} drawing(s): {drawing_ids}")
        if args.dry_run:
            for did in drawing_ids:
                drawing = session.get(Drawing, did)
                if drawing is None:
                    print(f"  {did}: NOT FOUND")
                    continue
                print(
                    f"  {did}: processing_status={drawing.processing_status} "
                    f"index_status={drawing.index_status} name={drawing.name!r}"
                )
            return 0

        failed: list[int] = []
        for did in drawing_ids:
            drawing = session.get(Drawing, did)
            if drawing is None:
                print(f"Skip {did}: not found", file=sys.stderr)
                failed.append(did)
                continue
            if cast(int, drawing.project_id) != int(args.project_id):
                print(f"Skip {did}: wrong project", file=sys.stderr)
                failed.append(did)
                continue
            try:
                result = run_drawing_index_job(did, session)
                print(
                    f"OK {did}: pages={result.pages} tokens={result.text_elements} "
                    f"document_ai={result.document_ai_stats}"
                )
            except Exception as exc:
                print(f"FAIL {did}: {exc}", file=sys.stderr)
                failed.append(did)

        return 1 if failed else 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
