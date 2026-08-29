"""Sheet digitization persistence + page orchestrator (S-3 / D-1).

Hard rule: any fractional→feet conversion must use ``scale_for_geometry`` /
per-viewport ``scale_json`` — never sheet-global ``drawings.scale_json`` alone.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.sheet_association import associate_labels_to_symbols
from ai.pipelines.sheet_entity_graph import (
    DrawingViewport,
    SheetEntityGraph,
    SheetLabel,
    SheetLine,
    SheetSymbol,
    assign_viewport_id,
)
from ai.pipelines.symbol_detector import detect_symbols, resolve_symbol_detector_weights_path
from ai.pipelines.viewport_scale import load_viewports
from models.drawing_symbol import DrawingSymbol
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing

logger = logging.getLogger(__name__)

MAX_LABELS_PER_PAGE = 800
SHEET_ENTITY_GRAPH_KEY = "sheetEntityGraph"


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


def _bbox_tuple_from_json(bbox_json: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return (
        float(bbox_json["x0"]),
        float(bbox_json["y0"]),
        float(bbox_json["x1"]),
        float(bbox_json["y1"]),
    )


def _labels_from_text_elements(
    session: Session,
    drawing_id: int,
    page: int,
    viewports: tuple[DrawingViewport, ...],
) -> list[SheetLabel]:
    rows = (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.master_drawing_id == int(drawing_id),
            DrawingTextElement.page == int(page),
        )
        .order_by(DrawingTextElement.id.asc())
        .limit(MAX_LABELS_PER_PAGE)
        .all()
    )
    labels: list[SheetLabel] = []
    for row in rows:
        text = cast(str, row.text).strip()
        if not text:
            continue
        bbox = _bbox_tuple_from_json(cast(dict[str, Any], row.bbox_json))
        labels.append(
            SheetLabel(
                text=text,
                bbox_fractional=bbox,
                viewport_id=assign_viewport_id(bbox, viewports),
                confidence=float(cast(float, row.ocr_confidence) or 1.0),
            )
        )
    return labels


def _extract_lines(
    rendition_png: Path,
    viewports: tuple[DrawingViewport, ...],
) -> list[SheetLine]:
    from ai.pipelines.line_extractor import extract_line_polylines

    if not viewports:
        return extract_line_polylines(rendition_png)

    lines: list[SheetLine] = []
    for viewport in viewports:
        lines.extend(extract_line_polylines(rendition_png, viewport=viewport))
    return lines


def sheet_entity_graph_to_json(graph: SheetEntityGraph) -> dict[str, Any]:
    """JSON-serializable form for index_stats_json persistence."""
    return {
        "drawing_id": graph.drawing_id,
        "page": graph.page,
        "viewports": [asdict(vp) for vp in graph.viewports],
        "labels": [asdict(label) for label in graph.labels],
        "symbols": [asdict(symbol) for symbol in graph.symbols],
        "lines": [asdict(line) for line in graph.lines],
        "associations": list(graph.associations),
        "meta": dict(graph.meta),
    }


def persist_sheet_entity_graph(
    session: Session,
    drawing_id: int,
    graph: SheetEntityGraph,
) -> None:
    """Store graph under ``drawing.index_stats_json['sheetEntityGraph'][page]``.

    Drawing has no dedicated ``meta`` column; index_stats_json is the v1 sink.
    """
    drawing = session.get(Drawing, int(drawing_id))
    if drawing is None:
        raise ValueError(f"Drawing {drawing_id} not found")

    stats: dict[str, Any] = {}
    existing = cast(dict[str, Any] | None, drawing.index_stats_json)
    if isinstance(existing, dict):
        stats = dict(existing)

    by_page = stats.get(SHEET_ENTITY_GRAPH_KEY)
    graphs: dict[str, Any] = dict(by_page) if isinstance(by_page, dict) else {}
    graphs[str(graph.page)] = sheet_entity_graph_to_json(graph)
    stats[SHEET_ENTITY_GRAPH_KEY] = graphs
    drawing.index_stats_json = stats  # type: ignore[assignment]
    session.flush()


def digitize_drawing_page(
    session: Session,
    drawing_id: int,
    page: int = 1,
    *,
    rendition_png: Path,
    persist: bool = True,
    project_id: int | None = None,
) -> SheetEntityGraph:
    """Build a SheetEntityGraph for one drawing page.

    Steps: viewports → OCR labels → lines → symbols → associations.
    Feet conversion (if any caller needs it later) must use per-viewport scale
    helpers — this orchestrator does not apply ``drawings.scale_json``.
    """
    rendition_png = Path(rendition_png)
    if not rendition_png.exists():
        raise FileNotFoundError(f"rendition_png not found: {rendition_png}")

    viewports_list = load_viewports(session, int(drawing_id), page=int(page))
    viewports = tuple(viewports_list)
    meta: dict[str, Any] = {
        "viewport_warning": not bool(viewports),
        "rendition_png": str(rendition_png),
    }

    labels = _labels_from_text_elements(session, int(drawing_id), int(page), viewports)
    lines = _extract_lines(rendition_png, viewports)

    weights = resolve_symbol_detector_weights_path()
    symbols = detect_symbols(
        rendition_png,
        weights_path=weights,
        viewports=viewports,
    )
    # Re-assign viewport ids in case detector ran without crop context.
    symbols = [
        SheetSymbol(
            symbol_class=symbol.symbol_class,
            bbox_fractional=symbol.bbox_fractional,
            viewport_id=assign_viewport_id(symbol.bbox_fractional, viewports)
            if viewports
            else symbol.viewport_id,
            confidence=symbol.confidence,
            detector=symbol.detector,
        )
        for symbol in symbols
    ]

    drawing = session.get(Drawing, int(drawing_id))
    resolved_project_id = project_id
    if resolved_project_id is None and drawing is not None:
        resolved_project_id = cast(int | None, drawing.project_id)

    associations = associate_labels_to_symbols(
        labels,
        symbols,
        legend_session=session,
        project_id=resolved_project_id,
    )

    graph = SheetEntityGraph(
        drawing_id=int(drawing_id),
        page=int(page),
        viewports=viewports,
        labels=tuple(labels),
        symbols=tuple(symbols),
        lines=tuple(lines),
        associations=tuple(associations),
        meta=meta,
    )

    logger.info(
        "digitize_drawing_page drawing_id=%s page=%s viewports=%s labels=%s "
        "symbols=%s lines=%s associations=%s viewport_warning=%s",
        drawing_id,
        page,
        len(viewports),
        len(labels),
        len(symbols),
        len(lines),
        len(associations),
        meta["viewport_warning"],
    )

    if persist:
        persist_sheet_entity_graph(session, int(drawing_id), graph)
        if symbols:
            upsert_drawing_symbols(
                session,
                int(drawing_id),
                symbols,
                page=int(page),
                replace_detector="yolo",
            )

    return graph
