"""Validation and persistence for contract-drawing markups."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.drawing_markup import DrawingMarkup
from services.inspection_vocabulary import (
    VocabCategory,
    canonicalize_vocab_term,
    canonical_terms,
)

INSPECTION_STATUSES = canonical_terms(VocabCategory.INSPECTION_STATUS)
INSPECTION_TYPES = canonical_terms(VocabCategory.INSPECTION_TYPE)

KINDS = ("polyline", "cloud", "arrow", "rect", "text")
MAX_POINTS = 5000
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
_MIN_POINTS = {"polyline": 2, "cloud": 3}
_EXACT_POINTS = {"arrow": 2, "rect": 2, "text": 1}
_FIELD_CATEGORY = {
    "inspection_type": VocabCategory.INSPECTION_TYPE,
    "status": VocabCategory.INSPECTION_STATUS,
}


class MarkupError(ValueError):
    """Raised for input that must be rejected. The route turns it into a 422."""


def _canon(value: str | None, field: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    hit = canonicalize_vocab_term(str(value), _FIELD_CATEGORY[field])
    if hit is None:
        raise MarkupError(f"{field} {value!r} is not in the controlled vocabulary")
    return hit


def clean_points(kind: str, points: Any) -> list[list[float]]:
    if kind not in KINDS:
        raise MarkupError(f"kind must be one of {', '.join(KINDS)}")
    if not isinstance(points, (list, tuple)):
        raise MarkupError("points must be a list of [x, y]")
    if len(points) > MAX_POINTS:
        raise MarkupError(f"at most {MAX_POINTS} points")
    out: list[list[float]] = []
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise MarkupError("each point must be [x, y]")
        try:
            x, y = float(pt[0]), float(pt[1])
        except (TypeError, ValueError) as exc:
            raise MarkupError("point coordinates must be numbers") from exc
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise MarkupError("points are display fractions and must lie in [0, 1]; check the frame")
        out.append([x, y])
    if kind in _EXACT_POINTS and len(out) != _EXACT_POINTS[kind]:
        raise MarkupError(f"{kind} needs exactly {_EXACT_POINTS[kind]} point(s)")
    if kind in _MIN_POINTS and len(out) < _MIN_POINTS[kind]:
        raise MarkupError(f"{kind} needs at least {_MIN_POINTS[kind]} points")
    return out


def validate(
    *, kind: str, points: Any, label: str | None, inspection_type: str | None, status: str | None, color: str | None
) -> dict[str, Any]:
    pts = clean_points(kind, points)
    text = (label or "").strip() or None
    if kind == "text" and not text:
        raise MarkupError("a text markup needs a label")
    if color is not None and not COLOR_RE.match(color):
        raise MarkupError("color must be #RRGGBB or #RRGGBBAA")
    return {
        "kind": kind,
        "points_json": pts,
        "label": text,
        "inspection_type": _canon(inspection_type, "inspection_type"),
        "status": _canon(status, "status"),
        "color": color,
    }


def create_markup(
    db: Session, *, drawing_id: int, page: int, created_by: str, kind: str, points: Any,
    label: str | None = None, inspection_type: str | None = None, status: str | None = None, color: str | None = None,
) -> DrawingMarkup:
    if page < 1:
        raise MarkupError("page starts at 1")
    fields = validate(kind=kind, points=points, label=label, inspection_type=inspection_type, status=status, color=color)
    row = DrawingMarkup(drawing_id=drawing_id, page=page, created_by=(created_by or "unknown")[:120], **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_markup(db: Session, markup_id: int) -> DrawingMarkup | None:
    row = db.get(DrawingMarkup, markup_id)
    return None if row is None or row.deleted_at is not None else row


def list_markups(
    db: Session, drawing_id: int, *, page: int | None = None, inspection_type: str | None = None, status: str | None = None
) -> list[DrawingMarkup]:
    query = db.query(DrawingMarkup).filter(DrawingMarkup.drawing_id == drawing_id, DrawingMarkup.deleted_at.is_(None))
    if page is not None:
        query = query.filter(DrawingMarkup.page == page)
    if inspection_type:
        query = query.filter(DrawingMarkup.inspection_type == _canon(inspection_type, "inspection_type"))
    if status:
        query = query.filter(DrawingMarkup.status == _canon(status, "status"))
    return query.order_by(DrawingMarkup.id).all()


def update_markup(db: Session, row: DrawingMarkup, changes: dict[str, Any]) -> DrawingMarkup:
    allowed = {"points", "label", "inspection_type", "status", "color"}
    unknown = set(changes) - allowed
    if unknown:
        raise MarkupError(f"cannot change {', '.join(sorted(unknown))}")
    merged = {
        "kind": row.kind,
        "points": changes.get("points", row.points_json),
        "label": changes.get("label", row.label),
        "inspection_type": changes.get("inspection_type", row.inspection_type),
        "status": changes.get("status", row.status),
        "color": changes.get("color", row.color),
    }
    fields = validate(**merged)
    for key, value in fields.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_markup(db: Session, row: DrawingMarkup) -> None:
    row.deleted_at = datetime.now(timezone.utc)
    db.commit()


def summary(db: Session, drawing_id: int, page: int | None = None) -> list[dict[str, Any]]:
    query = db.query(DrawingMarkup.inspection_type, DrawingMarkup.status, func.count(DrawingMarkup.id)).filter(
        DrawingMarkup.drawing_id == drawing_id, DrawingMarkup.deleted_at.is_(None)
    )
    if page is not None:
        query = query.filter(DrawingMarkup.page == page)
    rows = query.group_by(DrawingMarkup.inspection_type, DrawingMarkup.status).all()
    return sorted(
        ({"inspection_type": t, "status": s, "count": int(c)} for t, s, c in rows),
        key=lambda r: (r["inspection_type"] or "", r["status"] or ""),
    )
