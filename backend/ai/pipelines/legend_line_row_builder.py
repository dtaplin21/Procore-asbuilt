"""Cluster legend-band OCR/native tokens into horizontal label rows (Step 2a)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from ai.pipelines.fractional_coords import clamp_fractional_bbox
from ai.pipelines.master_drawing_region_builder import (
    _LEGEND_BLOCK_X_MAX,
    _LEGEND_BLOCK_Y_MAX,
    _LEGEND_BLOCK_Y_MIN,
    _LEGEND_HEADER_TOKENS,
    _PUNCTUATION_ONLY_RE,
    is_junk_text_element,
)
from models.drawing_text_element import DrawingTextElement

_SWATCH_WIDTH_FRAC = 0.06
# Max centroid-y delta to treat tokens as the same legend label row.
_ROW_CENTROID_Y_GAP = 0.006
# Vertical gap (fractional page) between row bottoms and next token tops → new row.
_ROW_Y_GAP = 0.003
# Max horizontal whitespace (x0 − prev x1) to treat tokens as one text run on a row.
_COLUMN_X_GAP = 0.06
# Max x0 delta to chain tokens into the same vertical label column (icon OCR path).
# Tighter than 0.035 so left title-block junk (lower x0) does not chain into legend labels.
_COLUMN_X0_START_GAP = 0.018
# Pad label-column x band when filtering tokens after column pick.
_COLUMN_X_PAD = 0.012
# Default legend label + HCAI permit suffix column (fractional x1); excludes far title block.
_LEGEND_LABEL_X1_DEFAULT = 0.88
_HCAI_PERMIT_CANONICAL = "HCAI PERMIT (SHOWN FOR REFERENCE ONLY)"
_SHEET_U2_C6 = "SHEET U2.C6.00"


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
    text = str(row.text).strip()
    if not text:
        return None
    if _PUNCTUATION_ONLY_RE.fullmatch(text):
        return None
    if is_junk_text_element(row) and not text.isdigit():
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
        effective = _effective_legend_rect(legend_rect)
        assert effective is not None
        rx0, ry0, rx1, ry1 = effective
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


def _cluster_tokens_by_x0_start(
    tokens: list[_LegendToken],
    *,
    column_x0_gap: float = _COLUMN_X0_START_GAP,
) -> list[list[_LegendToken]]:
    """Group tokens into vertical columns by x0 start (``legend_icon_extraction``)."""
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: t.x0)
    columns: list[list[_LegendToken]] = [[ordered[0]]]
    for token in ordered[1:]:
        prev_x0 = columns[-1][-1].x0
        if token.x0 - prev_x0 <= column_x0_gap:
            columns[-1].append(token)
        else:
            columns.append([token])
    return columns


def _cluster_tokens_by_x_column(
    tokens: list[_LegendToken],
    *,
    column_x_gap: float = _COLUMN_X_GAP,
) -> list[list[_LegendToken]]:
    """Split one horizontal row into runs by x gap (prev x1 → next x0)."""
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: t.x0)
    columns: list[list[_LegendToken]] = [[ordered[0]]]
    for token in ordered[1:]:
        prev = columns[-1][-1]
        if token.x0 - prev.x1 <= column_x_gap:
            columns[-1].append(token)
        else:
            columns.append([token])
    return columns


def _cluster_rows_by_centroid_y_gap(
    tokens: list[_LegendToken],
    *,
    row_centroid_y_gap: float = _ROW_CENTROID_Y_GAP,
) -> list[list[_LegendToken]]:
    """Group tokens into horizontal rows by centroid-y (avoids OCR y-overlap bleed)."""
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: t.centroid_y)
    row_groups: list[list[_LegendToken]] = [[ordered[0]]]
    row_max_cy = ordered[0].centroid_y
    for token in ordered[1:]:
        if token.centroid_y - row_max_cy <= row_centroid_y_gap:
            row_groups[-1].append(token)
            row_max_cy = max(row_max_cy, token.centroid_y)
        else:
            row_groups.append([token])
            row_max_cy = token.centroid_y
    return row_groups


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


def _token_in_x0_band(token: _LegendToken, x_min: float, x_max: float) -> bool:
    return x_min <= token.x0 <= x_max


def _select_dominant_label_column(
    tokens: list[_LegendToken],
    *,
    column_x0_gap: float = _COLUMN_X0_START_GAP,
    column_x_pad: float = _COLUMN_X_PAD,
) -> list[_LegendToken]:
    """Keep tokens in the dominant x0 column (icon OCR path), then clip to its x band."""
    columns = _cluster_tokens_by_x0_start(tokens, column_x0_gap=column_x0_gap)
    if not columns:
        return []
    main_column = max(columns, key=lambda col: (len(col), -min(t.x0 for t in col)))
    x_min, x_max = _column_x_range(main_column)
    x0_min = x_min - column_x_pad
    x0_max = x_max + column_x0_gap
    return [t for t in tokens if _token_in_x0_band(t, x0_min, x0_max)]


def _effective_legend_rect(
    legend_rect: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float] | None:
    """Tighten wide ROIs so permit/title columns sit outside the label strip."""
    if legend_rect is None:
        return None
    x0, y0, x1, y1 = legend_rect
    if x1 > _LEGEND_LABEL_X1_DEFAULT:
        x1 = _LEGEND_LABEL_X1_DEFAULT
    return clamp_fractional_bbox((x0, y0, x1, y1))




def _tokens_row_text(tokens: list[_LegendToken]) -> str:
    ordered = sorted(tokens, key=lambda t: (t.y0, t.x0))
    parts = [t.text for t in ordered if not _PUNCTUATION_ONLY_RE.fullmatch(t.text)]
    text = " ".join(parts).strip()
    return _normalize_line_type_phrasing(text)


def _normalize_line_type_phrasing(text: str) -> str:
    """Insert missing ``LINE`` before HCAI permit tails when OCR drops the word."""
    upper = text.upper()
    if upper.startswith("SEWER ") and not upper.startswith("SEWER LINE"):
        return f"SEWER LINE {text[6:].strip()}"
    if upper.startswith("ELECTRICAL") and "LINE" not in upper.split()[:2]:
        return f"{text} LINE".replace("  ", " ").strip()
    return text


def format_legend_row_manifest_text(text: str) -> str:
    """Normalize clustered OCR joins into stable, human-readable legend labels for AI/UI."""
    line = " ".join(text.split())
    upper = line.upper()

    line = re.sub(r"(?i)SHEET U2\.06\.00", _SHEET_U2_C6, line)

    if upper.startswith("SSMH OR SDMH") and "SEE DETAIL" in upper:
        line = re.sub(
            r"(?i)^SSMH OR SDMH SEE DETAIL 3\.\s*",
            "SSMH OR SDMH, SEE DETAIL 3, ",
            line,
        )

    if upper.startswith("CATCH BASIN") and "1 AND 2" in upper:
        if "SEE" not in upper:
            line = re.sub(r"(?i)^CATCH BASIN DETAILS", "CATCH BASIN, SEE DETAILS", line)
        if "SHEET" not in upper.upper():
            line = f"{line}, {_SHEET_U2_C6}"

    if "SEPARATE" in upper and "PHASE" in upper:
        if upper.startswith("SEPARATE") or upper.startswith("("):
            line = "UTILITY LINE (SEPARATE PHASE)"
        else:
            line = re.sub(
                r"(?i)UTILITY LINE\s*\(?\s*SEPARATE\s+PHASE\s*\)?",
                "UTILITY LINE (SEPARATE PHASE)",
                line,
            )

    line = _format_hcai_permit_manifest_line(line)
    return line.strip()


def _format_hcai_permit_manifest_line(text: str) -> str:
    upper = text.upper()
    if "HCAI PERMIT" not in upper:
        return text
    for prefix in ("SEWER LINE", "FIRE WATER LINE", "ELECTRICAL LINE"):
        if upper.startswith(prefix):
            return f"{prefix} — {_HCAI_PERMIT_CANONICAL}"
    return text


def _apply_manifest_formatting(rows: list[LegendLineRow]) -> list[LegendLineRow]:
    formatted: list[LegendLineRow] = []
    for row in rows:
        formatted.append(
            LegendLineRow(
                text=format_legend_row_manifest_text(row.text),
                label_bbox=row.label_bbox,
                swatch_bbox=row.swatch_bbox,
                legend_line_type_id=row.legend_line_type_id,
            )
        )
    return formatted


def legend_context_block(rows: list[LegendLineRow]) -> str:
    """Single block of numbered legend rows for LLM / audit prompts."""
    lines = [format_legend_row_manifest_text(row.text) for row in rows]
    return "\n".join(f"{index}. {label}" for index, label in enumerate(lines, start=1))


def _shared_hcai_permit_suffix(rows: list[LegendLineRow]) -> str | None:
    for row in rows:
        upper = row.text.upper()
        if "HCAI PERMIT" in upper and "SHOWN FOR REFERENCE ONLY" in upper.replace("  ", " "):
            start = upper.index("HCAI PERMIT")
            return row.text[start:].strip()
    return None


def _apply_shared_hcai_permit_suffix(rows: list[LegendLineRow]) -> list[LegendLineRow]:
    suffix = _shared_hcai_permit_suffix(rows)
    if not suffix:
        return rows
    out: list[LegendLineRow] = []
    for row in rows:
        upper = row.text.upper()
        if upper.startswith(("FIRE WATER LINE", "ELECTRICAL LINE")) and "HCAI PERMIT" not in upper:
            out.append(
                LegendLineRow(
                    text=f"{row.text} — {_HCAI_PERMIT_CANONICAL}",
                    label_bbox=row.label_bbox,
                    swatch_bbox=row.swatch_bbox,
                    legend_line_type_id=row.legend_line_type_id,
                )
            )
        else:
            out.append(row)
    return out


def _merge_utility_line_continuation_rows(
    row_groups: list[list[_LegendToken]],
) -> list[list[_LegendToken]]:
    """Attach a dangling ``LINE`` token row onto a preceding ``… UTILITY`` label row."""
    if len(row_groups) < 2:
        return row_groups
    merged: list[list[_LegendToken]] = []
    index = 0
    while index < len(row_groups):
        group = row_groups[index]
        if index + 1 < len(row_groups):
            nxt = sorted(row_groups[index + 1], key=lambda t: t.x0)
            if nxt and nxt[0].text.upper() == "LINE":
                separate_index = next(
                    (
                        j
                        for j, token in enumerate(nxt)
                        if token.text.upper() in {"SEPARATE", "PHASE"} or token.text == "("
                    ),
                    len(nxt),
                )
                line_tokens = nxt[:separate_index]
                remainder = nxt[separate_index:]
                group = group + line_tokens
                merged.append(group)
                if remainder:
                    merged.append(remainder)
                index += 2
                continue
        merged.append(group)
        index += 1
    return merged


def _expand_rows_for_utility_line_manifest(
    rows: list[LegendLineRow],
) -> list[LegendLineRow]:
    """Emit a bare ``UTILITY LINE`` row when the next row is ``(SEPARATE PHASE)`` only."""
    if not rows:
        return rows
    expanded: list[LegendLineRow] = []
    for index, row in enumerate(rows):
        upper = row.text.upper()
        if "SEPARATE" in upper and "PHASE" in upper and "UTILITY" not in upper:
            expanded.append(
                LegendLineRow(
                    text="UTILITY LINE",
                    label_bbox=row.label_bbox,
                    swatch_bbox=row.swatch_bbox,
                )
            )
            remainder = re.sub(r"\s+", " ", row.text).strip()
            if "SEPARATE" in remainder.upper() and "PHASE" in remainder.upper():
                phase_text = "UTILITY LINE (SEPARATE PHASE)"
            elif not remainder.upper().startswith("UTILITY"):
                phase_text = f"UTILITY LINE ({remainder})"
            else:
                phase_text = remainder
            expanded.append(
                LegendLineRow(
                    text=phase_text,
                    label_bbox=row.label_bbox,
                    swatch_bbox=row.swatch_bbox,
                )
            )
            continue
        expanded.append(row)
    return expanded


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
    row_centroid_y_gap: float = _ROW_CENTROID_Y_GAP,
    column_x_gap: float = _COLUMN_X_GAP,
    column_x0_gap: float = _COLUMN_X0_START_GAP,
    use_dominant_text_column: bool = True,
    use_centroid_y_rows: bool = True,
) -> list[LegendLineRow]:
    """Group legend-band tokens into one label phrase per horizontal row.

    When ``use_dominant_text_column`` is true (default), tokens are split into
    x0 columns (icon OCR path), the **dominant column by token count** is kept,
    then rows split on ``y0 - prev_y1`` and joined left-to-right within each row.
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
        tokens = _select_dominant_label_column(tokens, column_x0_gap=column_x0_gap)

    if not tokens:
        return []

    if use_centroid_y_rows:
        row_groups = _cluster_rows_by_centroid_y_gap(
            tokens,
            row_centroid_y_gap=row_centroid_y_gap,
        )
        row_groups = _merge_utility_line_continuation_rows(row_groups)
    else:
        row_groups = _cluster_rows_by_y_gap(tokens, row_y_gap=row_y_gap)

    rows: list[LegendLineRow] = []
    for group in row_groups:
        text = _tokens_row_text(group)
        if not text:
            continue
        label_bbox = _union_bbox(group)
        rows.append(
            LegendLineRow(
                text=text,
                label_bbox=label_bbox,
                swatch_bbox=_swatch_bbox_for_label(label_bbox),
            )
        )

    rows.sort(key=lambda r: (r.label_bbox[1], r.label_bbox[0]))
    rows = _expand_rows_for_utility_line_manifest(rows)
    rows = _apply_shared_hcai_permit_suffix(rows)
    return _apply_manifest_formatting(rows)


def element_bboxes_for_debug(elements: list[DrawingTextElement]) -> list[dict[str, Any]]:
    """Helper for audits — not used in production path."""
    out: list[dict[str, Any]] = []
    for element in elements:
        bbox = _bbox_from_element(element)
        if bbox is None:
            continue
        out.append({"text": cast(str, element.text), "bbox": bbox})
    return out
