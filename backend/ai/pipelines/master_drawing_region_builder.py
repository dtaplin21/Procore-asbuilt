"""Auto-generate searchable drawing regions from indexed OCR clusters (Phase 5)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.drawing_scale_parser import TITLE_BLOCK_X_MIN, TITLE_BLOCK_Y_MIN
from ai.pipelines.fractional_coords import clamp_fractional_bbox
from config import settings
from models.drawing_region import DrawingRegion
from models.drawing_text_element import DrawingTextElement
from services.master_drawing_legend_tagger import legend_tags_for_text_element

AUTO_INDEX_REGION_SOURCE = "auto_index"
_MIN_OCR_CONFIDENCE = 0.5
_CLUSTER_BUCKET_SIZE = 0.04
_FIXED_GRID_DIVISIONS = 12
_LEGEND_BLOCK_X_MAX = 0.35
_LEGEND_BLOCK_Y_MIN = 0.20
_LEGEND_BLOCK_Y_MAX = 0.85
_LEGEND_HEADER_TOKENS = frozenset({"LEGEND", "ABBREVIATIONS", "ABBREVIATION", "SYMBOLS", "SYMBOL"})
_PUNCTUATION_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)
_SINGLE_DIGIT_RE = re.compile(r"^\d$")

_TRADE_PHRASES: tuple[tuple[str, str], ...] = (
    ("sanitary sewer", "33-Sanitary Sewerage"),
    ("storm drain", "33-Storm Drainage"),
    ("fire protection", "21-Fire Suppression"),
    ("fire water", "21-Fire Suppression"),
    ("domestic water", "22-Plumbing"),
    ("natural gas", "23-Heating, Ventilating, and Air Conditioning"),
)


@dataclass(frozen=True)
class IndexedElement:
    row: DrawingTextElement
    x0: float
    y0: float
    x1: float
    y1: float
    centroid_x: float
    centroid_y: float


@dataclass(frozen=True)
class GridCell:
    page: int
    column: int
    row: int
    bucket_size: float


def _bbox_from_json(bbox_json: object) -> tuple[float, float, float, float] | None:
    if not isinstance(bbox_json, dict):
        return None
    if all(key in bbox_json for key in ("x0", "y0", "x1", "y1")):
        return (
            float(bbox_json["x0"]),
            float(bbox_json["y0"]),
            float(bbox_json["x1"]),
            float(bbox_json["y1"]),
        )
    if all(key in bbox_json for key in ("x", "y", "width", "height")):
        x = float(bbox_json["x"])
        y = float(bbox_json["y"])
        width = float(bbox_json["width"])
        height = float(bbox_json["height"])
        return x, y, x + width, y + height
    return None


def is_junk_text_element(row: DrawingTextElement) -> bool:
    text = str(row.text).strip()
    if not text:
        return True
    if float(cast(float, row.ocr_confidence)) < _MIN_OCR_CONFIDENCE:
        return True
    if _SINGLE_DIGIT_RE.fullmatch(text):
        return True
    if _PUNCTUATION_ONLY_RE.fullmatch(text):
        return True
    return False


def _indexed_element(row: DrawingTextElement) -> IndexedElement | None:
    bbox = _bbox_from_json(row.bbox_json)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    return IndexedElement(
        row=row,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        centroid_x=(x0 + x1) / 2.0,
        centroid_y=(y0 + y1) / 2.0,
    )


def _grid_bucket(value: float, bucket_size: float) -> int:
    if bucket_size <= 0:
        raise ValueError("bucket_size must be positive")
    bucket = int(value / bucket_size)
    max_bucket = max(0, int(round(1 / bucket_size)) - 1)
    return max(0, min(bucket, max_bucket))


def cluster_elements_by_grid(
    elements: list[IndexedElement],
    *,
    bucket_size: float,
) -> list[list[IndexedElement]]:
    buckets: dict[tuple[int, int, int], list[IndexedElement]] = {}
    for element in elements:
        page = int(element.row.page)
        key = (
            page,
            _grid_bucket(element.centroid_x, bucket_size),
            _grid_bucket(element.centroid_y, bucket_size),
        )
        buckets.setdefault(key, []).append(element)
    return list(buckets.values())


def cluster_elements_by_fixed_grid(
    elements: list[IndexedElement],
    *,
    divisions: int = _FIXED_GRID_DIVISIONS,
) -> list[tuple[GridCell, list[IndexedElement]]]:
    bucket_size = 1.0 / divisions
    buckets: dict[tuple[int, int, int], list[IndexedElement]] = {}
    for element in elements:
        page = int(element.row.page)
        column = _grid_bucket(element.centroid_x, bucket_size)
        row = _grid_bucket(element.centroid_y, bucket_size)
        key = (page, column, row)
        buckets.setdefault(key, []).append(element)

    grouped: list[tuple[GridCell, list[IndexedElement]]] = []
    for (page, column, row), cluster in sorted(buckets.items()):
        cell = GridCell(page=page, column=column, row=row, bucket_size=bucket_size)
        grouped.append((cell, cluster))
    return grouped


def _union_rect_geometry(
    elements: list[IndexedElement],
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    x0 = min(element.x0 for element in elements)
    y0 = min(element.y0 for element in elements)
    x1 = max(element.x1 for element in elements)
    y1 = max(element.y1 for element in elements)
    x0, y0, x1, y1 = clamp_fractional_bbox((x0, y0, x1, y1))
    geometry: dict[str, Any] = {
        "type": "rect",
        "x": x0,
        "y": y0,
        "width": max(x1 - x0, 0.001),
        "height": max(y1 - y0, 0.001),
        "meta": {"source": AUTO_INDEX_REGION_SOURCE},
    }
    if meta:
        geometry["meta"] = {**geometry["meta"], **meta}
    return geometry


def _fixed_cell_geometry(cell: GridCell, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    geometry: dict[str, Any] = {
        "type": "rect",
        "x": cell.column * cell.bucket_size,
        "y": cell.row * cell.bucket_size,
        "width": cell.bucket_size,
        "height": cell.bucket_size,
        "meta": {
            "source": AUTO_INDEX_REGION_SOURCE,
            "grid": {
                "divisions": _FIXED_GRID_DIVISIONS,
                "column": cell.column,
                "row": cell.row,
            },
        },
    }
    if meta:
        geometry["meta"] = {**geometry["meta"], **meta}
    return geometry


def _cluster_label(elements: list[IndexedElement], *, fallback: str = "Indexed cluster") -> str:
    for element in elements:
        expansion = element.row.legend_expansion
        if isinstance(expansion, str) and expansion.strip():
            return expansion.strip()[:255]

    ranked = sorted(elements, key=lambda item: float(item.row.ocr_confidence), reverse=True)
    parts = [str(item.row.text).strip() for item in ranked[:3] if str(item.row.text).strip()]
    if parts:
        return " ".join(parts)[:255]
    return fallback


def _cluster_location_tags(elements: list[IndexedElement]) -> list[str]:
    tags: set[str] = set()
    for element in elements:
        tags.update(legend_tags_for_text_element(element.row))
    return sorted(tag for tag in tags if tag)


def _cluster_search_text(elements: list[IndexedElement]) -> str:
    parts: list[str] = []
    for element in elements:
        parts.append(str(element.row.text))
        expansion = element.row.legend_expansion
        if isinstance(expansion, str) and expansion.strip():
            parts.append(expansion)
    return " ".join(parts).lower()


def _cluster_inspection_type_tags(elements: list[IndexedElement]) -> list[str]:
    haystack = _cluster_search_text(elements)
    tags: list[str] = []
    for phrase, trade_tag in _TRADE_PHRASES:
        if phrase in haystack and trade_tag not in tags:
            tags.append(trade_tag)
    return tags


def _in_title_block(element: IndexedElement) -> bool:
    return (
        int(element.row.page) == 1
        and element.centroid_x >= TITLE_BLOCK_X_MIN
        and element.centroid_y >= TITLE_BLOCK_Y_MIN
    )


def _in_legend_block(element: IndexedElement) -> bool:
    return (
        int(element.row.page) == 1
        and element.centroid_x <= _LEGEND_BLOCK_X_MAX
        and _LEGEND_BLOCK_Y_MIN <= element.centroid_y <= _LEGEND_BLOCK_Y_MAX
    )


def _legend_block_detected(elements: list[IndexedElement]) -> bool:
    if not elements:
        return False
    header_tokens = {
        str(element.row.text).strip().upper()
        for element in elements
        if str(element.row.text).strip()
    }
    if header_tokens & _LEGEND_HEADER_TOKENS:
        return True
    enriched = sum(
        1
        for element in elements
        if isinstance(element.row.legend_expansion, str) and element.row.legend_expansion.strip()
    )
    return enriched >= 3


def _partition_hybrid_elements(
    elements: list[IndexedElement],
) -> tuple[list[IndexedElement], list[IndexedElement], list[IndexedElement]]:
    title_block: list[IndexedElement] = []
    legend_block: list[IndexedElement] = []
    body: list[IndexedElement] = []

    for element in elements:
        if _in_title_block(element):
            title_block.append(element)
        elif _in_legend_block(element):
            legend_block.append(element)
        else:
            body.append(element)

    if not _legend_block_detected(legend_block):
        body.extend(legend_block)
        legend_block = []

    return title_block, legend_block, body


def _create_region(
    session: Session,
    drawing_id: int,
    cluster: list[IndexedElement],
    *,
    page: int,
    geometry: dict[str, Any],
    label: str,
) -> None:
    session.add(
        DrawingRegion(
            master_drawing_id=drawing_id,
            label=label[:255],
            page=page,
            geometry=geometry,
            location_tags=_cluster_location_tags(cluster),
            inspection_type_tags=_cluster_inspection_type_tags(cluster),
        )
    )


def _load_indexed_elements(session: Session, drawing_id: int) -> list[IndexedElement]:
    rows = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .order_by(DrawingTextElement.page.asc(), DrawingTextElement.id.asc())
        .all()
    )
    return [
        element
        for row in rows
        if not is_junk_text_element(row)
        for element in [_indexed_element(row)]
        if element is not None
    ]


def _build_cluster_regions(
    session: Session,
    drawing_id: int,
    elements: list[IndexedElement],
    *,
    bucket_size: float,
    min_words: int,
) -> int:
    created = 0
    for cluster in cluster_elements_by_grid(elements, bucket_size=bucket_size):
        if len(cluster) < min_words:
            continue
        page = int(cluster[0].row.page)
        _create_region(
            session,
            drawing_id,
            cluster,
            page=page,
            geometry=_union_rect_geometry(cluster),
            label=_cluster_label(cluster),
        )
        created += 1
    return created


def _build_grid_regions(
    session: Session,
    drawing_id: int,
    elements: list[IndexedElement],
) -> int:
    created = 0
    for cell, cluster in cluster_elements_by_fixed_grid(elements):
        if not cluster:
            continue
        _create_region(
            session,
            drawing_id,
            cluster,
            page=cell.page,
            geometry=_fixed_cell_geometry(cell),
            label=_cluster_label(cluster, fallback=f"Grid {cell.row + 1}x{cell.column + 1}"),
        )
        created += 1
    return created


def _build_hybrid_regions(
    session: Session,
    drawing_id: int,
    elements: list[IndexedElement],
) -> int:
    title_block, legend_block, body = _partition_hybrid_elements(elements)
    created = 0

    if title_block:
        _create_region(
            session,
            drawing_id,
            title_block,
            page=1,
            geometry=_union_rect_geometry(title_block, meta={"zone": "title_block"}),
            label="Title block",
        )
        created += 1

    if legend_block:
        _create_region(
            session,
            drawing_id,
            legend_block,
            page=1,
            geometry=_union_rect_geometry(legend_block, meta={"zone": "legend_block"}),
            label="Legend",
        )
        created += 1

    min_words = max(1, int(settings.drawing_index_min_cluster_words))
    created += _build_cluster_regions(
        session,
        drawing_id,
        body,
        bucket_size=_CLUSTER_BUCKET_SIZE,
        min_words=min_words,
    )
    return created


def build_auto_regions_from_text_elements(
    session: Session,
    drawing_id: int,
) -> int:
    """Build auto-generated drawing regions using the configured strategy."""
    indexed = _load_indexed_elements(session, drawing_id)
    mode = settings.drawing_index_auto_region_mode

    if mode == "grid":
        created = _build_grid_regions(session, drawing_id, indexed)
    elif mode == "hybrid":
        created = _build_hybrid_regions(session, drawing_id, indexed)
    else:
        min_words = max(1, int(settings.drawing_index_min_cluster_words))
        bucket_size = _CLUSTER_BUCKET_SIZE
        created = _build_cluster_regions(
            session,
            drawing_id,
            indexed,
            bucket_size=bucket_size,
            min_words=min_words,
        )

    if created:
        session.flush()
    return created
