#!/usr/bin/env python3
"""Run legend exemplar grounding and persist hits to the database.

Requires ``DOCUMENT_AI_GROUNDING_ENABLED=true`` and Document AI env vars.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/run_legend_grounding.py \\
        --drawing-id 1691 --project-id 688 \\
        --legend-bbox 0.70,0.02,0.98,0.135 \\
        --output-dir /tmp/legend_icons_1691
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import cast

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from ai.pipelines.legend_grounding import (  # noqa: E402
    DocumentAiGroundingProvider,
    manifest_entry_to_legend_icon,
    run_grounding_for_legend_entries,
)
from ai.pipelines.legend_icon_extraction import (  # noqa: E402
    parse_legend_bbox_arg,
    render_pdf_page_image,
)
from database import SessionLocal  # noqa: E402
from models.drawing_text_element import DrawingTextElement  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.file_storage import resolve_stored_file_path  # noqa: E402
from services.legend_grounding_service import (  # noqa: E402
    grounding_hits_to_json,
    grounding_is_available,
    list_grounding_hits,
    page_words_from_text_elements,
    run_and_persist_legend_grounding,
)


def _resolve_pdf(session: Session, drawing_id: int) -> Path | None:
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        return None
    storage_key = cast(str | None, drawing.storage_key)
    if not storage_key:
        return None
    resolved = resolve_stored_file_path(storage_key)
    if resolved is None or not resolved.is_file():
        return None
    return resolved


def _load_elements(session: Session, drawing_id: int, page: int) -> list[DrawingTextElement]:
    return (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.master_drawing_id == int(drawing_id),
            DrawingTextElement.page == int(page),
        )
        .order_by(DrawingTextElement.id.asc())
        .all()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run legend grounding and persist hits.")
    parser.add_argument("--project-id", type=int, default=688)
    parser.add_argument("--drawing-id", type=int, required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--legend-bbox", type=str, required=True)
    parser.add_argument("--output-dir", type=str, default="legend_icons_out")
    parser.add_argument(
        "--manifest",
        type=str,
        default="",
        help="Optional existing legend_manifest.json (skip icon re-extract)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write DB rows")
    parser.add_argument("--list-only", action="store_true", help="Print persisted hits and exit")
    args = parser.parse_args()

    if not grounding_is_available() and not args.list_only:
        print(
            "Legend grounding disabled or Document AI not configured. "
            "Set DOCUMENT_AI_GROUNDING_ENABLED=true and DOCUMENT_AI_* vars.",
            file=sys.stderr,
        )
        return 1

    legend_bbox = parse_legend_bbox_arg(args.legend_bbox)
    session = SessionLocal()
    try:
        if args.list_only:
            rows = list_grounding_hits(
                session,
                master_drawing_id=int(args.drawing_id),
                page=int(args.page),
            )
            print(json.dumps(grounding_hits_to_json(rows), indent=2))
            return 0

        pdf_path = _resolve_pdf(session, int(args.drawing_id))
        if pdf_path is None:
            print("Master PDF not found.", file=sys.stderr)
            return 1

        elements = _load_elements(session, int(args.drawing_id), int(args.page))

        if args.dry_run and args.manifest:
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            raw_entries = manifest.get("rows", manifest)
            entries = [manifest_entry_to_legend_icon(item) for item in raw_entries]
            full_image = render_pdf_page_image(pdf_path, page=int(args.page))
            provider = DocumentAiGroundingProvider()
            hits = run_grounding_for_legend_entries(
                full_page_image=full_image,
                entries=entries,
                provider=provider,
                full_page_words=page_words_from_text_elements(elements),
            )
            print(json.dumps({k: [h.__dict__ for h in v] for k, v in hits.items()}, indent=2))
            return 0

        if args.dry_run:
            print("--dry-run requires --manifest", file=sys.stderr)
            return 1

        run_id, hits_by_label, persisted = run_and_persist_legend_grounding(
            session,
            pdf_path=str(pdf_path),
            master_drawing_id=int(args.drawing_id),
            page=int(args.page),
            legend_bbox_fractional=legend_bbox,
            elements=elements,
            output_dir=args.output_dir,
        )
        total = sum(len(v) for v in hits_by_label.values())
        print(f"grounding_run_id={run_id} persisted_hits={total}")
        for label, hits in hits_by_label.items():
            print(f"  {label!r}: {len(hits)}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
