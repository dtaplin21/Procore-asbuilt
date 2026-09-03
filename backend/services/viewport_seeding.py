"""Auto-seed drawing_viewports after OCR index (digitization V-5 wire-in)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.viewport_detector import (
    proposal_to_seed_dict,
    propose_viewports_from_ocr,
)
from models.drawing_text_element import DrawingTextElement
from models.drawing_viewport import DrawingViewport
from models.models import Drawing

logger = logging.getLogger(__name__)

_MANUAL_SOURCE = "manual"
_OCR_SOURCE = "ocr"
_LAYOUT_SOURCE = "layout_fallback"

_PLAN_PROFILE_SIGNAL_RE = re.compile(
    r"\b(PLAN|PROFILE|SCALES)\b",
    re.IGNORECASE,
)

# Default plan+profile split for sewer install sheets (C4.20-style).
_LAYOUT_PLAN_PROFILE: dict[str, tuple[float, float, float, float]] = {
    "plan": (0.03, 0.03, 0.82, 0.45),
    "profile": (0.03, 0.45, 0.82, 0.94),
}


@dataclass(frozen=True)
class ViewportSeedResult:
    drawing_id: int
    page: int
    written: int
    source: str  # skipped_manual | ocr | layout_fallback | none
    viewport_ids: tuple[str, ...]


def _bbox_tuple(bbox: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        float(bbox["x0"]),
        float(bbox["y0"]),
        float(bbox["x1"]),
        float(bbox["y1"]),
    )


def has_manual_viewports(session: Session, drawing_id: int, *, page: int = 1) -> bool:
    return (
        session.query(DrawingViewport)
        .filter(
            DrawingViewport.drawing_id == int(drawing_id),
            DrawingViewport.page == int(page),
            DrawingViewport.source == _MANUAL_SOURCE,
        )
        .count()
        > 0
    )


def clear_ocr_viewports(session: Session, drawing_id: int, *, page: int = 1) -> int:
    """Remove prior auto-seeded viewports before re-index refresh."""
    rows = (
        session.query(DrawingViewport)
        .filter(
            DrawingViewport.drawing_id == int(drawing_id),
            DrawingViewport.page == int(page),
            DrawingViewport.source.in_([_OCR_SOURCE, _LAYOUT_SOURCE]),
        )
        .all()
    )
    for row in rows:
        session.delete(row)
    return len(rows)


def upsert_drawing_viewports(
    session: Session,
    *,
    drawing_id: int,
    viewports: Sequence[dict[str, Any]],
    page: int = 1,
    default_source: str = _OCR_SOURCE,
    require_plan_and_other: bool = False,
) -> int:
    """Upsert viewports by (drawing_id, page, viewport_id). Returns row count."""
    if require_plan_and_other:
        by_kind = {str(v["kind"]): v for v in viewports}
        plan = by_kind.get("plan")
        other = by_kind.get("section") or by_kind.get("profile")
        if plan is None or other is None:
            raise ValueError(
                "viewports must include kind=plan and kind=section|profile"
            )
        if _bbox_tuple(plan["bbox_json"]) == _bbox_tuple(other["bbox_json"]):
            raise ValueError("plan and section/profile bboxes must differ")

    seen: dict[tuple[float, float, float, float], str] = {}
    for vp in viewports:
        key = _bbox_tuple(vp["bbox_json"])
        vid = str(vp["viewport_id"])
        if key in seen:
            raise ValueError(
                f"viewports {seen[key]!r} and {vid!r} share the same bbox"
            )
        seen[key] = vid

    written = 0
    for spec in viewports:
        viewport_id = str(spec["viewport_id"])
        existing = (
            session.query(DrawingViewport)
            .filter_by(drawing_id=int(drawing_id), page=int(page), viewport_id=viewport_id)
            .one_or_none()
        )
        if existing is not None and cast(str, existing.source) == _MANUAL_SOURCE:
            continue

        scale_json = spec.get("scale_json")
        if isinstance(scale_json, dict) and float(
            scale_json.get("real_feet_per_paper_inch") or 0
        ) <= 0:
            scale_json = None

        payload = {
            "kind": str(spec["kind"]),
            "bbox_json": dict(spec["bbox_json"]),
            "scale_json": dict(scale_json) if isinstance(scale_json, dict) else None,
            "source": str(spec.get("source") or default_source),
            "notes": str(spec.get("notes") or "") or None,
        }
        if existing is None:
            session.add(
                DrawingViewport(
                    drawing_id=int(drawing_id),
                    page=int(page),
                    viewport_id=viewport_id,
                    **payload,
                )
            )
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
        written += 1
    return written


def _indexed_pages(session: Session, drawing_id: int) -> list[int]:
    rows = (
        session.query(DrawingTextElement.page)
        .filter(DrawingTextElement.master_drawing_id == int(drawing_id))
        .distinct()
        .all()
    )
    pages = sorted({int(cast(int, row[0])) for row in rows})
    return pages or [1]


def _sheet_has_plan_profile_signals(session: Session, drawing_id: int, *, page: int) -> bool:
    for row in (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.master_drawing_id == int(drawing_id),
            DrawingTextElement.page == int(page),
        )
        .all()
    ):
        if _PLAN_PROFILE_SIGNAL_RE.search(str(row.text or "")):
            return True
    return False


def _scale_json_from_drawing(drawing: Drawing) -> dict[str, Any] | None:
    raw = drawing.scale_json
    if not isinstance(raw, dict):
        return None
    rfppi = float(raw.get("real_feet_per_paper_inch") or 0)
    if rfppi <= 0:
        return None
    return dict(raw)


def _layout_fallback_rows(
    drawing: Drawing,
    *,
    page: int,
) -> tuple[dict[str, Any], ...]:
    scale = _scale_json_from_drawing(drawing)
    plan_scale = scale
    profile_scale = scale
    if scale is not None:
        horiz = scale.get("horizontal")
        vert = scale.get("vertical")
        if isinstance(horiz, dict) and isinstance(vert, dict):
            try:
                h_den = float(horiz.get("denominator") or 0)
                v_den = float(vert.get("denominator") or 0)
                if h_den > 0 and v_den > 0 and abs(h_den - v_den) > 1e-6:
                    profile_scale = dict(scale)
            except (TypeError, ValueError):
                pass

    def _row(viewport_id: str, kind: str, bbox: tuple[float, float, float, float], scale_json: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "viewport_id": viewport_id,
            "kind": kind,
            "bbox_json": {
                "x0": bbox[0],
                "y0": bbox[1],
                "x1": bbox[2],
                "y1": bbox[3],
            },
            "scale_json": scale_json
            or {
                "raw_text": "",
                "real_feet_per_paper_inch": 0.0,
                "confidence": 0.0,
                "page": page,
            },
            "source": _LAYOUT_SOURCE,
            "notes": "Layout fallback plan+profile split after OCR index",
        }

    return (
        _row("plan", "plan", _LAYOUT_PLAN_PROFILE["plan"], plan_scale),
        _row("profile", "profile", _LAYOUT_PLAN_PROFILE["profile"], profile_scale),
    )


def seed_viewports_for_page(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
) -> ViewportSeedResult:
    """Propose and upsert viewports for one indexed page."""
    if has_manual_viewports(session, drawing_id, page=page):
        return ViewportSeedResult(
            drawing_id=int(drawing_id),
            page=int(page),
            written=0,
            source="skipped_manual",
            viewport_ids=(),
        )

    clear_ocr_viewports(session, drawing_id, page=page)

    proposals = propose_viewports_from_ocr(session, drawing_id, page=page)
    seed_source = _OCR_SOURCE

    if not proposals:
        drawing = session.get(Drawing, drawing_id)
        # Multi-page linked attachments (e.g. 78-page UMR): layout fallback only on
        # page 1 or pages with explicit PLAN/PROFILE OCR — not every sheet.
        use_layout = drawing is not None and (
            _sheet_has_plan_profile_signals(session, drawing_id, page=page)
            or (
                cast(str | None, drawing.source) == "linked_evidence"
                and int(page) == 1
            )
        )
        if use_layout and drawing is not None:
            seed_rows = _layout_fallback_rows(drawing, page=page)
            seed_source = _LAYOUT_SOURCE
        else:
            session.flush()
            return ViewportSeedResult(
                drawing_id=int(drawing_id),
                page=int(page),
                written=0,
                source="none",
                viewport_ids=(),
            )
    else:
        seed_rows = tuple(proposal_to_seed_dict(p) for p in proposals)

    written = upsert_drawing_viewports(
        session,
        drawing_id=drawing_id,
        viewports=seed_rows,
        page=page,
        default_source=seed_source,
        require_plan_and_other=False,
    )
    session.flush()
    return ViewportSeedResult(
        drawing_id=int(drawing_id),
        page=int(page),
        written=written,
        source=seed_source,
        viewport_ids=tuple(str(r["viewport_id"]) for r in seed_rows),
    )


def maybe_seed_viewports_after_index(session: Session, drawing_id: int) -> None:
    """After OCR index, auto-seed viewports from OCR or layout fallback.

    Non-blocking for the index job — failures are logged, never raised.
    Skips drawings that already have manual (``source=manual``) viewports.

    Commits after each page that writes rows so a later digitization failure
    (which must not roll back the session) cannot discard viewport flushes.
    """
    try:
        pages = _indexed_pages(session, drawing_id)
        results: list[ViewportSeedResult] = []
        for page in pages:
            result = seed_viewports_for_page(session, drawing_id, page=page)
            results.append(result)
            if result.written > 0:
                session.commit()

        for result in results:
            if result.written <= 0 and result.source != "skipped_manual":
                continue
            logger.info(
                "viewport_auto_seed",
                extra={
                    "drawing_id": drawing_id,
                    "page": result.page,
                    "written": result.written,
                    "source": result.source,
                    "viewport_ids": list(result.viewport_ids),
                },
            )
    except Exception:
        logger.exception(
            "viewport_auto_seed_failed",
            extra={"drawing_id": drawing_id},
        )
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
