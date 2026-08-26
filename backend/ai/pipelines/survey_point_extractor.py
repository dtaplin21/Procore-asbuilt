"""Extract paired N/E survey points from OCR tokens."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

POINTS_PER_INCH = 72.0
NE_PAIR_MAX_DISTANCE_FT = 15.0
NE_PAIR_HORIZONTAL_MAX_FT = 12.0
NE_PAIR_VERTICAL_MAX_FT = 8.0
STATION_ATTACH_MAX_FT = 25.0
STRUCTURE_ATTACH_MAX_FT = 25.0
NE_PAIR_MAX_DISTANCE_NORM = 0.12
NE_PAIR_HORIZONTAL_MAX_NORM = 0.15
NE_PAIR_VERTICAL_MAX_NORM = 0.05
STATION_ATTACH_MAX_NORM = 0.08
STRUCTURE_ATTACH_MAX_NORM = 0.08
SCALE_FALLBACK_REAL_FEET_PER_PAPER_INCH = 10.0
MIN_OCR_CONFIDENCE = 0.40

_NORTHING_RE = re.compile(
    r"\bN\s*(?:=|:)?\s*(\d{6,8}(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)
_EASTING_RE = re.compile(
    r"\bE\s*(?:=|:)?\s*(\d{6,8}(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)
_STATION_RE = re.compile(
    r"\b(?:STA\.?\s*)?(\d{1,2}\+\d{2}(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)
_STRUCTURE_RE = re.compile(
    r"\b(SSMH|SSMH-\d+|MH-?\d+|CO-?\d+|SMH|DMH|CB|DI)\b",
    re.IGNORECASE,
)
_BARE_COORD_NUMBER_RE = re.compile(r"^(\d{6,8}(?:\.\d{1,2})?)$")
# California State Plane–style campus coords (UCSF / Bay Area drawings).
_BARE_NORTHING_RANGE = (1_000_000.0, 3_000_000.0)
_BARE_EASTING_RANGE = (5_000_000.0, 7_500_000.0)


class _TextElementLike(Protocol):
    page: int
    text: str
    bbox_json: dict[str, float]
    ocr_confidence: float


@dataclass(frozen=True)
class SurveyPointRecord:
    page: int
    northing: float
    easting: float
    station: str | None
    structure_label: str | None
    label_bbox_json: dict[str, float]
    northing_bbox_json: dict[str, float] | None
    easting_bbox_json: dict[str, float] | None
    ocr_confidence: float
    meta_json: dict[str, Any]


@dataclass(frozen=True)
class PairingScaleContext:
    mode: Literal["physical", "normalized_fallback"]
    scale_json: dict[str, Any] | None
    page_meta: dict[str, Any]
    real_feet_per_paper_inch: float | None
    scale_source: str


def resolve_pairing_scale(
    *,
    scale_json: dict[str, Any] | None,
    page_meta: dict[str, Any],
    scale_source: str,
) -> PairingScaleContext:
    if scale_json and float(scale_json.get("confidence", 0)) >= 0.50:
        return PairingScaleContext(
            mode="physical",
            scale_json=scale_json,
            page_meta=page_meta,
            real_feet_per_paper_inch=float(scale_json["real_feet_per_paper_inch"]),
            scale_source=scale_source,
        )
    if page_meta.get("width_pt") and page_meta.get("height_pt"):
        return PairingScaleContext(
            mode="physical",
            scale_json=None,
            page_meta=page_meta,
            real_feet_per_paper_inch=SCALE_FALLBACK_REAL_FEET_PER_PAPER_INCH,
            scale_source="campus_default",
        )
    return PairingScaleContext(
        mode="normalized_fallback",
        scale_json=None,
        page_meta=page_meta,
        real_feet_per_paper_inch=None,
        scale_source="none",
    )


def normalized_delta_to_feet(
    dx_norm: float,
    dy_norm: float,
    *,
    page_width_pt: float,
    page_height_pt: float,
    real_feet_per_paper_inch: float,
) -> tuple[float, float]:
    page_width_in = page_width_pt / POINTS_PER_INCH
    page_height_in = page_height_pt / POINTS_PER_INCH
    return (
        abs(dx_norm) * page_width_in * real_feet_per_paper_inch,
        abs(dy_norm) * page_height_in * real_feet_per_paper_inch,
    )


def _centroid(bbox: dict[str, float]) -> tuple[float, float]:
    return (
        (bbox["x0"] + bbox["x1"]) / 2.0,
        (bbox["y0"] + bbox["y1"]) / 2.0,
    )


def _distance_between(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    *,
    ctx: PairingScaleContext,
) -> tuple[float, float, float]:
    dx_norm = abs(bx - ax)
    dy_norm = abs(by - ay)
    dist_norm = math.hypot(dx_norm, dy_norm)
    if ctx.mode == "physical":
        assert ctx.real_feet_per_paper_inch is not None
        dx_ft, dy_ft = normalized_delta_to_feet(
            dx_norm,
            dy_norm,
            page_width_pt=float(ctx.page_meta["width_pt"]),
            page_height_pt=float(ctx.page_meta["height_pt"]),
            real_feet_per_paper_inch=ctx.real_feet_per_paper_inch,
        )
        return dx_ft, dy_ft, math.hypot(dx_ft, dy_ft)
    return dx_norm, dy_norm, dist_norm


def pairing_passes_gates(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    *,
    ctx: PairingScaleContext,
) -> tuple[bool, float]:
    dx, dy, dist = _distance_between(ax, ay, bx, by, ctx=ctx)
    if ctx.mode == "physical":
        ok = (
            dx <= NE_PAIR_HORIZONTAL_MAX_FT
            and dy <= NE_PAIR_VERTICAL_MAX_FT
            and dist <= NE_PAIR_MAX_DISTANCE_FT
        )
        return ok, dist
    ok = (
        dx <= NE_PAIR_HORIZONTAL_MAX_NORM
        and dy <= NE_PAIR_VERTICAL_MAX_NORM
        and dist <= NE_PAIR_MAX_DISTANCE_NORM
    )
    return ok, dist


def attach_passes_gates(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    *,
    ctx: PairingScaleContext,
    attach_kind: Literal["station", "structure"],
) -> bool:
    _, _, dist = _distance_between(ax, ay, bx, by, ctx=ctx)
    if ctx.mode == "physical":
        max_ft = STATION_ATTACH_MAX_FT if attach_kind == "station" else STRUCTURE_ATTACH_MAX_FT
        return dist <= max_ft
    max_norm = STATION_ATTACH_MAX_NORM if attach_kind == "station" else STRUCTURE_ATTACH_MAX_NORM
    return dist <= max_norm


def _valid_bbox(bbox: Any) -> dict[str, float] | None:
    if not isinstance(bbox, dict):
        return None
    try:
        x0 = float(bbox["x0"])
        y0 = float(bbox["y0"])
        x1 = float(bbox["x1"])
        y1 = float(bbox["y1"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _classify_bare_coordinate(value: float) -> Literal["northing", "easting"] | None:
    """Classify OCR-only numeric tokens (no ``N``/``E`` prefix) by campus value ranges."""
    if _BARE_NORTHING_RANGE[0] <= value <= _BARE_NORTHING_RANGE[1]:
        return "northing"
    if _BARE_EASTING_RANGE[0] <= value <= _BARE_EASTING_RANGE[1]:
        return "easting"
    return None


def _append_coord_token(
    tokens: list[tuple[float, dict[str, float], float]],
    *,
    value: float,
    bbox: dict[str, float],
    confidence: float,
) -> None:
    tokens.append((value, bbox, confidence))


def extract_survey_points_from_elements(
    elements: Sequence[_TextElementLike],
    *,
    scale_json: dict[str, Any] | None,
    page_meta_json: list[dict[str, Any]],
    scale_source: str = "master_index",
) -> list[SurveyPointRecord]:
    by_page: dict[int, list[_TextElementLike]] = {}
    for element in elements:
        by_page.setdefault(int(element.page), []).append(element)

    page_meta_by_num = {int(page["page"]): page for page in page_meta_json}
    results: list[SurveyPointRecord] = []

    for page, page_elements in by_page.items():
        page_meta = page_meta_by_num.get(
            page,
            page_meta_json[0] if page_meta_json else {},
        )
        ctx = resolve_pairing_scale(
            scale_json=scale_json,
            page_meta=page_meta,
            scale_source=scale_source,
        )

        n_tokens: list[tuple[float, dict[str, float], float]] = []
        e_tokens: list[tuple[float, dict[str, float], float]] = []
        for element in page_elements:
            bbox = _valid_bbox(element.bbox_json)
            if bbox is None:
                continue
            text = str(element.text)
            confidence = float(getattr(element, "ocr_confidence", 1.0))
            northing_match = _NORTHING_RE.search(text)
            if northing_match:
                _append_coord_token(
                    n_tokens,
                    value=float(northing_match.group(1)),
                    bbox=bbox,
                    confidence=confidence,
                )
            easting_match = _EASTING_RE.search(text)
            if easting_match:
                _append_coord_token(
                    e_tokens,
                    value=float(easting_match.group(1)),
                    bbox=bbox,
                    confidence=confidence,
                )
            if northing_match is None and easting_match is None:
                bare_match = _BARE_COORD_NUMBER_RE.match(text.strip())
                if bare_match is not None:
                    kind = _classify_bare_coordinate(float(bare_match.group(1)))
                    if kind == "northing":
                        _append_coord_token(
                            n_tokens,
                            value=float(bare_match.group(1)),
                            bbox=bbox,
                            confidence=confidence,
                        )
                    elif kind == "easting":
                        _append_coord_token(
                            e_tokens,
                            value=float(bare_match.group(1)),
                            bbox=bbox,
                            confidence=confidence,
                        )

        for n_val, n_bbox, n_conf in n_tokens:
            nx, ny = _centroid(n_bbox)
            best_e: tuple[float, dict[str, float], float] | None = None
            best_dist = float("inf")
            for e_val, e_bbox, e_conf in e_tokens:
                ex, ey = _centroid(e_bbox)
                ok, dist = pairing_passes_gates(nx, ny, ex, ey, ctx=ctx)
                if ok and dist < best_dist:
                    best_dist = dist
                    best_e = (e_val, e_bbox, e_conf)
            if best_e is None:
                continue

            e_val, e_bbox, e_conf = best_e
            ocr_confidence = min(n_conf, e_conf)
            if ocr_confidence < MIN_OCR_CONFIDENCE:
                continue

            label_bbox = {
                "x0": min(n_bbox["x0"], e_bbox["x0"]),
                "y0": min(n_bbox["y0"], e_bbox["y0"]),
                "x1": max(n_bbox["x1"], e_bbox["x1"]),
                "y1": max(n_bbox["y1"], e_bbox["y1"]),
            }

            station: str | None = None
            structure_label: str | None = None
            for element in page_elements:
                bbox = _valid_bbox(element.bbox_json)
                if bbox is None:
                    continue
                cx, cy = _centroid(bbox)
                text = str(element.text)
                station_match = _STATION_RE.search(text)
                if station_match and attach_passes_gates(
                    nx, ny, cx, cy, ctx=ctx, attach_kind="station"
                ):
                    station = station_match.group(1)
                structure_match = _STRUCTURE_RE.search(text)
                if structure_match and attach_passes_gates(
                    nx, ny, cx, cy, ctx=ctx, attach_kind="structure"
                ):
                    structure_label = structure_match.group(1).upper()

            meta: dict[str, Any] = {
                "pairing_scale_mode": ctx.mode,
                "pairing_scale_source": ctx.scale_source,
            }
            if ctx.mode == "physical":
                meta["pairing_distance_ft"] = best_dist
            else:
                meta["pairing_distance_norm"] = best_dist
            if ctx.scale_source in ("campus_default", "none"):
                meta["scale_fallback"] = True

            results.append(
                SurveyPointRecord(
                    page=page,
                    northing=n_val,
                    easting=e_val,
                    station=station,
                    structure_label=structure_label,
                    label_bbox_json=label_bbox,
                    northing_bbox_json=n_bbox,
                    easting_bbox_json=e_bbox,
                    ocr_confidence=ocr_confidence,
                    meta_json=meta,
                )
            )

    return results


def extract_stations_from_text(text: str) -> list[str]:
    """Return normalized station strings found in free text (e.g. ``10+90.95``)."""
    if not text:
        return []
    seen: set[str] = set()
    stations: list[str] = []
    for match in _STATION_RE.finditer(text):
        station = match.group(1).strip().upper()
        if not station or station in seen:
            continue
        seen.add(station)
        stations.append(station)
    return stations


def extract_survey_points_from_plain_text(
    text: str,
    *,
    page: int = 1,
    scale_source: str = "plain_text_fallback",
) -> list[SurveyPointRecord]:
    """Fallback when OCR tokens split ``N``/``E`` labels away from numeric values."""
    n_matches = [(match.start(), float(match.group(1))) for match in _NORTHING_RE.finditer(text)]
    e_matches = [(match.start(), float(match.group(1))) for match in _EASTING_RE.finditer(text)]
    if not n_matches or not e_matches:
        return []

    pairs: list[tuple[float, float, int, int]] = []
    for e_pos, e_val in sorted(e_matches, key=lambda item: item[0]):
        preceding = [item for item in n_matches if item[0] < e_pos]
        if not preceding:
            continue
        n_pos, n_val = max(preceding, key=lambda item: item[0])
        if e_pos - n_pos > 160:
            continue
        pairs.append((n_val, e_val, n_pos, e_pos))
        break

    if not pairs:
        return []

    northing, easting, n_pos, e_pos = pairs[0]
    window_start = max(0, min(n_pos, e_pos) - 80)
    window_end = min(len(text), max(n_pos, e_pos) + 80)
    nearby = text[window_start:window_end]
    stations = extract_stations_from_text(nearby) or extract_stations_from_text(text)
    structures = [
        match.group(1).upper()
        for match in _STRUCTURE_RE.finditer(nearby)
    ]

    return [
        SurveyPointRecord(
            page=page,
            northing=northing,
            easting=easting,
            station=stations[0] if stations else None,
            structure_label=structures[0] if structures else None,
            label_bbox_json={"x0": 0.0, "y0": 0.0, "x1": 0.01, "y1": 0.01},
            northing_bbox_json=None,
            easting_bbox_json=None,
            ocr_confidence=0.75,
            meta_json={
                "pairing_scale_source": scale_source,
                "plain_text_fallback": True,
            },
        )
    ]


_UNTRUSTED_SURVEY_SOURCES = frozenset({"pre2_baseline_seed"})
_MIN_PLACED_BBOX_AREA = 0.00005


def is_placed_survey_label_bbox(
    bbox: Any,
    *,
    source: str | None = None,
    meta_json: dict[str, Any] | None = None,
) -> bool:
    """True when a survey point bbox is suitable for coordinate pin placement on a drawing."""
    if not isinstance(bbox, dict):
        return False
    try:
        x0 = float(bbox["x0"])
        y0 = float(bbox["y0"])
        x1 = float(bbox["x1"])
        y1 = float(bbox["y1"])
    except (KeyError, TypeError, ValueError):
        return False

    width = x1 - x0
    height = y1 - y0
    if width <= 0 or height <= 0:
        return False
    if width * height < _MIN_PLACED_BBOX_AREA:
        return False
    if source in _UNTRUSTED_SURVEY_SOURCES:
        return False
    if isinstance(meta_json, dict) and meta_json.get("plain_text_fallback"):
        return False
    return True
