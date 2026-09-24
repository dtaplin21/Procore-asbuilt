"""Cluster legend-band OCR/native tokens into horizontal label rows (Step 2a)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from ai.pipelines.fractional_coords import clamp_fractional_bbox
from ai.pipelines.master_drawing_region_builder import (
    _LEGEND_BLOCK_X_MAX,
    _LEGEND_BLOCK_Y_MAX,
    _LEGEND_BLOCK_Y_MIN,
    _LEGEND_HEADER_TOKENS,
    is_junk_text_element,
)
from models.drawing_text_element import DrawingTextElement

_SWATCH_WIDTH_FRAC = 0.06
_ROW_Y_TOLERANCE = 0.008


@dataclass(frozen=True)
class LegendLineRow:
    text: str
    label_bbox: tuple[float, float, float, float]
    swatch_bbox: tuple[float, float, float, float]
    legend_line_type_id: int | None = None


@dataclass(frozen=True)
class _LegendToken:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    centroid_x: float
    centroid_y: float


def _bbox_from_element(row: DrawingTextElement) -> tuple[float, float, float, float] | None:
    bbox_json = row.bbox_json
    if not isinstance(bbox_json, dict):
        return None
    if not all(key in bbox_json for key in ("x0", "y0", "x1", "y1")):
        return None
    return (
        float(bbox_json["x0"]),
        float(bbox_json["y0"]),
        float(bbox_json["x1"]),
        float(bbox_json["y1"]),
    )


def _token_from_element(row: DrawingTextElement) -> _LegendToken | None:
    if is_junk_text_element(row):
        return None
    text = str(row.text).strip()
    if not text:
        return None
    upper = text.upper()
    if upper in _LEGEND_HEADER_TOKENS:
        return None
    bbox = _bbox_from_element(row)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    return _LegendToken(
        text=text,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        centroid_x=(x0 + x1) / 2.0,
        centroid_y=(y0 + y1) / 2.0,
    )


def _in_legend_band(
    token: _LegendToken,
    *,
    legend_x_max: float,
    legend_y_min: float,
    legend_y_max: float,
) -> bool:
    if token.x0 > legend_x_max:
        return False
    if token.centroid_y < legend_y_min or token.centroid_y > legend_y_max:
        return False
    return True


def _union_bbox(tokens: list[_LegendToken]) -> tuple[float, float, float, float]:
    x0 = min(t.x0 for t in tokens)
    y0 = min(t.y0 for t in tokens)
    x1 = max(t.x1 for t in tokens)
    y1 = max(t.y1 for t in tokens)
    return clamp_fractional_bbox((x0, y0, x1, y1))


def _swatch_bbox_for_label(
    label_bbox: tuple[float, float, float, float],
    *,
    swatch_width_frac: float = _SWATCH_WIDTH_FRAC,
) -> tuple[float, float, float, float]:
    lx0, ly0, lx1, ly1 = label_bbox
    return clamp_fractional_bbox(
        (lx0 - swatch_width_frac, ly0, lx0, ly1),
    )


def cluster_legend_line_rows(
    elements: list[DrawingTextElement],
    *,
    legend_x_max: float = _LEGEND_BLOCK_X_MAX,
    legend_y_min: float = _LEGEND_BLOCK_Y_MIN,
    legend_y_max: float = _LEGEND_BLOCK_Y_MAX,
    row_y_tolerance: float = _ROW_Y_TOLERANCE,
) -> list[LegendLineRow]:
    """Group legend-band tokens by similar cy; join text left-to-right."""
    tokens: list[_LegendToken] = []
    for element in elements:
        token = _token_from_element(element)
        if token is None:
            continue
        if not _in_legend_band(
            token,
            legend_x_max=legend_x_max,
            legend_y_min=legend_y_min,
            legend_y_max=legend_y_max,
        ):
            continue
        tokens.append(token)

    if not tokens:
        return []

    tokens.sort(key=lambda t: (t.centroid_y, t.x0))

    row_groups: list[list[_LegendToken]] = []
    current: list[_LegendToken] = [tokens[0]]
    for token in tokens[1:]:
        mean_cy = sum(t.centroid_y for t in current) / len(current)
        if abs(token.centroid_y - mean_cy) <= row_y_tolerance:
            current.append(token)
        else:
            row_groups.append(current)
            current = [token]
    row_groups.append(current)

    rows: list[LegendLineRow] = []
    for group in row_groups:
        group.sort(key=lambda t: t.x0)
        text = " ".join(t.text for t in group)
        label_bbox = _union_bbox(group)
        rows.append(
            LegendLineRow(
                text=text,
                label_bbox=label_bbox,
                swatch_bbox=_swatch_bbox_for_label(label_bbox),
            )
        )

    rows.sort(key=lambda r: (r.label_bbox[1], r.label_bbox[0]))
    return rows


def element_bboxes_for_debug(elements: list[DrawingTextElement]) -> list[dict[str, Any]]:
    """Helper for audits — not used in production path."""
    out: list[dict[str, Any]] = []
    for element in elements:
        bbox = _bbox_from_element(element)
        if bbox is None:
            continue
        out.append({"text": cast(str, element.text), "bbox": bbox})
    return out
