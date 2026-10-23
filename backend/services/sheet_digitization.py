"""Sheet digitization persistence + page orchestrator (S-3 / D-1).

Hard rule: any fractional→feet conversion must use ``scale_for_geometry`` /
per-viewport ``scale_json`` — never sheet-global ``drawings.scale_json`` alone.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.legend_line_swatch import LegendLineTemplate
from ai.pipelines.sheet_association import associate_labels_to_symbols
from ai.pipelines.sheet_entity_graph import (
    DrawingViewport,
    LineTypingStatus,
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
MIN_VECTOR_CHAINS_BEFORE_RASTER_FALLBACK = 50
# Past this, line geometry is a file. index_stats_json is returned on every
# index-status poll, and 1722 is on the order of 80k chains.
INLINE_LINE_LIMIT = 2000
LINE_STORAGE_KEY = "line_storage_key"
LINE_COUNT_KEY = "line_count"


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


def _text_elements_for_page(
    session: Session,
    drawing_id: int,
    page: int,
) -> list[DrawingTextElement]:
    return (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.master_drawing_id == int(drawing_id),
            DrawingTextElement.page == int(page),
        )
        .order_by(DrawingTextElement.id.asc())
        .limit(MAX_LABELS_PER_PAGE)
        .all()
    )


def _resolve_source_pdf(
    session: Session,
    drawing_id: int,
    source_pdf: Path | None,
) -> Path | None:
    if source_pdf is not None:
        path = Path(source_pdf)
        return path if path.is_file() else None
    drawing = session.get(Drawing, int(drawing_id))
    if drawing is None:
        return None
    storage_key = cast(str | None, drawing.storage_key)
    if not storage_key or not str(storage_key).strip():
        return None
    from services.file_storage import resolve_stored_file_path

    resolved = resolve_stored_file_path(storage_key)
    if resolved is None or not resolved.is_file():
        return None
    return resolved


def _legend_templates_for_page(
    session: Session,
    *,
    pdf_path: Path | None,
    drawing_id: int,
    page: int,
    project_id: int | None,
    line_meta: dict[str, Any],
) -> tuple[LegendLineTemplate, ...]:
    if pdf_path is None or not pdf_path.is_file():
        return ()
    from ai.pipelines.legend_line_swatch import (
        build_legend_line_templates_with_diagnostics,
        legend_line_templates_to_meta,
    )
    from services.legend_index_helpers import (
        cluster_legend_rows_for_drawing,
        legend_rows_to_audit_meta,
    )

    rows = cluster_legend_rows_for_drawing(session, drawing_id, page=page)
    line_meta["legend_line_row_count"] = len(rows)
    if rows:
        line_meta["legend_line_rows"] = legend_rows_to_audit_meta(rows)
    templates, template_diag = build_legend_line_templates_with_diagnostics(
        session,
        pdf_path,
        rows,
        project_id=project_id,
        page=page,
    )
    line_meta["legend_template_diagnostics"] = template_diag
    if templates:
        line_meta["legend_line_templates"] = legend_line_templates_to_meta(templates)
    return tuple(templates)


def _extract_lines_raster(
    rendition_png: Path,
    viewports: tuple[DrawingViewport, ...],
    *,
    dash_templates: tuple[LegendLineTemplate, ...] = (),
) -> list[SheetLine]:
    from ai.pipelines.line_extractor import extract_line_polylines

    kwargs: dict[str, Any] = {"classify_dash": True}
    if dash_templates:
        kwargs["dash_templates"] = dash_templates
    if not viewports:
        return extract_line_polylines(rendition_png, **kwargs)
    lines: list[SheetLine] = []
    for viewport in viewports:
        lines.extend(extract_line_polylines(rendition_png, viewport=viewport, **kwargs))
    return lines


def _extract_lines(
    *,
    pdf_path: Path | None,
    rendition_png: Path,
    viewports: tuple[DrawingViewport, ...],
    page: int,
    session: Session,
    drawing_id: int,
    project_id: int | None,
    line_meta: dict[str, Any],
) -> list[SheetLine]:
    from collections import Counter

    from ai.pipelines.legend_line_typing import select_chains_for_storage
    from ai.pipelines.legend_line_swatch import classify_chain_typings
    from ai.pipelines.pdf_line_source_gate import PdfLineSource, classify_pdf_line_source
    from ai.pipelines.pdf_vector_line_extractor import (
        chains_to_sheet_lines,
        extract_pdf_vector_chains,
    )

    dash_templates = _legend_templates_for_page(
        session,
        pdf_path=pdf_path,
        drawing_id=drawing_id,
        page=page,
        project_id=project_id,
        line_meta=line_meta,
    )

    if pdf_path is not None and pdf_path.is_file():
        source, line_stats = classify_pdf_line_source(pdf_path, page=page)
        line_meta["pdf_line_source"] = source.value
        line_meta["pdf_line_source_stats"] = {
            "path_count": line_stats.path_count,
            "line_op_count": line_stats.line_op_count,
            "stroked_path_count": line_stats.stroked_path_count,
        }
        if source is PdfLineSource.VECTOR:
            chains = extract_pdf_vector_chains(pdf_path, page=page, max_chains=None)
            if len(chains) >= MIN_VECTOR_CHAINS_BEFORE_RASTER_FALLBACK:
                typings = classify_chain_typings(chains, list(dash_templates))
                plan_bbox: tuple[float, float, float, float] | None = None
                for vp in viewports:
                    if vp.kind == "plan":
                        plan_bbox = vp.bbox_fractional
                        break
                if dash_templates:
                    from ai.pipelines.label_seeded_stitching import (
                        enrich_ambiguous_chain_typings,
                        labels_from_bboxes,
                        segments_from_pdf_vector_segments,
                        style_filter_for_swatch,
                    )
                    from ai.pipelines.pdf_vector_line_extractor import extract_pdf_vector_segments

                    page_labels = _labels_from_text_elements(
                        session, drawing_id, page, viewports
                    )
                    text_boxes = labels_from_bboxes(
                        (lb.text, lb.bbox_fractional) for lb in page_labels
                    )
                    pdf_segments = extract_pdf_vector_segments(pdf_path, page=page)
                    seg_list = segments_from_pdf_vector_segments(pdf_segments)
                    code_to_template: dict[
                        str, tuple[int, str, Any]
                    ] = {}
                    for tpl in dash_templates:
                        code = (tpl.abbreviation_code or "").strip().upper()
                        if not code or code in code_to_template:
                            continue
                        code_to_template[code] = (
                            tpl.legend_line_type_id,
                            tpl.line_type_name,
                            style_filter_for_swatch(
                                stroke_width_bucket=tpl.style.stroke_width_bucket,
                                color=tpl.style.color,
                            ),
                        )
                    typings, trace_stats = enrich_ambiguous_chain_typings(
                        chains,
                        typings,
                        seg_list,
                        text_boxes,
                        code_to_template=code_to_template,
                        plan_bbox=plan_bbox,
                    )
                    line_meta["label_seeded_trace"] = trace_stats
                line_meta["chain_typing_counts"] = dict(Counter(t.status for t in typings))
                wanted_type_ids = tuple(tpl.legend_line_type_id for tpl in dash_templates)
                # Keep every chain, including hairlines. A 2000 cap dropped more than
                # half the stroked items on Master.pdf and the audit counted them missing.
                keep_indices, tier_counts = select_chains_for_storage(
                    chains,
                    typings,
                    plan_bbox=plan_bbox,
                    wanted_type_ids=wanted_type_ids,
                    max_chains=len(chains),
                )
                line_meta["chain_storage_tiers"] = tier_counts
                dropped = int(tier_counts.get("dropped") or 0)
                line_meta["capture_check"] = {
                    "outcome": "FAILED" if dropped else "OK",
                    "reason": "CHAIN_CAP" if dropped else "KEPT",
                    "kept": int(tier_counts.get("selected") or 0),
                    "dropped": dropped,
                    "wanted_dropped": int(tier_counts.get("wanted_dropped") or 0),
                }
                lines: list[SheetLine] = []
                for idx in keep_indices:
                    chain = chains[idx]
                    ty = typings[idx]
                    type_name = ty.line_type_name if ty.status == "typed" else None
                    type_id = ty.legend_line_type_id if ty.status == "typed" else None
                    lines.extend(
                        chains_to_sheet_lines(
                            [chain],
                            viewports,
                            line_type=type_name,
                            legend_line_type_id=type_id,
                            line_typing_status=cast(LineTypingStatus, ty.status),
                            candidate_legend_line_type_ids=ty.candidate_type_ids,
                        )
                    )
                return lines
            line_meta["pdf_line_source"] = "raster_fallback"

    line_meta.setdefault("pdf_line_source", "raster")
    return _extract_lines_raster(
        rendition_png,
        viewports,
        dash_templates=dash_templates,
    )


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


def sheet_line_storage_key(project_id: int, drawing_id: int, page: int) -> str:
    return (
        f"drawings/sheet-graph/project-{int(project_id)}"
        f"/drawing-{int(drawing_id)}/page-{int(page)}-lines.json"
    )


def partition_sheet_lines(
    payload: dict[str, Any],
    *,
    project_id: int,
    drawing_id: int,
) -> tuple[dict[str, Any], tuple[str, bytes] | None]:
    """Keep small line lists on the drawing row. Write larger ones to a file.

    Returns the payload to store in ``index_stats_json`` and, when the lines
    do not fit inline, ``(storage_key, file_bytes)``.
    """
    lines = payload.get("lines") if isinstance(payload.get("lines"), list) else []
    out = dict(payload)
    out[LINE_COUNT_KEY] = len(lines)
    if len(lines) <= INLINE_LINE_LIMIT:
        out.pop(LINE_STORAGE_KEY, None)
        return out, None
    page = int(payload.get("page") or 1)
    key = sheet_line_storage_key(project_id, drawing_id, page)
    body = json.dumps({"lines": lines}, separators=(",", ":")).encode("utf-8")
    out["lines"] = []
    out[LINE_STORAGE_KEY] = key
    return out, (key, body)


def load_page_lines(page_graph: dict[str, Any] | None) -> list[Any]:
    """Line dicts for one page, from the sidecar file or from the inline list."""
    if not isinstance(page_graph, dict):
        return []
    key = page_graph.get(LINE_STORAGE_KEY)
    if isinstance(key, str) and key.strip():
        from services.storage import storage_key_to_abs_path

        path = storage_key_to_abs_path(key)
        if not path.is_file():
            logger.warning("sheet_lines_file_missing", extra={"storage_key": key})
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        lines = raw.get("lines") if isinstance(raw, dict) else None
        return lines if isinstance(lines, list) else []
    lines = page_graph.get("lines")
    return lines if isinstance(lines, list) else []


def persist_sheet_entity_graph(
    session: Session,
    drawing_id: int,
    graph: SheetEntityGraph,
) -> None:
    """Store graph under ``drawing.index_stats_json['sheetEntityGraph'][page]``.

    Drawing has no dedicated ``meta`` column; index_stats_json is the v1 sink.
    Line geometry above ``INLINE_LINE_LIMIT`` is a file next to the PDF. The
    drawing row keeps ``line_count`` and ``line_storage_key``.
    """
    from services.storage import storage_key_to_abs_path, write_bytes_to_storage_key

    drawing = session.get(Drawing, int(drawing_id))
    if drawing is None:
        raise ValueError(f"Drawing {drawing_id} not found")

    stats: dict[str, Any] = {}
    existing = cast(dict[str, Any] | None, drawing.index_stats_json)
    if isinstance(existing, dict):
        stats = dict(existing)

    by_page = stats.get(SHEET_ENTITY_GRAPH_KEY)
    graphs: dict[str, Any] = dict(by_page) if isinstance(by_page, dict) else {}
    previous = graphs.get(str(graph.page))
    previous_key = previous.get(LINE_STORAGE_KEY) if isinstance(previous, dict) else None
    project_id = int(drawing.project_id) if drawing.project_id is not None else 0
    payload, sidecar = partition_sheet_lines(
        sheet_entity_graph_to_json(graph),
        project_id=project_id,
        drawing_id=int(drawing_id),
    )
    if sidecar is not None:
        key, body = sidecar
        write_bytes_to_storage_key(key, body)
    elif isinstance(previous_key, str) and previous_key.strip():
        old_path = storage_key_to_abs_path(previous_key)
        if old_path.is_file():
            old_path.unlink()
    graphs[str(graph.page)] = payload
    stats[SHEET_ENTITY_GRAPH_KEY] = graphs
    drawing.index_stats_json = stats  # type: ignore[assignment]
    session.flush()


def digitize_drawing_page(
    session: Session,
    drawing_id: int,
    page: int = 1,
    *,
    rendition_png: Path,
    source_pdf: Path | None = None,
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

    drawing = session.get(Drawing, int(drawing_id))
    resolved_project_id = project_id
    if resolved_project_id is None and drawing is not None:
        resolved_project_id = cast(int | None, drawing.project_id)

    labels = _labels_from_text_elements(session, int(drawing_id), int(page), viewports)
    pdf_path = _resolve_source_pdf(session, int(drawing_id), source_pdf)
    lines = _extract_lines(
        pdf_path=pdf_path,
        rendition_png=rendition_png,
        viewports=viewports,
        page=int(page),
        session=session,
        drawing_id=int(drawing_id),
        project_id=resolved_project_id,
        line_meta=meta,
    )

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
    if pdf_path is not None:
        from ai.pipelines.pdf_vector_line_extractor import extract_pdf_fill_symbols

        symbols.extend(
            extract_pdf_fill_symbols(pdf_path, page=int(page), viewports=viewports)
        )

    associations = associate_labels_to_symbols(
        labels,
        symbols,
        legend_session=session,
        project_id=resolved_project_id,
    )
    classified = [symbol for symbol in symbols if symbol.detector != "pdf_fill"]
    fill_owned = [symbol for symbol in symbols if symbol.detector == "pdf_fill"]
    meta["grounding_check"] = {
        "outcome": "WARN" if not classified else "OK",
        "reason": "EMPTY_OUTPUT" if not classified else "HAS_SYMBOLS",
        "symbol_count": len(classified),
        "fill_owned_count": len(fill_owned),
    }

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
        detected = [symbol for symbol in symbols if symbol.detector != "pdf_fill"]
        fill_owned = [symbol for symbol in symbols if symbol.detector == "pdf_fill"]
        if detected:
            upsert_drawing_symbols(
                session,
                int(drawing_id),
                detected,
                page=int(page),
                replace_detector="yolo",
            )
        if fill_owned:
            upsert_drawing_symbols(
                session,
                int(drawing_id),
                fill_owned,
                page=int(page),
                replace_detector="pdf_fill",
            )

    return graph
