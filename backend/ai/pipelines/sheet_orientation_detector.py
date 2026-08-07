"""Detect construction-sheet true-north orientation for coordinate normalization."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

logger = logging.getLogger(__name__)

KEYPLAN_NCC_THRESHOLD = 0.70
KEYPLAN_TITLE_BLOCK_X_MIN = 0.65
KEYPLAN_TITLE_BLOCK_Y_MIN = 0.65
KEYPLAN_CARDINAL_ROTATIONS = (0, 90, 180, 270)

ORIENTATION_TEXT_CONFIDENCE = 0.85
KEYPLAN_CV_CONFIDENCE = 0.80
PDF_ROTATION_CONFIDENCE = 0.60
ASSUMED_UP_CONFIDENCE = 0.50

DEFAULT_KEYPLAN_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "keyplan_template.png"
)

_ORIENTATION_LOOSE_RE = re.compile(
    r"\bNORTH\b.{0,20}\b(POINT(?:S|ING)?|ORIENTED|ORIENTATION|ARROW|VIEW)\b",
    re.IGNORECASE,
)
_DIRECTION_WORD_RE = re.compile(
    r"\b(UP|DOWN|LEFT|RIGHT|SOUTH|NORTH|EAST|WEST)\b",
    re.IGNORECASE,
)

ORIENTATION_TEXT_TO_DEG: dict[str, float] = {
    "UP": 0.0,
    "NORTH": 0.0,
    "DOWN": 180.0,
    "SOUTH": 180.0,
    "LEFT": 90.0,
    "WEST": 90.0,
    "RIGHT": 270.0,
    "EAST": 270.0,
}


class _TextElementLike(Protocol):
    page: int
    text: str


@dataclass(frozen=True)
class SheetOrientationResult:
    true_north_rotation_deg: float
    true_north_source: str
    confidence: float
    keyplan_bbox: list[float] | None = None
    keyplan_match_score: float | None = None
    orientation_text: str | None = None


def _normalize_cardinal_degrees(degrees: float) -> float:
    normalized = float(degrees) % 360.0
    if normalized in KEYPLAN_CARDINAL_ROTATIONS:
        return normalized
    # Snap to nearest cardinal for construction sheets.
    cardinals = KEYPLAN_CARDINAL_ROTATIONS
    return float(min(cardinals, key=lambda value: min(abs(normalized - value), abs(normalized - value - 360))))


def _direction_word_to_degrees(text: str) -> float | None:
    matches = list(_DIRECTION_WORD_RE.finditer(text))
    if not matches:
        return None

    # Prefer the last direction word in the snippet — e.g. "NORTH POINTING DOWN".
    for match in reversed(matches):
        word = match.group(1).upper()
        if word == "NORTH":
            continue
        if word in ORIENTATION_TEXT_TO_DEG:
            return ORIENTATION_TEXT_TO_DEG[word]

    for match in matches:
        word = match.group(1).upper()
        if word in ORIENTATION_TEXT_TO_DEG:
            return ORIENTATION_TEXT_TO_DEG[word]
    return None


def detect_orientation_from_text(texts: Sequence[str]) -> tuple[float, str] | None:
    """Return ``(rotation_deg, snippet)`` when an orientation callout is found."""
    combined = "\n".join(text.strip() for text in texts if text and text.strip())
    if not combined:
        return None

    for match in _ORIENTATION_LOOSE_RE.finditer(combined):
        start = max(0, match.start() - 10)
        end = min(len(combined), match.end() + 40)
        snippet = combined[start:end].strip()
        degrees = _direction_word_to_degrees(snippet)
        if degrees is not None:
            return _normalize_cardinal_degrees(degrees), snippet

    return None


def _title_block_texts(
    text_elements: Sequence[_TextElementLike],
    *,
    page: int,
) -> list[str]:
    return [str(element.text) for element in text_elements if int(element.page) == page]


def _rotate_image_90_steps(image: Any, steps: int) -> Any:
    import cv2  # type: ignore[import-untyped]

    steps = steps % 4
    if steps == 0:
        return image
    if steps == 1:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if steps == 2:
        return cv2.rotate(image, cv2.ROTATE_180)
    return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)


def detect_orientation_from_keyplan_cv(
    rendition_png_path: Path,
    *,
    page_number: int = 1,
    template_path: Path | None = None,
) -> tuple[float, float, list[float]] | None:
    """Return ``(rotation_deg, ncc_score, keyplan_bbox_norm)`` when CV matches."""
    template_path = template_path or DEFAULT_KEYPLAN_TEMPLATE_PATH
    if not template_path.exists():
        return None

    try:
        import cv2  # type: ignore[import-untyped]
        import numpy as np  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("opencv/numpy unavailable; skipping keyplan orientation CV")
        return None

    image = cv2.imread(str(rendition_png_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None

    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        return None

    height, width = image.shape[:2]
    x0 = int(width * KEYPLAN_TITLE_BLOCK_X_MIN)
    y0 = int(height * KEYPLAN_TITLE_BLOCK_Y_MIN)
    region = image[y0:height, x0:width]
    if region.size == 0:
        return None

    best_score = -1.0
    best_rotation = 0
    best_loc = (0, 0)
    best_template_shape = template.shape[:2]

    for rotation in KEYPLAN_CARDINAL_ROTATIONS:
        steps = int(rotation // 90)
        rotated_template = _rotate_image_90_steps(template, steps)
        th, tw = rotated_template.shape[:2]
        if th > region.shape[0] or tw > region.shape[1]:
            continue
        result = cv2.matchTemplate(region, rotated_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if float(max_val) > best_score:
            best_score = float(max_val)
            best_rotation = rotation
            best_loc = max_loc
            best_template_shape = (th, tw)

    if best_score < KEYPLAN_NCC_THRESHOLD:
        return None

    match_x0 = x0 + best_loc[0]
    match_y0 = y0 + best_loc[1]
    match_x1 = match_x0 + best_template_shape[1]
    match_y1 = match_y0 + best_template_shape[0]
    bbox_norm = [
        match_x0 / width,
        match_y0 / height,
        match_x1 / width,
        match_y1 / height,
    ]
    return _normalize_cardinal_degrees(float(best_rotation)), best_score, bbox_norm


def detect_sheet_orientation(
    *,
    page: int,
    page_meta: dict[str, Any],
    text_elements: Sequence[_TextElementLike],
    rendition_png_path: Path | None = None,
    keyplan_template_path: Path | None = None,
) -> SheetOrientationResult:
    """Detect orientation using text → keyplan CV → PDF rotation → assumed up."""
    page_texts = _title_block_texts(text_elements, page=page)

    text_match = detect_orientation_from_text(page_texts)
    if text_match is not None:
        rotation_deg, snippet = text_match
        return SheetOrientationResult(
            true_north_rotation_deg=rotation_deg,
            true_north_source="orientation_text",
            confidence=ORIENTATION_TEXT_CONFIDENCE,
            orientation_text=snippet,
        )

    if rendition_png_path is not None and rendition_png_path.exists():
        cv_match = detect_orientation_from_keyplan_cv(
            rendition_png_path,
            page_number=page,
            template_path=keyplan_template_path,
        )
        if cv_match is not None:
            rotation_deg, score, bbox = cv_match
            return SheetOrientationResult(
                true_north_rotation_deg=rotation_deg,
                true_north_source="keyplan_cv",
                confidence=KEYPLAN_CV_CONFIDENCE,
                keyplan_bbox=bbox,
                keyplan_match_score=score,
            )

    pdf_rotation = page_meta.get("rotation")
    if pdf_rotation is not None:
        try:
            rotation_deg = _normalize_cardinal_degrees(float(pdf_rotation))
            return SheetOrientationResult(
                true_north_rotation_deg=rotation_deg,
                true_north_source="pdf_rotation",
                confidence=PDF_ROTATION_CONFIDENCE,
            )
        except (TypeError, ValueError):
            pass

    return SheetOrientationResult(
        true_north_rotation_deg=0.0,
        true_north_source="assumed_up",
        confidence=ASSUMED_UP_CONFIDENCE,
    )


def enrich_page_meta_with_orientation(
    page_meta: dict[str, Any],
    result: SheetOrientationResult,
) -> dict[str, Any]:
    """Return a copy of ``page_meta`` with orientation fields added."""
    enriched = dict(page_meta)
    enriched["true_north_rotation_deg"] = result.true_north_rotation_deg
    enriched["true_north_source"] = result.true_north_source
    enriched["orientation_text"] = result.orientation_text
    enriched["keyplan_bbox"] = result.keyplan_bbox
    enriched["keyplan_match_score"] = result.keyplan_match_score
    return enriched
