#!/usr/bin/env python3
"""Compare master drawing index tokens for Phase 5 validation (A/B, checklist).

Load tokens from the database and/or TSV exports from
``audit_drawing_index_coverage.py --export``.

Usage (from ``backend/``)::

    # Current DB: source counts + golden keyword checklist
    ./venv/bin/python scripts/compare_index_sources.py --drawing-id 1691 --project-id 688

    # Left gutter (fractional x <= 0.15) — e.g. Highway 24 labels
    ./venv/bin/python scripts/compare_index_sources.py --drawing-id 1691 --project-id 688 --gutter-x-max 0.15

    # Diff two audit TSV exports (pre/post Document AI re-index)
    ./venv/bin/python scripts/compare_index_sources.py \\
        --baseline tokens_1691_tesseract.tsv \\
        --current tokens_1691_docai.tsv

    # DB vs saved baseline TSV
    ./venv/bin/python scripts/compare_index_sources.py \\
        --drawing-id 1691 --project-id 688 \\
        --baseline tokens_1691_baseline.tsv
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

from database import SessionLocal  # noqa: E402
from models.drawing_text_element import DrawingTextElement  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.drawing_index_validation import (  # noqa: E402
    IndexToken,
    default_validation_keywords,
    diff_by_source,
    diff_token_sets,
    keyword_hits,
    load_audit_tsv_file,
    summarize_sources,
)


def _tokens_from_db(*, project_id: int, drawing_id: int) -> list[IndexToken]:
    db = SessionLocal()
    try:
        drawing = db.get(Drawing, drawing_id)
        if drawing is None:
            raise ValueError(f"Drawing {drawing_id} not found")
        if cast(int, drawing.project_id) != project_id:
            print(
                f"Warning: drawing project_id={drawing.project_id} != {project_id}",
                file=sys.stderr,
            )
        rows = (
            db.query(DrawingTextElement)
            .filter(DrawingTextElement.master_drawing_id == int(drawing_id))
            .order_by(DrawingTextElement.page.asc(), DrawingTextElement.id.asc())
            .all()
        )
        tokens: list[IndexToken] = []
        for row in rows:
            bbox = row.bbox_json if isinstance(row.bbox_json, dict) else {}
            x0 = float(bbox.get("x0", 0))
            y0 = float(bbox.get("y0", 0))
            x1 = float(bbox.get("x1", 0))
            y1 = float(bbox.get("y1", 0))
            tokens.append(
                IndexToken(
                    page=cast(int, row.page),
                    centroid_x=(x0 + x1) / 2.0,
                    centroid_y=(y0 + y1) / 2.0,
                    source=str(row.source),
                    text=str(row.text),
                    ocr_confidence=float(cast(float, row.ocr_confidence)),
                )
            )
        return tokens
    finally:
        db.close()


def _print_summary(label: str, tokens: list[IndexToken]) -> None:
    print(f"\n=== {label} ({len(tokens)} tokens) ===")
    print(f"By source: {summarize_sources(tokens)}")


def _print_checklist(
    tokens: list[IndexToken],
    keywords: tuple[str, ...],
    *,
    gutter_x_max: float | None,
    page: int,
) -> None:
    print(f"\n--- Keyword checklist (page={page}, gutter_x_max={gutter_x_max}) ---")
    hits = keyword_hits(tokens, keywords, gutter_x_max=gutter_x_max, page=page)
    for keyword in keywords:
        matched = hits.get(keyword, [])
        status = "OK" if matched else "MISSING"
        print(f"  [{status}] {keyword}: {len(matched)} hit(s)")
        for token in matched[:5]:
            print(
                f"       p{token.page} ({token.centroid_x:.3f},{token.centroid_y:.3f}) "
                f"{token.source!r} {token.text!r}"
            )
        if len(matched) > 5:
            print(f"       ... {len(matched) - 5} more")


def _print_diff(diff_label: str, diff) -> None:
    print(f"\n--- {diff_label} ---")
    print(f"  shared:         {len(diff.shared)}")
    print(f"  only baseline:  {diff.only_baseline_count}")
    print(f"  only current:   {diff.only_current_count}")
    for token in diff.only_current[:25]:
        print(
            f"  + p{token.page} ({token.centroid_x:.3f},{token.centroid_y:.3f}) "
            f"{token.source!r} {token.text!r}"
        )
    if diff.only_current_count > 25:
        print(f"  ... {diff.only_current_count - 25} more only in current")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare indexed drawing tokens (Phase 5).")
    parser.add_argument("--project-id", type=int, default=688)
    parser.add_argument("--drawing-id", type=int, default=0, help="Load current tokens from DB")
    parser.add_argument("--baseline", type=str, default="", help="Baseline audit TSV path")
    parser.add_argument("--current", type=str, default="", help="Current audit TSV path (optional if --drawing-id)")
    parser.add_argument(
        "--keywords",
        type=str,
        default="",
        help="Comma-separated checklist (default: SSMH,MLK,HIGHWAY,...)",
    )
    parser.add_argument(
        "--gutter-x-max",
        type=float,
        default=None,
        help="Only checklist tokens with centroid_x <= this (normalized 0-1)",
    )
    parser.add_argument("--page", type=int, default=1, help="Page for keyword checklist")
    parser.add_argument(
        "--diff-source",
        type=str,
        default="",
        help="When diffing, compare only this source (e.g. document_ai vs document_ai)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable summary on stdout")
    args = parser.parse_args()

    keywords = tuple(
        k.strip()
        for k in (args.keywords.split(",") if args.keywords else default_validation_keywords())
        if k.strip()
    )

    baseline_tokens: list[IndexToken] | None = None
    current_tokens: list[IndexToken] | None = None

    if args.baseline:
        baseline_tokens = load_audit_tsv_file(args.baseline)
    if args.current:
        current_tokens = load_audit_tsv_file(args.current)
    if args.drawing_id:
        current_tokens = _tokens_from_db(
            project_id=int(args.project_id),
            drawing_id=int(args.drawing_id),
        )

    if current_tokens is None and baseline_tokens is None:
        print("Provide --drawing-id and/or --baseline / --current TSV paths.", file=sys.stderr)
        return 1

    if not args.json:
        if baseline_tokens is not None:
            _print_summary("Baseline", baseline_tokens)
        if current_tokens is not None:
            _print_summary("Current", current_tokens)
        if current_tokens is not None:
            _print_checklist(
                current_tokens,
                keywords,
                gutter_x_max=args.gutter_x_max,
                page=int(args.page),
            )
        elif baseline_tokens is not None:
            _print_checklist(
                baseline_tokens,
                keywords,
                gutter_x_max=args.gutter_x_max,
                page=int(args.page),
            )

        if baseline_tokens is not None and current_tokens is not None:
            if args.diff_source:
                diff = diff_by_source(
                    baseline_tokens,
                    current_tokens,
                    source=args.diff_source,
                )
                _print_diff(f"Diff source={args.diff_source!r}", diff)
            else:
                diff = diff_token_sets(baseline_tokens, current_tokens)
                _print_diff("Diff (all sources)", diff)

    summary: dict[str, object] = {
        "keywords": keywords,
        "gutter_x_max": args.gutter_x_max,
        "page": args.page,
    }
    if baseline_tokens is not None:
        summary["baseline"] = {
            "total": len(baseline_tokens),
            "by_source": summarize_sources(baseline_tokens),
        }
    if current_tokens is not None:
        summary["current"] = {
            "total": len(current_tokens),
            "by_source": summarize_sources(current_tokens),
        }
        hits = keyword_hits(
            current_tokens,
            keywords,
            gutter_x_max=args.gutter_x_max,
            page=int(args.page),
        )
        summary["checklist"] = {k: len(v) for k, v in hits.items()}
    if baseline_tokens is not None and current_tokens is not None:
        diff = (
            diff_by_source(baseline_tokens, current_tokens, source=args.diff_source)
            if args.diff_source
            else diff_token_sets(baseline_tokens, current_tokens)
        )
        summary["diff"] = {
            "shared": len(diff.shared),
            "only_baseline": diff.only_baseline_count,
            "only_current": diff.only_current_count,
        }

    if args.json:
        print(json.dumps(summary, indent=2))
    elif summary.get("checklist"):
        print("\nChecklist counts:", summary["checklist"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
