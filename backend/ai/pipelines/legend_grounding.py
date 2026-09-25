"""Legend exemplar grounding via Document AI tokens + visual template match.

Document AI does not expose Gemini-style pointing; this module uses:

1. **document_ai_text** — find label token sequences on the full sheet from indexed
   or sync-processed Document AI words (plan copy of legend labels).
2. **template_match** — OpenCV normalized cross-correlation on the rendered page
   vs the icon crop (symbols / line swatches without plan text).

Both emit ``GroundingHit`` bboxes in master fractional coordinates.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Sequence, cast

import numpy as np
from PIL import Image

from ai.pipelines.document_ai_sync import process_image_bytes_document_ai
from ai.pipelines.document_text_extraction import PositionedWord
from ai.pipelines.fractional_coords import clamp_fractional_bbox
from ai.pipelines.legend_icon_extraction import LegendIconEntry, LegendIconSource
from config import settings

_TOKEN_SPLIT_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class GroundingHit:
    label_text: str
    confidence: float
    page_fractional_bbox: tuple[float, float, float, float]
    match_method: str
    raw_model_output: str = ""


@dataclass(frozen=True)
class PageWord:
    text: str
    text_normalized: str
    bbox_fractional: tuple[float, float, float, float]
    confidence: float


class GroundingProvider(ABC):
    @abstractmethod
    def find_occurrences(
        self,
        full_page_image: Image.Image,
        exemplar_crop: Image.Image,
        exemplar_label: str,
        exclude_region_fractional: tuple[float, float, float, float] | None = None,
        *,
        full_page_words: Sequence[PageWord] | None = None,
    ) -> list[GroundingHit]:
        raise NotImplementedError


def _normalize_label(text: str) -> str:
    return _TOKEN_SPLIT_RE.sub(" ", text.strip().upper())


def _bbox_intersection_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _bbox_area(b: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = b
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _mostly_inside_exclude(
    bbox: tuple[float, float, float, float],
    exclude: tuple[float, float, float, float] | None,
    *,
    overlap_ratio: float = 0.5,
) -> bool:
    if exclude is None:
        return False
    inter = _bbox_intersection_area(bbox, exclude)
    area = _bbox_area(bbox)
    if area <= 0:
        return False
    return inter / area >= overlap_ratio


def page_words_from_positioned(words: Sequence[PositionedWord]) -> list[PageWord]:
    out: list[PageWord] = []
    for word in words:
        text = str(word.text).strip()
        if not text:
            continue
        frac = word.bbox.to_fractional()
        out.append(
            PageWord(
                text=text,
                text_normalized=_normalize_label(text),
                bbox_fractional=clamp_fractional_bbox(frac),
                confidence=float(word.ocr_confidence or 0.0),
            )
        )
    return out


def _find_text_occurrences(
    *,
    label: str,
    words: Sequence[PageWord],
    exclude_region: tuple[float, float, float, float] | None,
) -> list[GroundingHit]:
    query_tokens = [_normalize_label(t) for t in _TOKEN_SPLIT_RE.split(label) if t.strip()]
    if not query_tokens:
        return []

    ordered = sorted(words, key=lambda w: (w.bbox_fractional[1], w.bbox_fractional[0]))
    hits: list[GroundingHit] = []
    n = len(query_tokens)
    m = len(ordered)
    if m < n:
        return []

    for i in range(m - n + 1):
        window = ordered[i : i + n]
        if [w.text_normalized for w in window] != query_tokens:
            continue
        x0 = min(w.bbox_fractional[0] for w in window)
        y0 = min(w.bbox_fractional[1] for w in window)
        x1 = max(w.bbox_fractional[2] for w in window)
        y1 = max(w.bbox_fractional[3] for w in window)
        bbox = clamp_fractional_bbox((x0, y0, x1, y1))
        if _mostly_inside_exclude(bbox, exclude_region):
            continue
        conf = min(w.confidence for w in window)
        hits.append(
            GroundingHit(
                label_text=label,
                confidence=conf,
                page_fractional_bbox=bbox,
                match_method="document_ai_text",
            )
        )
    return hits


def _template_match_occurrences(
    *,
    full_page_image: Image.Image,
    exemplar_crop: Image.Image,
    exemplar_label: str,
    exclude_region: tuple[float, float, float, float] | None,
    threshold: float,
) -> list[GroundingHit]:
    import cv2

    page_gray = np.asarray(full_page_image.convert("L"))
    tmpl_gray = np.asarray(exemplar_crop.convert("L"))
    th, tw = tmpl_gray.shape[:2]
    ph, pw = page_gray.shape[:2]
    if th < 3 or tw < 3 or ph < th or pw < tw:
        return []

    result = cv2.matchTemplate(page_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= threshold)
    candidates: list[tuple[float, int, int]] = []
    for y, x in zip(ys.tolist(), xs.tolist(), strict=False):
        candidates.append((float(result[y, x]), x, y))

    candidates.sort(key=lambda item: -item[0])
    kept: list[GroundingHit] = []
    min_dist_px = max(th, tw) * 0.6

    for score, x, y in candidates:
        bbox = clamp_fractional_bbox(
            (x / pw, y / ph, (x + tw) / pw, (y + th) / ph),
        )
        if _mostly_inside_exclude(bbox, exclude_region):
            continue
        cx = x + tw / 2.0
        cy = y + th / 2.0
        duplicate = False
        for existing in kept:
            ex0, ey0, ex1, ey1 = existing.page_fractional_bbox
            ecx = ((ex0 + ex1) / 2.0) * pw
            ecy = ((ey0 + ey1) / 2.0) * ph
            if ((cx - ecx) ** 2 + (cy - ecy) ** 2) ** 0.5 < min_dist_px:
                duplicate = True
                break
        if duplicate:
            continue
        kept.append(
            GroundingHit(
                label_text=exemplar_label,
                confidence=float(score),
                page_fractional_bbox=bbox,
                match_method="template_match",
                raw_model_output=f"tm_ccoeff_normed>={threshold:.3f}",
            )
        )
    return kept


class DocumentAiGroundingProvider(GroundingProvider):
    """Ground legend exemplars using Document AI word index + template match."""

    def __init__(
        self,
        *,
        min_confidence: float | None = None,
        template_threshold: float | None = None,
        sync_ocr_fallback: bool = True,
    ) -> None:
        self.min_confidence = (
            float(min_confidence)
            if min_confidence is not None
            else float(settings.document_ai_grounding_min_confidence)
        )
        self.template_threshold = (
            float(template_threshold)
            if template_threshold is not None
            else float(settings.document_ai_grounding_template_threshold)
        )
        self.sync_ocr_fallback = sync_ocr_fallback

    def _full_page_words(
        self,
        full_page_image: Image.Image,
        full_page_words: Sequence[PageWord] | None,
    ) -> list[PageWord]:
        if full_page_words:
            return list(full_page_words)
        if not self.sync_ocr_fallback:
            return []
        buffer = BytesIO()
        full_page_image.save(buffer, format="PNG")
        positioned = process_image_bytes_document_ai(buffer.getvalue(), mime_type="image/png")
        return page_words_from_positioned(positioned)

    def find_occurrences(
        self,
        full_page_image: Image.Image,
        exemplar_crop: Image.Image,
        exemplar_label: str,
        exclude_region_fractional: tuple[float, float, float, float] | None = None,
        *,
        full_page_words: Sequence[PageWord] | None = None,
    ) -> list[GroundingHit]:
        words = self._full_page_words(full_page_image, full_page_words)
        hits: list[GroundingHit] = []
        hits.extend(
            _find_text_occurrences(
                label=exemplar_label,
                words=words,
                exclude_region=exclude_region_fractional,
            )
        )
        hits.extend(
            _template_match_occurrences(
                full_page_image=full_page_image,
                exemplar_crop=exemplar_crop,
                exemplar_label=exemplar_label,
                exclude_region=exclude_region_fractional,
                threshold=self.template_threshold,
            )
        )

        merged: list[GroundingHit] = []
        for hit in hits:
            if hit.confidence < self.min_confidence:
                continue
            if _mostly_inside_exclude(hit.page_fractional_bbox, exclude_region_fractional):
                continue
            merged.append(hit)
        return _dedupe_hits(merged)


def _dedupe_hits(hits: list[GroundingHit]) -> list[GroundingHit]:
    """Drop near-duplicate boxes, keeping higher confidence."""
    ordered = sorted(hits, key=lambda h: -h.confidence)
    kept: list[GroundingHit] = []
    for hit in ordered:
        if any(
            _bbox_intersection_area(hit.page_fractional_bbox, k.page_fractional_bbox)
            / max(_bbox_area(hit.page_fractional_bbox), 1e-9)
            > 0.6
            for k in kept
        ):
            continue
        kept.append(hit)
    return kept


def run_grounding_for_legend_entries(
    *,
    full_page_image: Image.Image,
    entries: Sequence[LegendIconEntry],
    provider: GroundingProvider,
    full_page_words: Sequence[PageWord] | None = None,
) -> dict[str, list[GroundingHit]]:
    results: dict[str, list[GroundingHit]] = {}
    for entry in entries:
        exemplar = Image.open(entry.icon_crop_path)
        try:
            hits = provider.find_occurrences(
                full_page_image=full_page_image,
                exemplar_crop=exemplar,
                exemplar_label=entry.label_text,
                exclude_region_fractional=entry.icon_fractional_bbox,
                full_page_words=full_page_words,
            )
        finally:
            exemplar.close()
        results[entry.label_text] = hits
    return results


def _fractional_bbox_from_manifest(value: Any, *, field: str) -> tuple[float, float, float, float]:
    if isinstance(value, dict):
        return (
            float(value["x0"]),
            float(value["y0"]),
            float(value["x1"]),
            float(value["y1"]),
        )
    if isinstance(value, (list, tuple)) and len(value) == 4:
        a, b, c, d = value
        return (float(a), float(b), float(c), float(d))
    raise ValueError(f"{field} must be a bbox dict or a 4-element sequence")


def manifest_entry_to_legend_icon(entry: dict[str, Any]) -> LegendIconEntry:
    """Load ``LegendIconEntry`` from ``legend_manifest.json`` row."""
    exclude = entry.get("icon_fractional_bbox") or entry.get("page_fractional_bbox")
    if exclude is None:
        raise KeyError("manifest entry missing icon_fractional_bbox")
    exclude_tuple = _fractional_bbox_from_manifest(exclude, field="icon_fractional_bbox")

    label_bbox_raw = entry.get("label_fractional_bbox")
    if label_bbox_raw is None:
        label_bbox = exclude_tuple
    else:
        label_bbox = _fractional_bbox_from_manifest(
            label_bbox_raw,
            field="label_fractional_bbox",
        )

    return LegendIconEntry(
        row_id=int(entry.get("row_id", entry.get("index", 0))),
        label_text=str(entry["label_text"]),
        icon_crop_path=str(entry["icon_crop_path"]),
        icon_fractional_bbox=clamp_fractional_bbox(exclude_tuple),
        label_fractional_bbox=clamp_fractional_bbox(label_bbox),
        source=cast(LegendIconSource, entry.get("source", "indexed_tokens")),
    )
