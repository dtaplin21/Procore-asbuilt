"""Native PDF text in the same display fractional frame as Document AI and vectors.

``get_text("words")`` boxes are in unrotated PDF user space. For rotated sheets,
``page.rotation_matrix`` maps them to the rendered orientation; ``page.rect`` is
the normalizing size (post-rotation), matching ``page.get_pixmap`` / viewer PNGs.

Vector geometry uses ``pdf_display_space`` (``transformation_matrix``); native
text uses this module until both paths are unified.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import fitz


@dataclasses.dataclass(frozen=True)
class DisplayWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    source: str = "native_pdf"

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0


def native_words_display_fractional(page: fitz.Page) -> list[DisplayWord]:
    """Native text-layer words as fractions of the page as rendered."""
    width = float(page.rect.width)
    height = float(page.rect.height)
    if width <= 0 or height <= 0:
        return []
    matrix = page.rotation_matrix
    out: list[DisplayWord] = []
    for w in page.get_text("words"):
        text = str(w[4]).strip()
        if not text:
            continue
        rect = fitz.Rect(w[0], w[1], w[2], w[3]) * matrix
        rect.normalize()
        out.append(
            DisplayWord(
                text=text,
                x0=rect.x0 / width,
                y0=rect.y0 / height,
                x1=rect.x1 / width,
                y1=rect.y1 / height,
            )
        )
    return out


def _token_box(token: Any) -> tuple[float, float, float, float]:
    if hasattr(token, "bbox") and hasattr(token.bbox, "to_fractional"):
        return token.bbox.to_fractional()
    if hasattr(token, "x0"):
        return float(token.x0), float(token.y0), float(token.x1), float(token.y1)
    if isinstance(token, dict):
        bbox = token.get("bbox_json") or token
        return (
            float(bbox["x0"]),
            float(bbox["y0"]),
            float(bbox["x1"]),
            float(bbox["y1"]),
        )
    bbox = token.bbox_json
    return float(bbox["x0"]), float(bbox["y0"]), float(bbox["x1"]), float(bbox["y1"])


def _token_text(token: Any) -> str:
    if isinstance(token, dict):
        return str(token.get("text", "")).strip().upper()
    return str(getattr(token, "text", "")).strip().upper()


def frame_agreement(
    native: list[Any],
    docai: list[Any],
    *,
    center_tol: float = 0.01,
    min_chars: int = 3,
) -> dict[str, float | int | None]:
    """Share of native tokens that align with a Document AI token at the same place."""
    docai_by_text: dict[str, list[tuple[float, float]]] = {}
    for token in docai:
        x0, y0, x1, y1 = _token_box(token)
        docai_by_text.setdefault(_token_text(token), []).append(((x0 + x1) / 2.0, (y0 + y1) / 2.0))

    compared = 0
    matched = 0
    for token in native:
        label = _token_text(token)
        if len(label) < min_chars:
            continue
        candidates = docai_by_text.get(label)
        if not candidates:
            continue
        compared += 1
        x0, y0, x1, y1 = _token_box(token)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if any(abs(cx - ax) <= center_tol and abs(cy - ay) <= center_tol for ax, ay in candidates):
            matched += 1

    agreement = (matched / compared) if compared else None
    return {"compared": compared, "matched": matched, "agreement": agreement}
