"""Recover station labels split across adjacent OCR tokens (e.g. ``10`` + ``+`` + ``90.95``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ai.pipelines.survey_point_extractor import (
    SurveyPointRecord,
    _valid_bbox,
    extract_stations_from_text,
)

_ROW_Y_TOLERANCE = 0.012
_MAX_TOKENS_PER_JOIN = 8
_MAX_JOINED_CHARS = 48
_PLAN_VIEW_MAX_Y = 0.55


@dataclass(frozen=True)
class _RowToken:
    text: str
    bbox: dict[str, float]
    page: int
    confidence: float


def _centroid_y(bbox: dict[str, float]) -> float:
    return (float(bbox["y0"]) + float(bbox["y1"])) / 2.0


def _cluster_row_tokens(
    tokens: Sequence[_RowToken],
    *,
    y_tolerance: float = _ROW_Y_TOLERANCE,
) -> list[list[_RowToken]]:
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: (_centroid_y(t.bbox), float(t.bbox["x0"])))
    rows: list[list[_RowToken]] = []
    current: list[_RowToken] = [ordered[0]]
    current_y = _centroid_y(ordered[0].bbox)

    for token in ordered[1:]:
        cy = _centroid_y(token.bbox)
        if abs(cy - current_y) <= y_tolerance:
            current.append(token)
        else:
            rows.append(sorted(current, key=lambda t: float(t.bbox["x0"])))
            current = [token]
            current_y = cy
    rows.append(sorted(current, key=lambda t: float(t.bbox["x0"])))
    return rows


def _join_bbox(tokens: Sequence[_RowToken]) -> dict[str, float]:
    x0 = min(float(t.bbox["x0"]) for t in tokens)
    y0 = min(float(t.bbox["y0"]) for t in tokens)
    x1 = max(float(t.bbox["x1"]) for t in tokens)
    y1 = max(float(t.bbox["y1"]) for t in tokens)
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _stations_from_row(row: Sequence[_RowToken]) -> list[tuple[str, dict[str, float], float]]:
    """Return (station, label_bbox, confidence) discovered on one OCR row."""
    if not row:
        return []

    texts = [t.text.strip() for t in row if t.text.strip()]
    if not texts:
        return []

    hits: list[tuple[str, dict[str, float], float]] = []
    seen: set[str] = set()
    n = len(row)

    for start in range(n):
        parts: list[str] = []
        window: list[_RowToken] = []
        for offset in range(min(_MAX_TOKENS_PER_JOIN, n - start)):
            token = row[start + offset]
            part = token.text.strip()
            if not part:
                continue
            parts.append(part)
            window.append(token)
            joined = " ".join(parts)
            if len(joined) > _MAX_JOINED_CHARS:
                break
            compact = joined.replace(" ", "")
            discovered: set[str] = set()
            for candidate_text in (joined, compact):
                for station in extract_stations_from_text(candidate_text):
                    normalized = station.strip().upper()
                    if normalized in seen or normalized in discovered:
                        continue
                    discovered.add(normalized)
                    seen.add(normalized)
                    conf = min(t.confidence for t in window)
                    hits.append((station, _join_bbox(window), conf))

    return hits


def extract_station_control_points_from_elements(
    elements: Sequence[Any],
    *,
    page_meta_json: list[dict[str, Any]] | None = None,
    max_plan_y: float = _PLAN_VIEW_MAX_Y,
    scale_source: str = "station_control",
) -> list[SurveyPointRecord]:
    """Build station-only control points (N/E zero) from composed plan-view OCR rows."""
    del page_meta_json  # reserved for future plan-viewport clipping
    by_page: dict[int, list[_RowToken]] = {}

    for element in elements:
        bbox = _valid_bbox(getattr(element, "bbox_json", None))
        if bbox is None:
            continue
        if _centroid_y(bbox) > max_plan_y:
            continue
        page = int(getattr(element, "page", 1))
        text = str(getattr(element, "text", "") or "").strip()
        if not text:
            continue
        confidence = float(getattr(element, "ocr_confidence", 1.0))
        by_page.setdefault(page, []).append(
            _RowToken(text=text, bbox=bbox, page=page, confidence=confidence)
        )

    records: list[SurveyPointRecord] = []
    seen_station_page: set[tuple[int, str]] = set()

    for page, tokens in by_page.items():
        for row in _cluster_row_tokens(tokens):
            for station, label_bbox, confidence in _stations_from_row(row):
                key = (page, station.strip().upper())
                if key in seen_station_page:
                    continue
                seen_station_page.add(key)
                records.append(
                    SurveyPointRecord(
                        page=page,
                        northing=0.0,
                        easting=0.0,
                        station=station,
                        structure_label=None,
                        label_bbox_json=label_bbox,
                        northing_bbox_json=None,
                        easting_bbox_json=None,
                        ocr_confidence=confidence,
                        meta_json={
                            "pairing": "station",
                            "station_control": True,
                            "pairing_scale_source": scale_source,
                        },
                    )
                )

    return records
