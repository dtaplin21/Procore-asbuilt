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
# Vertical gap (fractional page) between row bottoms and next token tops → new row.
_ROW_Y_GAP = 0.003
# Max horizontal whitespace (x0 − prev x1) to treat tokens as one text run on a row.
_COLUMN_X_GAP = 0.06
# Pad label-column x band when filtering tokens after column pick.
_COLUMN_X_PAD = 0.015


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
    raw_bbox = row.bbox_json
    if not isinstance(raw_bbox, dict):
        return None
    bbox_json = cast(dict[str, Any], raw_bbox)
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


def _token_in_legend_region(
    token: _LegendToken,
    *,
    legend_rect: tuple[float, float, float, float] | None,
    legend_x_max: float,
    legend_y_min: float,
    legend_y_max: float,
) -> bool:
    if legend_rect is not None:
        rx0, ry0, rx1, ry1 = legend_rect
        cx, cy = token.centroid_x, token.centroid_y
        return rx0 <= cx <= rx1 and ry0 <= cy <= ry1
    return _in_legend_band(
        token,
        legend_x_max=legend_x_max,
        legend_y_min=legend_y_min,
        legend_y_max=legend_y_max,
    )


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


def _cluster_tokens_by_x_column(
    tokens: list[_LegendToken],
    *,
    column_x_gap: float = _COLUMN_X_GAP,
) -> list[list[_LegendToken]]:
    """Split tokens into vertical page columns (horizontal gap between sorted x)."""
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: (t.x0, t.centroid_y))
    columns: list[list[_LegendToken]] = [[ordered[0]]]
    for token in ordered[1:]:
        prev = columns[-1][-1]
        if token.x0 - prev.x1 <= column_x_gap:
            columns[-1].append(token)
        else:
            columns.append([token])
    return columns


def _cluster_rows_by_y_gap(
    tokens: list[_LegendToken],
    *,
    row_y_gap: float = _ROW_Y_GAP,
) -> list[list[_LegendToken]]:
    """Group tokens into horizontal bands using y0 vs previous row y1 (not mean cy)."""
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: (t.y0, t.x0))
    row_groups: list[list[_LegendToken]] = [[ordered[0]]]
    row_y1 = ordered[0].y1
    for token in ordered[1:]:
        if token.y0 - row_y1 <= row_y_gap:
            row_groups[-1].append(token)
            row_y1 = max(row_y1, token.y1)
        else:
            row_groups.append([token])
            row_y1 = token.y1
    return row_groups


def _horizontal_runs(
    tokens: list[_LegendToken],
    *,
    column_x_gap: float = _COLUMN_X_GAP,
) -> list[list[_LegendToken]]:
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: t.x0)
    runs: list[list[_LegendToken]] = [[ordered[0]]]
    for token in ordered[1:]:
        prev = runs[-1][-1]
        if token.x0 - prev.x1 <= column_x_gap:
            runs[-1].append(token)
        else:
            runs.append([token])
    return runs


def _column_x_range(column: list[_LegendToken]) -> tuple[float, float]:
    return min(t.x0 for t in column), max(t.x1 for t in column)


def _token_in_x_band(token: _LegendToken, x_min: float, x_max: float) -> bool:
    return x_min <= token.centroid_x <= x_max


def _select_label_column_x_band(
    tokens: list[_LegendToken],
    *,
    column_x_gap: float = _COLUMN_X_GAP,
    row_y_gap: float = _ROW_Y_GAP,
    column_x_pad: float = _COLUMN_X_PAD,
) -> tuple[float, float]:
    """Pick the legend label column: most horizontal rows hit, tie-break leftmost x."""
    columns = _cluster_tokens_by_x_column(tokens, column_x_gap=column_x_gap)
    if not columns:
        return 0.0, 1.0
    if len(columns) == 1:
        x0, x1 = _column_x_range(columns[0])
        return x0 - column_x_pad, x1 + column_x_pad

    y_rows = _cluster_rows_by_y_gap(tokens, row_y_gap=row_y_gap)
    best_col: list[_LegendToken] | None = None
    best_key: tuple[int, float] | None = None
    for column in columns:
        col_x0, col_x1 = _column_x_range(column)
        row_hits = 0
        for row in y_rows:
            if any(_token_in_x_band(t, col_x0, col_x1) for t in row):
                row_hits += 1
        key = (row_hits, -col_x0)
        if best_key is None or key > best_key:
            best_key = key
            best_col = column

    assert best_col is not None
    x0, x1 = _column_x_range(best_col)
    return x0 - column_x_pad, x1 + column_x_pad


