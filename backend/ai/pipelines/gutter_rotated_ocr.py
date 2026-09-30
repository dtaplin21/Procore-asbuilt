"""Supplemental OCR on the plan left gutter with rotation correction (e.g. HIGHWAY 24).

Full-page Document AI / Tesseract often miss vertically oriented gutter labels on
rotation=270 CAD sheets. This crops the gutter band, tries 0/90/180/270° deskew
for Tesseract, and maps words back to fractional page coordinates.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Any

from PIL import Image

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.fractional_coords import clamp_fractional_bbox
from ai.pipelines.legend_icon_extraction import render_pdf_page_image
from ai.pipelines.ocr_engine import ocr_image_tesseract, tesseract_is_available
from config import settings

logger = logging.getLogger(__name__)

_GUTTER_SOURCE = "gutter_rotated_ocr"
_HIGHWAY_RE = re.compile(r"HIGHWAY\s*\d*", re.IGNORECASE)


def _gutter_frac_rect() -> tuple[float, float, float, float]:
    x1 = float(settings.drawing_index_gutter_x_max)
    y0 = float(settings.drawing_index_gutter_y_min)
    y1 = float(settings.drawing_index_gutter_y_max)
    return clamp_fractional_bbox((0.0, y0, x1, y1))


def _crop_frac(page: Image.Image, rect: tuple[float, float, float, float]) -> Image.Image:
    w, h = page.size
    x0, y0, x1, y1 = rect
    box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    return page.crop(box)


def _word_bbox_to_frac(
    word_bbox: BoundingBox,
    *,
    crop_w: float,
    crop_h: float,
    crop_rect: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    cx0, cy0, cx1, cy1 = crop_rect
    fw = max(crop_w, 1.0)
    fh = max(crop_h, 1.0)
    x0 = cx0 + (word_bbox.x / fw) * (cx1 - cx0)
    y0 = cy0 + (word_bbox.y / fh) * (cy1 - cy0)
    x1 = cx0 + ((word_bbox.x + word_bbox.width) / fw) * (cx1 - cx0)
    y1 = cy0 + ((word_bbox.y + word_bbox.height) / fh) * (cy1 - cy0)
    return clamp_fractional_bbox((x0, y0, x1, y1))


def _map_point_inverse_rotate(
    x: float,
    y: float,
    *,
    img_w: float,
    img_h: float,
    rotate_deg: int,
) -> tuple[float, float]:
    """Map a point from rotated-image space back to pre-rotate crop space."""
    deg = rotate_deg % 360
    if deg == 0:
        return x, y
    if deg == 90:
        return y, img_w - x
    if deg == 180:
        return img_w - x, img_h - y
    if deg == 270:
        return img_h - y, x
    return x, y


def _ocr_crop_with_rotation_attempts(crop: Image.Image) -> tuple[list[PositionedWord], int]:
    """Try Tesseract on crop at several rotations; return best word list + winning rotation."""
    if not tesseract_is_available():
        return [], 0

    best_words: list[PositionedWord] = []
    best_score = -1
    best_rot = 0
    rotations = (0, 90, 180, 270)

    for rot in rotations:
        rotated = crop.rotate(-rot, expand=True) if rot else crop
        buf = BytesIO()
        rotated.save(buf, format="PNG")
        words, rw, rh = ocr_image_tesseract(image_bytes=buf.getvalue(), page_index=0)
        if not words:
            continue
        score = sum(float(w.ocr_confidence or 0.0) for w in words)
        for w in words:
            if _HIGHWAY_RE.search(w.text):
                score += 5.0
        if score > best_score:
            best_score = score
            best_words = words
            best_rot = rot

    if not best_words:
        return [], 0

    orig_w, orig_h = crop.size
    mapped: list[PositionedWord] = []
    for word in best_words:
        bb = word.bbox
        x0, y0 = bb.x, bb.y
        x1, y1 = bb.x + bb.width, bb.y + bb.height
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        if best_rot:
            rot_w, rot_h = (orig_h, orig_w) if best_rot in (90, 270) else (orig_w, orig_h)
            inv_corners = [
                _map_point_inverse_rotate(px, py, img_w=rot_w, img_h=rot_h, rotate_deg=best_rot)
                for px, py in corners
            ]
            xs = [c[0] for c in inv_corners]
            ys = [c[1] for c in inv_corners]
            nx0, ny0, nx1, ny1 = min(xs), min(ys), max(xs), max(ys)
        else:
            nx0, ny0, nx1, ny1 = x0, y0, x1, y1
        mapped.append(
            PositionedWord(
                text=word.text,
                bbox=BoundingBox(
                    x=nx0,
                    y=ny0,
                    width=max(nx1 - nx0, 1.0),
                    height=max(ny1 - ny0, 1.0),
                    page_width=float(orig_w),
                    page_height=float(orig_h),
                ),
                page_index=0,
                ocr_confidence=word.ocr_confidence,
                token_source=_GUTTER_SOURCE,
            )
        )
    return mapped, best_rot


def supplement_gutter_rotated_ocr(
    pdf_path: str,
    *,
    page: int = 1,
    page_rotation_deg: float | None = None,
) -> list[PositionedWord]:
    """Return positioned words to merge into the master index (may be empty)."""
    if not settings.drawing_index_gutter_ocr_enabled:
        return []

    rotation = int(page_rotation_deg or 0) % 360
    if rotation not in (90, 180, 270):
        # Still useful for horizontal gutter text; rotation search handles skew.
        pass

    try:
        page_img = render_pdf_page_image(pdf_path, page=page)
    except Exception as exc:
        logger.warning("gutter_rotated_ocr_render_failed", extra={"error": str(exc)})
        return []

    gutter_rect = _gutter_frac_rect()
    crop = _crop_frac(page_img, gutter_rect)
    if crop.size[0] < 8 or crop.size[1] < 8:
        return []

    words, winning_rot = _ocr_crop_with_rotation_attempts(crop)
    if not words:
        return []

    logger.info(
        "gutter_rotated_ocr_ok",
        extra={
            "page": page,
            "pdf_rotation": rotation,
            "deskew_deg": winning_rot,
            "word_count": len(words),
            "gutter_rect": gutter_rect,
        },
    )

    crop_w, crop_h = crop.size
    out: list[PositionedWord] = []
    for word in words:
        frac = _word_bbox_to_frac(
            word.bbox,
            crop_w=float(crop_w),
            crop_h=float(crop_h),
            crop_rect=gutter_rect,
        )
        x0, y0, x1, y1 = frac
        out.append(
            PositionedWord(
                text=word.text,
                bbox=BoundingBox(
                    x=x0,
                    y=y0,
                    width=x1 - x0,
                    height=y1 - y0,
                    page_width=1.0,
                    page_height=1.0,
                ),
                page_index=page - 1,
                ocr_confidence=word.ocr_confidence,
                token_source=_GUTTER_SOURCE,
            )
        )
    return out
