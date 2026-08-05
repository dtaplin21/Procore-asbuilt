"""Regex-first drawing scale extraction for master drawing auto-index."""

from __future__ import annotations

import re
from typing import Any

from ai.pipelines.document_text_extraction import PositionedWord

TITLE_BLOCK_X_MIN = 0.75
TITLE_BLOCK_Y_MIN = 0.75

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


def _attach_page_dimensions(
    scale_json: dict[str, Any],
    page_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    if page_meta is None:
        return scale_json
    width_pt = page_meta.get("width_pt")
    height_pt = page_meta.get("height_pt")
    if isinstance(width_pt, (int, float)) and width_pt > 0:
        scale_json["page_width_in"] = float(width_pt) / 72.0
    if isinstance(height_pt, (int, float)) and height_pt > 0:
        scale_json["page_height_in"] = float(height_pt) / 72.0
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

    return None
