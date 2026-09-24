"""Map PDF user-space geometry to normalized display space (matches ``page.get_pixmap``)."""

from __future__ import annotations

import fitz


def pdf_point_to_display_fractional(page: fitz.Page, x: float, y: float) -> tuple[float, float]:
    """Map one PDF point to fractional page coords using ``transformation_matrix``."""
    pw, ph = page.rect.width, page.rect.height
    if pw <= 0 or ph <= 0:
        raise ValueError("page has invalid dimensions")
    rect = fitz.Rect(x, y, x, y) * page.transformation_matrix
    return float(rect.x0) / pw, float(rect.y0) / ph


def pdf_rect_to_display_fractional(
    page: fitz.Page,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> tuple[float, float, float, float]:
    """Map a PDF axis-aligned rect to fractional display bbox (x0, y0, x1, y1)."""
    pw, ph = page.rect.width, page.rect.height
    if pw <= 0 or ph <= 0:
        raise ValueError("page has invalid dimensions")
    display = fitz.Rect(x0, y0, x1, y1) * page.transformation_matrix
    return (
        float(display.x0) / pw,
        float(display.y0) / ph,
        float(display.x1) / pw,
        float(display.y1) / ph,
    )
