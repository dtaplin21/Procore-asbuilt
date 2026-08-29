#!/usr/bin/env python3
"""Seed manual drawing_viewports for multi-scale sheets (digitization V-3).

Hard-coded (editable) viewports for UCSF aux C4.20 (drawing 1501): plan + profile
with distinct bboxes and scales from the sheet (not the legacy sheet-global
``drawings.scale_json`` OCR miss).

Usage (from ``backend/``)::

    ./venv/bin/python scripts/seed_drawing_viewports.py --dry-run
    ./venv/bin/python scripts/seed_drawing_viewports.py --drawing-id 1501

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

from database import SessionLocal  # noqa: E402
from models.drawing_viewport import DrawingViewport  # noqa: E402
from models.models import Drawing  # noqa: E402

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


def _validate_viewports(viewports: tuple[dict[str, Any], ...]) -> None:
    by_kind = {str(v["kind"]): v for v in viewports}
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
    scale = vp["scale_json"]
    print(
        f"  [{action}] viewport_id={vp['viewport_id']!r} kind={vp['kind']!r} "
        f"bbox=({bbox['x0']:.4f},{bbox['y0']:.4f},{bbox['x1']:.4f},{bbox['y1']:.4f}) "
        f"scale={scale.get('raw_text')!r} "
        f"rfppi={scale.get('real_feet_per_paper_inch')}"
    )


def upsert_viewports(
    session: Session,
    *,
    drawing_id: int,
    viewports: tuple[dict[str, Any], ...] = _UCSF_C420_VIEWPORTS,
    dry_run: bool = False,
) -> int:
    """Upsert viewports by (drawing_id, page, viewport_id). Returns row count."""
    _validate_viewports(viewports)

    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        raise SystemExit(f"Drawing {drawing_id} not found")

    print(f"Drawing {drawing_id}: {drawing.name!r} (page={PAGE})")
    written = 0
    for spec in viewports:
        viewport_id = str(spec["viewport_id"])
        existing = (
            session.query(DrawingViewport)
            .filter_by(drawing_id=drawing_id, page=PAGE, viewport_id=viewport_id)
            .one_or_none()
        )
        payload = {
            "kind": str(spec["kind"]),
            "bbox_json": dict(spec["bbox_json"]),
            "scale_json": dict(spec["scale_json"]),
            "source": SOURCE,
            "notes": str(spec.get("notes") or "") or None,
        }
        if existing is None:
            _print_viewport({**spec, **payload}, action="INSERT" if not dry_run else "DRY-INSERT")
            if not dry_run:
                session.add(
                    DrawingViewport(
                        drawing_id=drawing_id,
                        page=PAGE,
                        viewport_id=viewport_id,
                        **payload,
                    )
                )
        else:
            _print_viewport({**spec, **payload}, action="UPDATE" if not dry_run else "DRY-UPDATE")
            if not dry_run:
                for key, value in payload.items():
                    setattr(existing, key, value)
        written += 1

    if dry_run:
        session.rollback()
        print(f"Dry-run only — would upsert {written} viewport(s).")
    else:
        session.commit()
        print(f"Upserted {written} viewport(s).")
    return written


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
        help="Print planned upserts without writing",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
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
