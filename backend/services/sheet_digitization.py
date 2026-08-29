"""Sheet digitization persistence helpers (symbols, later graph entities)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.sheet_entity_graph import SheetSymbol
from models.drawing_symbol import DrawingSymbol


def _bbox_json_from_symbol(symbol: SheetSymbol | Mapping[str, Any]) -> dict[str, float]:
    if isinstance(symbol, SheetSymbol):
        x0, y0, x1, y1 = symbol.bbox_fractional
        return {"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1)}
    bbox = symbol.get("bbox_json") or symbol.get("bbox_fractional")
    if isinstance(bbox, dict):
        return {
            "x0": float(bbox["x0"]),
            "y0": float(bbox["y0"]),
            "x1": float(bbox["x1"]),
            "y1": float(bbox["y1"]),
        }
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        x0, y0, x1, y1 = (float(v) for v in bbox)
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
    raise ValueError("symbol requires bbox_json or bbox_fractional")


def _symbol_fields(symbol: SheetSymbol | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(symbol, SheetSymbol):
        return {
            "symbol_class": symbol.symbol_class,
            "bbox_json": _bbox_json_from_symbol(symbol),
            "viewport_id": symbol.viewport_id,
            "confidence": float(symbol.confidence),
            "detector": symbol.detector,
            "meta_json": None,
        }
    return {
        "symbol_class": str(symbol["symbol_class"]),
        "bbox_json": _bbox_json_from_symbol(symbol),
        "viewport_id": cast(str | None, symbol.get("viewport_id")),
        "confidence": float(symbol.get("confidence", 1.0)),
        "detector": str(symbol.get("detector", "manual")),
        "meta_json": cast(dict[str, Any] | None, symbol.get("meta_json")),
    }


def upsert_drawing_symbols(
    session: Session,
    drawing_id: int,
    symbols: Sequence[SheetSymbol | Mapping[str, Any]],
    *,
    page: int = 1,
    replace_detector: str | None = None,
) -> int:
    """Insert symbols for a drawing page.

    When ``replace_detector`` is set, delete existing rows for that
    ``drawing_id`` + ``page`` + ``detector`` before insert (idempotent re-runs).
    """
    if replace_detector is not None:
        session.query(DrawingSymbol).filter(
            DrawingSymbol.drawing_id == int(drawing_id),
            DrawingSymbol.page == int(page),
            DrawingSymbol.detector == str(replace_detector),
        ).delete(synchronize_session=False)

    count = 0
    for symbol in symbols:
        fields = _symbol_fields(symbol)
        session.add(
            DrawingSymbol(
                drawing_id=int(drawing_id),
                page=int(page),
                **fields,
            )
        )
        count += 1

    session.flush()
    return count


def load_drawing_symbols(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
    detector: str | None = None,
) -> list[DrawingSymbol]:
    """Load persisted symbols for a drawing page."""
    query = session.query(DrawingSymbol).filter(
        DrawingSymbol.drawing_id == int(drawing_id),
        DrawingSymbol.page == int(page),
    )
    if detector is not None:
        query = query.filter(DrawingSymbol.detector == detector)
    return list(query.order_by(DrawingSymbol.id.asc()).all())
