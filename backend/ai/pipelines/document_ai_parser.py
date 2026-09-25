"""Map Document AI ``Document`` JSON / proto to ``PositionedWord`` tokens."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord

TOKEN_SOURCE_DOCUMENT_AI = "document_ai"


def _text_from_anchor(full_text: str, anchor: Mapping[str, Any] | None) -> str:
    if not anchor:
        return ""
    segments = anchor.get("textSegments") or anchor.get("text_segments") or []
    parts: list[str] = []
    for seg in segments:
        if not isinstance(seg, Mapping):
            continue
        start = int(seg.get("startIndex") or seg.get("start_index") or 0)
        end = int(seg.get("endIndex") or seg.get("end_index") or 0)
        parts.append(full_text[start:end])
    return "".join(parts).strip()


def _page_dimensions(page: Mapping[str, Any]) -> tuple[float, float]:
    dim = page.get("dimension") or {}
    width = float(dim.get("width") or 0.0)
    height = float(dim.get("height") or 0.0)
    if width <= 0 or height <= 0:
        width, height = 1.0, 1.0
    return width, height


def _bbox_from_normalized_poly(
    poly: Mapping[str, Any] | None,
    *,
    page_width: float,
    page_height: float,
) -> BoundingBox | None:
    if not poly:
        return None
    vertices = poly.get("normalizedVertices") or poly.get("normalized_vertices") or []
    if not vertices:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for v in vertices:
        if not isinstance(v, Mapping):
            continue
        xs.append(float(v.get("x") or 0.0))
        ys.append(float(v.get("y") or 0.0))
    if not xs or not ys:
        return None
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return BoundingBox(
        x=x0 * page_width,
        y=y0 * page_height,
        width=max(0.0, (x1 - x0) * page_width),
        height=max(0.0, (y1 - y0) * page_height),
        page_width=page_width,
        page_height=page_height,
    )


def document_payload(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Unwrap batch JSON wrappers to the inner Document dict."""
    if "pages" in data or "text" in data:
        return data
    inner = data.get("document")
    if isinstance(inner, Mapping):
        return inner
    return data


def document_ai_tokens_to_words(
    document: Mapping[str, Any],
    *,
    page_index: int,
    token_source: str = TOKEN_SOURCE_DOCUMENT_AI,
) -> list[PositionedWord]:
    """Extract tokens for one page (0-based ``page_index``)."""
    pages = document.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        return []
    page = pages[page_index]
    if not isinstance(page, Mapping):
        return []

    full_text = str(document.get("text") or "")
    page_width, page_height = _page_dimensions(page)
    words: list[PositionedWord] = []

    for token in page.get("tokens") or []:
        if not isinstance(token, Mapping):
            continue
        layout = token.get("layout")
        if not isinstance(layout, Mapping):
            continue
        confidence_raw = layout.get("confidence")
        confidence = 0.0 if confidence_raw is None else float(confidence_raw)
        anchor = layout.get("textAnchor") or layout.get("text_anchor")
        poly = layout.get("boundingPoly") or layout.get("bounding_poly")
        text = _text_from_anchor(full_text, anchor if isinstance(anchor, Mapping) else None)
        if not text:
            continue
        bbox = _bbox_from_normalized_poly(
            poly if isinstance(poly, Mapping) else None,
            page_width=page_width,
            page_height=page_height,
        )
        if bbox is None:
            continue
        words.append(
            PositionedWord(
                text=text,
                bbox=bbox,
                page_index=page_index,
                ocr_confidence=confidence,
                token_source=token_source,
            )
        )
    return words


def document_ai_document_to_words(
    document: Mapping[str, Any],
    *,
    token_source: str = TOKEN_SOURCE_DOCUMENT_AI,
) -> list[PositionedWord]:
    """All pages from a Document dict."""
    doc = document_payload(document)
    pages = doc.get("pages") or []
    words: list[PositionedWord] = []
    for page_index in range(len(pages)):
        words.extend(
            document_ai_tokens_to_words(
                doc,
                page_index=page_index,
                token_source=token_source,
            )
        )
    return words


def parse_document_json_bytes(raw: bytes) -> list[PositionedWord]:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Document AI JSON root must be an object")
    return document_ai_document_to_words(data)


def parse_document_json_file(path: str | Path) -> list[PositionedWord]:
    return parse_document_json_bytes(Path(path).read_bytes())


def words_from_proto_document(document: Any) -> list[PositionedWord]:
    """Convert a ``google.cloud.documentai.Document`` proto to words."""
    from google.protobuf.json_format import MessageToDict

    data = MessageToDict(document._pb if hasattr(document, "_pb") else document)
    return document_ai_document_to_words(data)
