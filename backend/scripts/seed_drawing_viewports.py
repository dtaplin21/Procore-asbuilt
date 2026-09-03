#!/usr/bin/env python3
"""Seed manual drawing_viewports for multi-scale sheets (digitization V-3 / V-5).

Hard-coded (editable) viewports for UCSF aux C4.20 (drawing 1501): plan + profile
with distinct bboxes and scales from the sheet (not the legacy sheet-global
``drawings.scale_json`` OCR miss).

Usage (from ``backend/``)::

    ./venv/bin/python scripts/seed_drawing_viewports.py --dry-run
    ./venv/bin/python scripts/seed_drawing_viewports.py --drawing-id 1501

    # OCR proposals (V-5): print only unless --apply
    ./venv/bin/python scripts/seed_drawing_viewports.py --from-ocr --drawing-id 1501
    ./venv/bin/python scripts/seed_drawing_viewports.py --from-ocr --drawing-id 1501 --apply

Refine bboxes with ``scripts/pick_fractional_point.py`` + the exported PNG under
``tests/fixtures/digitization/aux_c420_page1.png``.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, cast

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from ai.pipelines.viewport_detector import (  # noqa: E402
    proposal_to_seed_dict,
    propose_viewports_from_ocr,
)
from database import SessionLocal  # noqa: E402
from models.drawing_viewport import DrawingViewport  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.viewport_seeding import upsert_drawing_viewports  # noqa: E402

DEFAULT_DRAWING_ID = 1501  # aux C4.20 (see seed_master_registration_controls.AUX_ID)
PAGE = 1
SOURCE = "manual"


def _scale(
    *,
    raw_text: str,
    real_feet_per_paper_inch: float,
    confidence: float,
    horizontal_ft: float | None = None,
    vertical_ft: float | None = None,
) -> dict[str, Any]:
    """Build scale_json in drawing_scale_parser shape (paper inch = 1)."""
    h_ft = float(horizontal_ft if horizontal_ft is not None else real_feet_per_paper_inch)
    v_ft = float(vertical_ft if vertical_ft is not None else h_ft)
    paper_in = 1.0

    def _component(real_ft: float) -> dict[str, float | str]:
        return {
            "numerator": paper_in,
            "denominator": real_ft,
            "units": "in=ft",
        }

    return {
        "raw_text": raw_text,
        "paper_inches_per_real_foot": paper_in / float(real_feet_per_paper_inch),
        "real_feet_per_paper_inch": float(real_feet_per_paper_inch),
        "horizontal": _component(h_ft),
        "vertical": _component(v_ft),
        "confidence": confidence,
        "page": PAGE,
    }


# Editable seed for U1.C4.20 sewer plan & profile (drawing 1501).
# Bboxes from 150 DPI page raster + OCR (elev 98 tops profile ~y=0.465;
# titleblock / sheet chrome to the right of ~x=0.82; bottom SCALES strip ~y>0.94).
# Sheet note: SCALES: 1"=10' HORIZONTAL, 1"=1' VERTICAL (OCR vertical was noisy).
_UCSF_C420_VIEWPORTS: tuple[dict[str, Any], ...] = (
    {
        "viewport_id": "plan",
        "kind": "plan",
        "bbox_json": {"x0": 0.03, "y0": 0.03, "x1": 0.82, "y1": 0.45},
        "scale_json": _scale(
            raw_text='1"=10\'',
            real_feet_per_paper_inch=10.0,
            confidence=0.9,
        ),
        "notes": (
            "Main plan view (exclude profile below ~y=0.45 and right titleblock). "
            "H scale matches sheet SCALES note; refine with pick_fractional_point."
        ),
    },
    {
        "viewport_id": "profile",
        "kind": "profile",
        "bbox_json": {"x0": 0.03, "y0": 0.45, "x1": 0.82, "y1": 0.94},
        "scale_json": _scale(
            raw_text='1"=10\' HORIZONTAL, 1"=1\' VERTICAL',
            real_feet_per_paper_inch=10.0,
            confidence=0.85,
            horizontal_ft=10.0,
            vertical_ft=1.0,
        ),
        "notes": (
            "Sewer profile strip (C4.20 is plan+profile, not a cut section). "
            "Primary rfppi is horizontal; use vertical component for elev feet."
        ),
    },
)


def _bbox_tuple(bbox: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        float(bbox["x0"]),
        float(bbox["y0"]),
        float(bbox["x1"]),
        float(bbox["y1"]),
    )


def _validate_viewports(
    viewports: tuple[dict[str, Any], ...],
    *,
    require_plan_and_other: bool = True,
) -> None:
    by_kind = {str(v["kind"]): v for v in viewports}
    if require_plan_and_other:
        plan = by_kind.get("plan")
        other = by_kind.get("section") or by_kind.get("profile")
        if plan is None or other is None:
            raise SystemExit(
                "Seed must include kind=plan and kind=section|profile with distinct bboxes."
            )
        if _bbox_tuple(plan["bbox_json"]) == _bbox_tuple(other["bbox_json"]):
            raise SystemExit(
                "Refuse to seed: plan and section/profile bboxes are identical. "
                "Edit _UCSF_C420_VIEWPORTS."
            )
    # Also reject any duplicate bboxes across the full seed list.
    seen: dict[tuple[float, float, float, float], str] = {}
    for vp in viewports:
        key = _bbox_tuple(vp["bbox_json"])
        vid = str(vp["viewport_id"])
        if key in seen:
            raise SystemExit(
                f"Refuse to seed: viewports {seen[key]!r} and {vid!r} share the same bbox."
            )
        seen[key] = vid


def _print_viewport(vp: dict[str, Any], *, action: str) -> None:
    bbox = vp["bbox_json"]
    scale = vp.get("scale_json") or {}
    print(
        f"  [{action}] viewport_id={vp['viewport_id']!r} kind={vp['kind']!r} "
        f"bbox=({bbox['x0']:.4f},{bbox['y0']:.4f},{bbox['x1']:.4f},{bbox['y1']:.4f}) "
        f"scale={scale.get('raw_text')!r} "
        f"rfppi={scale.get('real_feet_per_paper_inch')} "
        f"source={vp.get('source', SOURCE)!r}"
    )


def upsert_viewports(
    session: Session,
    *,
    drawing_id: int,
    viewports: tuple[dict[str, Any], ...] = _UCSF_C420_VIEWPORTS,
    dry_run: bool = False,
    require_plan_and_other: bool = True,
    default_source: str = SOURCE,
) -> int:
    """Upsert viewports by (drawing_id, page, viewport_id). Returns row count."""
    _validate_viewports(viewports, require_plan_and_other=require_plan_and_other)

    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        raise SystemExit(f"Drawing {drawing_id} not found")

    print(f"Drawing {drawing_id}: {drawing.name!r} (page={PAGE})")
    for spec in viewports:
        _print_viewport({**spec, "source": spec.get("source") or default_source}, action="PLAN")

    if dry_run:
        print(f"Dry-run only — would upsert {len(viewports)} viewport(s).")
        return len(viewports)

    written = upsert_drawing_viewports(
        session,
        drawing_id=drawing_id,
        viewports=viewports,
        page=PAGE,
        default_source=default_source,
        require_plan_and_other=require_plan_and_other,
    )
    session.commit()
    print(f"Upserted {written} viewport(s).")
    return written


def _run_from_ocr(
    session: Session,
    *,
    drawing_id: int,
    apply: bool,
) -> int:
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        raise SystemExit(f"Drawing {drawing_id} not found")

    proposals = propose_viewports_from_ocr(session, drawing_id, page=PAGE)
    print(
        f"Drawing {drawing_id}: {drawing.name!r} — OCR proposals "
        f"({len(proposals)}; write={'yes' if apply else 'no, pass --apply'})"
    )
    if not proposals:
        print("  (no proposals)")
        return 0

    seed_rows = tuple(proposal_to_seed_dict(p) for p in proposals)
    for row in seed_rows:
        _print_viewport(row, action="OCR" if not apply else "OCR-APPLY")

    plan_count = sum(1 for p in proposals if p.kind == "plan")
    section_count = sum(1 for p in proposals if p.kind == "section")
    print(f"  summary: plan={plan_count} section={section_count} total={len(proposals)}")

    if not apply:
        return len(proposals)

    return upsert_viewports(
        session,
        drawing_id=drawing_id,
        viewports=seed_rows,
        dry_run=False,
        require_plan_and_other=False,
        default_source="ocr",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drawing-id",
        type=int,
        default=DEFAULT_DRAWING_ID,
        help=f"Target drawing id (default {DEFAULT_DRAWING_ID} = C4.20 aux)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned manual upserts without writing",
    )
    parser.add_argument(
        "--from-ocr",
        action="store_true",
        help="Propose viewports from OCR (prints only unless --apply)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="With --from-ocr, write filtered proposals to drawing_viewports",
    )
    args = parser.parse_args()

    if args.apply and not args.from_ocr:
        raise SystemExit("--apply requires --from-ocr")

    db = SessionLocal()
    try:
        if args.from_ocr:
            _run_from_ocr(
                db,
                drawing_id=cast(int, args.drawing_id),
                apply=bool(args.apply),
            )
        else:
            upsert_viewports(
                db,
                drawing_id=cast(int, args.drawing_id),
                dry_run=bool(args.dry_run),
            )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
