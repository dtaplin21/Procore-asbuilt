"""Regex-first drawing scale extraction for master drawing auto-index."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ai.pipelines.document_text_extraction import PositionedWord

logger = logging.getLogger(__name__)

TITLE_BLOCK_X_MIN = 0.75
TITLE_BLOCK_Y_MIN = 0.75
SCALE_LLM_CONFIDENCE_THRESHOLD = 0.60
SCALE_LLM_MAX_CONFIDENCE = 0.85

SCALE_PARSE_PROMPT = """
Extract the drawing scale from this construction sheet title-block OCR text.

Look for expressions like:
- 1" = 10'
- 1 inch = 10 feet
- SCALE 1/8" = 1'-0"
- HORIZ 1"=10'  VERT 1"=10'
- 1:100

Respond as JSON:
{
  "found": true,
  "raw_text": "exact scale text from the snippet",
  "paper_inches": 1.0,
  "real_feet": 10.0,
  "confidence": 0.0
}

If no scale is present, respond with:
{"found": false, "raw_text": "", "paper_inches": 0, "real_feet": 0, "confidence": 0.0}

paper_inches and real_feet must express the horizontal scale as:
paper_inches inches on the drawing equals real_feet feet in the field.
"""

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

POINTS_PER_INCH = 72.0

_INCH_FEET_RE = re.compile(
    r"""
    (?P<paper_in>\d+(?:\.\d+)?)
    \s*
    (?:"|inch(?:es)?|in\b)
    \s*=\s*
    (?P<real_ft>\d+(?:\.\d+)?)
    \s*
    (?:'|feet|foot|ft\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ARCH_FRACTION_RE = re.compile(
    r"""
    (?:SCALE\s+)?
    (?P<paper_num>\d+)\s*/\s*(?P<paper_den>\d+)
    \s*
    (?:"|in\b)
    \s*=\s*
    (?P<real_ft>\d+)
    \s*
    '
    \s*
    -?
    \s*
    (?P<real_in>\d+)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_HORIZ_VERT_RE = re.compile(
    r"""
    (?P<label>HORIZ(?:ONTAL)?|VERT(?:ICAL)?)
    \s+
    (?P<paper_in>\d+(?:\.\d+)?)
    \s*
    "
    \s*=\s*
    (?P<real_ft>\d+(?:\.\d+)?)
    \s*
    '
    """,
    re.IGNORECASE | re.VERBOSE,
)

_RATIO_RE = re.compile(
    r"""
    (?:SCALE\s+)?
    1\s*:\s*(?P<denom>\d+(?:\.\d+)?)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _scale_component(paper_in: float, real_ft: float) -> dict[str, float | str]:
    return {"numerator": paper_in, "denominator": real_ft, "units": "in=ft"}


def _scale_ratios(paper_in: float, real_ft: float) -> tuple[float, float]:
    if paper_in <= 0 or real_ft <= 0:
        raise ValueError("scale values must be positive")
    real_feet_per_paper_inch = real_ft / paper_in
    paper_inches_per_real_foot = paper_in / real_ft
    return paper_inches_per_real_foot, real_feet_per_paper_inch


def page_size_inches_from_points(width_pt: float, height_pt: float) -> tuple[float, float]:
    """Convert PDF MediaBox points to paper inches."""
    return width_pt / POINTS_PER_INCH, height_pt / POINTS_PER_INCH


def page_size_inches_from_meta(page_meta: dict[str, Any]) -> tuple[float | None, float | None]:
    """Read cached page size inches from page meta or derive from points."""
    width_in = page_meta.get("page_width_in")
    height_in = page_meta.get("page_height_in")
    if isinstance(width_in, (int, float)) and isinstance(height_in, (int, float)):
        return float(width_in), float(height_in)

    width_pt = page_meta.get("width_pt")
    height_pt = page_meta.get("height_pt")
    if isinstance(width_pt, (int, float)) and isinstance(height_pt, (int, float)):
        if width_pt > 0 and height_pt > 0:
            return page_size_inches_from_points(float(width_pt), float(height_pt))
    return None, None


def real_feet_per_paper_inch_from_scale(
    scale_json: dict[str, Any],
    *,
    axis: str = "horizontal",
) -> float | None:
    """Return feet per paper inch for the requested axis."""
    component_key = "vertical" if axis == "vertical" else "horizontal"
    component = scale_json.get(component_key)
    if isinstance(component, dict):
        try:
            paper_in = float(component["numerator"])
            real_ft = float(component["denominator"])
        except (KeyError, TypeError, ValueError):
            paper_in = 0.0
            real_ft = 0.0
        if paper_in > 0 and real_ft > 0:
            return real_ft / paper_in

    try:
        value = float(scale_json.get("real_feet_per_paper_inch", 0.0))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def real_extent_feet(
    normalized_extent: float,
    page_size_in: float,
    real_feet_per_paper_inch: float,
) -> float:
    """Convert a normalized page fraction to real-world feet on site."""
    return normalized_extent * page_size_in * real_feet_per_paper_inch


def _normalized_bbox_extents(
    bbox: dict[str, float] | tuple[float, float, float, float],
) -> tuple[float, float] | None:
    if isinstance(bbox, tuple):
        if len(bbox) != 4:
            return None
        x0, y0, x1, y1 = bbox
        return max(0.0, x1 - x0), max(0.0, y1 - y0)

    if "x0" in bbox and "x1" in bbox and "y0" in bbox and "y1" in bbox:
        return (
            max(0.0, float(bbox["x1"]) - float(bbox["x0"])),
            max(0.0, float(bbox["y1"]) - float(bbox["y0"])),
        )

    if all(key in bbox for key in ("x", "y", "width", "height")):
        return max(0.0, float(bbox["width"])), max(0.0, float(bbox["height"]))

    return None


def real_size_from_normalized_bbox(
    bbox: dict[str, float] | tuple[float, float, float, float],
    scale_json: dict[str, Any],
    *,
    page_meta: dict[str, Any] | None = None,
) -> dict[str, float] | None:
    """Convert a normalized bbox to real width/height in feet."""
    extents = _normalized_bbox_extents(bbox)
    if extents is None:
        return None

    normalized_width, normalized_height = extents
    page_width_in = scale_json.get("page_width_in")
    page_height_in = scale_json.get("page_height_in")
    if page_meta is not None:
        meta_width_in, meta_height_in = page_size_inches_from_meta(page_meta)
        if page_width_in is None:
            page_width_in = meta_width_in
        if page_height_in is None:
            page_height_in = meta_height_in

    if not isinstance(page_width_in, (int, float)) or not isinstance(page_height_in, (int, float)):
        return None

    horizontal_scale = real_feet_per_paper_inch_from_scale(scale_json, axis="horizontal")
    vertical_scale = real_feet_per_paper_inch_from_scale(scale_json, axis="vertical")
    if horizontal_scale is None or vertical_scale is None:
        return None

    return {
        "width_ft": real_extent_feet(normalized_width, float(page_width_in), horizontal_scale),
        "height_ft": real_extent_feet(normalized_height, float(page_height_in), vertical_scale),
    }


def _attach_page_dimensions(
    scale_json: dict[str, Any],
    page_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    if page_meta is None:
        return scale_json
    width_pt = page_meta.get("width_pt")
    height_pt = page_meta.get("height_pt")
    if isinstance(width_pt, (int, float)) and isinstance(height_pt, (int, float)):
        if width_pt > 0 and height_pt > 0:
            page_width_in, page_height_in = page_size_inches_from_points(
                float(width_pt),
                float(height_pt),
            )
            scale_json["page_width_in"] = page_width_in
            scale_json["page_height_in"] = page_height_in
    return scale_json


def _build_scale_json(
    *,
    raw_text: str,
    paper_in: float,
    real_ft: float,
    confidence: float,
    horizontal: dict[str, float | str] | None = None,
    vertical: dict[str, float | str] | None = None,
    page: int = 1,
    source_bbox: list[float] | None = None,
    page_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paper_inches_per_real_foot, real_feet_per_paper_inch = _scale_ratios(paper_in, real_ft)
    horiz = horizontal or _scale_component(paper_in, real_ft)
    vert = vertical or horiz
    result: dict[str, Any] = {
        "raw_text": raw_text,
        "paper_inches_per_real_foot": paper_inches_per_real_foot,
        "real_feet_per_paper_inch": real_feet_per_paper_inch,
        "horizontal": horiz,
        "vertical": vert,
        "confidence": confidence,
        "page": page,
    }
    if source_bbox is not None:
        result["source_bbox"] = source_bbox
    return _attach_page_dimensions(result, page_meta)


def parse_scale_from_text(
    text: str,
    *,
    page: int = 1,
    source_bbox: list[float] | None = None,
    page_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Parse the first supported scale expression from free text."""
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return None

    horiz_match: re.Match[str] | None = None
    vert_match: re.Match[str] | None = None
    for match in _HORIZ_VERT_RE.finditer(normalized):
        label = match.group("label").upper()
        if label.startswith("HORIZ"):
            horiz_match = match
        elif label.startswith("VERT"):
            vert_match = match

    if horiz_match is not None:
        paper_in = float(horiz_match.group("paper_in"))
        real_ft = float(horiz_match.group("real_ft"))
        horizontal = _scale_component(paper_in, real_ft)
        vertical = horizontal
        if vert_match is not None:
            vertical = _scale_component(
                float(vert_match.group("paper_in")),
                float(vert_match.group("real_ft")),
            )
        raw = horiz_match.group(0)
        if vert_match is not None and vert_match.group(0) not in raw:
            raw = f"{raw} {vert_match.group(0)}"
        return _build_scale_json(
            raw_text=raw.strip(),
            paper_in=paper_in,
            real_ft=real_ft,
            confidence=0.92,
            horizontal=horizontal,
            vertical=vertical,
            page=page,
            source_bbox=source_bbox,
            page_meta=page_meta,
        )

    arch_match = _ARCH_FRACTION_RE.search(normalized)
    if arch_match is not None:
        paper_in = float(arch_match.group("paper_num")) / float(arch_match.group("paper_den"))
        real_ft = float(arch_match.group("real_ft"))
        real_in = arch_match.group("real_in")
        if real_in is not None and real_in != "":
            real_ft += float(real_in) / 12.0
        return _build_scale_json(
            raw_text=arch_match.group(0).strip(),
            paper_in=paper_in,
            real_ft=real_ft,
            confidence=0.88,
            page=page,
            source_bbox=source_bbox,
            page_meta=page_meta,
        )

    inch_feet_match = _INCH_FEET_RE.search(normalized)
    if inch_feet_match is not None:
        paper_in = float(inch_feet_match.group("paper_in"))
        real_ft = float(inch_feet_match.group("real_ft"))
        return _build_scale_json(
            raw_text=inch_feet_match.group(0).strip(),
            paper_in=paper_in,
            real_ft=real_ft,
            confidence=0.90,
            page=page,
            source_bbox=source_bbox,
            page_meta=page_meta,
        )

    ratio_match = _RATIO_RE.search(normalized)
    if ratio_match is not None:
        denom = float(ratio_match.group("denom"))
        if denom <= 0:
            return None
        # 1:N architectural scale: 1 paper inch = N real inches.
        paper_in = 1.0
        real_ft = denom / 12.0
        return _build_scale_json(
            raw_text=ratio_match.group(0).strip(),
            paper_in=paper_in,
            real_ft=real_ft,
            confidence=0.72,
            page=page,
            source_bbox=source_bbox,
            page_meta=page_meta,
        )

    return None


def _parse_scale_llm_payload(content: str) -> dict[str, Any]:
    trimmed = (content or "").strip()
    if not trimmed:
        return {"found": False, "raw_text": "", "paper_inches": 0.0, "real_feet": 0.0, "confidence": 0.0}

    candidates = [trimmed]
    block_match = _JSON_BLOCK_RE.search(trimmed)
    if block_match:
        candidates.insert(0, block_match.group(1))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return _sanitize_scale_llm_dict(parsed)

    return {"found": False, "raw_text": "", "paper_inches": 0.0, "real_feet": 0.0, "confidence": 0.0}


def _sanitize_scale_llm_dict(raw: dict[str, Any]) -> dict[str, Any]:
    found = bool(raw.get("found", False))
    raw_text = str(raw.get("raw_text", "") or "").strip()

    try:
        paper_inches = float(raw.get("paper_inches", 0.0))
    except (TypeError, ValueError):
        paper_inches = 0.0

    try:
        real_feet = float(raw.get("real_feet", 0.0))
    except (TypeError, ValueError):
        real_feet = 0.0

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))
    if not found or paper_inches <= 0 or real_feet <= 0:
        found = False

    return {
        "found": found,
        "raw_text": raw_text,
        "paper_inches": paper_inches,
        "real_feet": real_feet,
        "confidence": confidence,
    }


def _call_scale_llm(content: str) -> dict[str, Any]:
    """Send title-block OCR text to the chat model when regex parsing misses."""
    try:
        from config import settings
        from openai import OpenAI
    except ImportError:
        return {"found": False, "raw_text": "", "paper_inches": 0.0, "real_feet": 0.0, "confidence": 0.0}

    if not getattr(settings, "openai_api_key", None):
        return {"found": False, "raw_text": "", "paper_inches": 0.0, "real_feet": 0.0, "confidence": 0.0}

    preview = (content or "").strip()
    if not preview:
        return {"found": False, "raw_text": "", "paper_inches": 0.0, "real_feet": 0.0, "confidence": 0.0}

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        f"{SCALE_PARSE_PROMPT.strip()}\n\n"
        f"Title-block OCR text:\n{preview[:4000]}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=128,
        )
        message = (resp.choices[0].message.content or "").strip()
        return _parse_scale_llm_payload(message)
    except Exception as exc:
        logger.warning("drawing_scale_llm_failed", extra={"error": str(exc)})
        return {"found": False, "raw_text": "", "paper_inches": 0.0, "real_feet": 0.0, "confidence": 0.0}


def parse_scale_from_text_llm(
    text: str,
    *,
    page: int = 1,
    source_bbox: list[float] | None = None,
    page_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """LLM fallback for scale parsing when regex finds nothing."""
    payload = _call_scale_llm(text)
    if not payload.get("found"):
        return None

    confidence = float(payload["confidence"])
    if confidence < SCALE_LLM_CONFIDENCE_THRESHOLD:
        return None

    paper_in = float(payload["paper_inches"])
    real_ft = float(payload["real_feet"])
    raw_text = str(payload.get("raw_text") or text.strip())[:500]
    return _build_scale_json(
        raw_text=raw_text,
        paper_in=paper_in,
        real_ft=real_ft,
        confidence=min(confidence, SCALE_LLM_MAX_CONFIDENCE),
        page=page,
        source_bbox=source_bbox,
        page_meta=page_meta,
    )


def _word_in_title_block(word: PositionedWord) -> bool:
    x0, y0, x1, y1 = word.bbox.to_fractional()
    center_x = (x0 + x1) / 2.0
    center_y = (y0 + y1) / 2.0
    return center_x >= TITLE_BLOCK_X_MIN and center_y >= TITLE_BLOCK_Y_MIN


def _words_to_text(words: list[PositionedWord]) -> str:
    ordered = sorted(words, key=lambda word: (round(word.bbox.y, 1), word.bbox.x))
    return " ".join(word.text.strip() for word in ordered if word.text.strip())


def _words_bbox_fractional(words: list[PositionedWord]) -> list[float]:
    boxes = [word.bbox.to_fractional() for word in words]
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def parse_scale_from_words(
    words: list[PositionedWord],
    *,
    page: int = 1,
    page_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Scan page-1 title block first, then the full page, for scale text."""
    page_index = page - 1
    page_words = [word for word in words if word.page_index == page_index]
    if not page_words:
        return None

    search_regions: list[tuple[str, list[PositionedWord]]] = [
        ("title_block", [word for word in page_words if _word_in_title_block(word)]),
        ("full_page", page_words),
    ]

    for _region_name, region_words in search_regions:
        if not region_words:
            continue
        text = _words_to_text(region_words)
        parsed = parse_scale_from_text(
            text,
            page=page,
            source_bbox=_words_bbox_fractional(region_words),
            page_meta=page_meta,
        )
        if parsed is not None:
            return parsed

        parsed = parse_scale_from_text_llm(
            text,
            page=page,
            source_bbox=_words_bbox_fractional(region_words),
            page_meta=page_meta,
        )
        if parsed is not None:
            return parsed

    return None