def _filter_tokens_to_x_band(
    tokens: list[_LegendToken],
    x_min: float,
    x_max: float,
) -> list[_LegendToken]:
    return [t for t in tokens if _token_in_x_band(t, x_min, x_max)]


def legend_rows_to_manifest(rows: list[LegendLineRow]) -> list[dict[str, Any]]:
    """JSON-serializable legend row manifest for audits / golden regression."""
    manifest: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        lx0, ly0, lx1, ly1 = row.label_bbox
        sx0, sy0, sx1, sy1 = row.swatch_bbox
        manifest.append(
            {
                "index": index,
                "text": row.text,
                "legend_line_type_id": row.legend_line_type_id,
                "label_bbox": {"x0": lx0, "y0": ly0, "x1": lx1, "y1": ly1},
                "swatch_bbox": {"x0": sx0, "y0": sy0, "x1": sx1, "y1": sy1},
            }
        )
    return manifest


def cluster_legend_line_rows(
    elements: list[DrawingTextElement],
    *,
    legend_x_max: float = _LEGEND_BLOCK_X_MAX,
    legend_y_min: float = _LEGEND_BLOCK_Y_MIN,
    legend_y_max: float = _LEGEND_BLOCK_Y_MAX,
    legend_rect: tuple[float, float, float, float] | None = None,
    row_y_gap: float = _ROW_Y_GAP,
    column_x_gap: float = _COLUMN_X_GAP,
    column_x_pad: float = _COLUMN_X_PAD,
    use_dominant_text_column: bool = True,
) -> list[LegendLineRow]:
    """Group legend-band tokens into one label phrase per horizontal row.

    When ``use_dominant_text_column`` is true (default), tokens are restricted
    to the dominant **label column** (most y-bands, tie-break leftmost) before
    row clustering — this drops title-block columns that share the ROI.

    Rows split on vertical gap (``y0 - prev_y1``). Within each row only the
    leftmost horizontal text run is kept so permit / hospital text on the same
    scanline does not merge into the legend label.
    """
    tokens: list[_LegendToken] = []
    for element in elements:
        token = _token_from_element(element)
        if token is None:
            continue
        if not _token_in_legend_region(
            token,
            legend_rect=legend_rect,
            legend_x_max=legend_x_max,
            legend_y_min=legend_y_min,
            legend_y_max=legend_y_max,
        ):
            continue
        tokens.append(token)

    if not tokens:
        return []

    if use_dominant_text_column:
        x_min, x_max = _select_label_column_x_band(
            tokens,
            column_x_gap=column_x_gap,
            row_y_gap=row_y_gap,
            column_x_pad=column_x_pad,
        )
        tokens = _filter_tokens_to_x_band(tokens, x_min, x_max)

    if not tokens:
        return []

    row_groups = _cluster_rows_by_y_gap(tokens, row_y_gap=row_y_gap)

    rows: list[LegendLineRow] = []
    for group in row_groups:
        if use_dominant_text_column:
            runs = _horizontal_runs(group, column_x_gap=column_x_gap)
            if not runs:
                continue
            label_tokens = list(runs[0])
        else:
            label_tokens = list(group)
        label_tokens.sort(key=lambda t: t.x0)
        text = " ".join(t.text for t in label_tokens).strip()
        if not text:
            continue
        label_bbox = _union_bbox(label_tokens)
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
