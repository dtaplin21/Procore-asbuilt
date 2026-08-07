"""Extract survey coordinate points from uploaded evidence files."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import fitz
from sqlalchemy.orm import Session

from ai.pipelines.document_text_extraction import ExtractedDocument, PositionedWord, extract_document
from ai.pipelines.drawing_scale_parser import parse_scale_from_words
from ai.pipelines.survey_point_extractor import SurveyPointRecord, extract_survey_points_from_elements
from models.models import Drawing, EvidenceDrawingLink, EvidenceRecord


class _WordElement:
    __slots__ = ("page", "text", "bbox_json", "ocr_confidence")

    def __init__(
        self,
        *,
        page: int,
        text: str,
        bbox_json: dict[str, float],
        ocr_confidence: float,
    ) -> None:
        self.page = page
        self.text = text
        self.bbox_json = bbox_json
        self.ocr_confidence = ocr_confidence


def _word_bbox_json(word: PositionedWord) -> dict[str, float]:
    x0, y0, x1, y1 = word.bbox.to_fractional()
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def words_to_pseudo_elements(words: list[PositionedWord]) -> list[_WordElement]:
    elements: list[_WordElement] = []
    for word in words:
        text = word.text.strip()
        if not text:
            continue
        elements.append(
            _WordElement(
                page=word.page_index + 1,
                text=text,
                bbox_json=_word_bbox_json(word),
                ocr_confidence=float(word.ocr_confidence),
            )
        )
    return elements


def build_page_meta_from_path(file_path: Path, page_count: int) -> list[dict[str, Any]]:
    if file_path.suffix.lower() == ".pdf":
        doc = fitz.open(str(file_path))
        try:
            total_pages = min(doc.page_count, page_count)
            page_meta: list[dict[str, Any]] = []
            for page_index in range(total_pages):
                page = doc.load_page(page_index)
                page_meta.append(
                    {
                        "page": page_index + 1,
                        "width_pt": float(page.rect.width),
                        "height_pt": float(page.rect.height),
                        "rotation": int(page.rotation),
                    }
                )
            return page_meta
        finally:
            doc.close()

    return [{"page": 1, "width_pt": None, "height_pt": None, "rotation": 0}]


def load_linked_drawings(session: Session, evidence_id: int) -> list[Drawing]:
    links = (
        session.query(EvidenceDrawingLink)
        .filter(EvidenceDrawingLink.evidence_id == evidence_id)
        .all()
    )
    drawings: list[Drawing] = []
    seen: set[int] = set()
    for link in links:
        drawing_id = int(link.drawing_id)
        if drawing_id in seen:
            continue
        seen.add(drawing_id)
        drawing = session.get(Drawing, drawing_id)
        if drawing is not None:
            drawings.append(drawing)
    return drawings


def resolve_scale_for_evidence(
    evidence: EvidenceRecord,
    linked_drawings: list[Drawing],
    *,
    document_words: list[PositionedWord],
    page_meta_json: list[dict[str, Any]],
) -> dict[str, Any] | None:
    evidence_meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    cached = evidence_meta.get("scale_json")
    if isinstance(cached, dict) and float(cached.get("confidence", 0)) >= 0.50:
        return cached

    first_page_meta = page_meta_json[0] if page_meta_json else None
    parsed = parse_scale_from_words(
        document_words,
        page=1,
        page_meta=first_page_meta,
    )
    if parsed is not None:
        return parsed

    for drawing in linked_drawings:
        if cast(str, drawing.index_status) != "ready":
            continue
        scale_json = cast(dict[str, Any] | None, drawing.scale_json)
        if scale_json and float(scale_json.get("confidence", 0)) >= 0.50:
            return scale_json

    return None


def extract_survey_points_from_evidence(
    session: Session,
    evidence: EvidenceRecord,
    file_path: str | Path,
) -> tuple[list[SurveyPointRecord], dict[str, Any] | None]:
    """Scan the full evidence file (all pages) for paired N/E survey points."""
    path = Path(file_path)
    document: ExtractedDocument = extract_document(path)
    page_meta_json = build_page_meta_from_path(path, document.page_count)
    linked_drawings = load_linked_drawings(session, int(evidence.id))
    scale_json = resolve_scale_for_evidence(
        evidence,
        linked_drawings,
        document_words=document.words,
        page_meta_json=page_meta_json,
    )

    points = extract_survey_points_from_elements(
        words_to_pseudo_elements(document.words),
        scale_json=scale_json,
        page_meta_json=page_meta_json,
        scale_source="evidence_extract",
    )
    return points, scale_json


def persist_evidence_survey_meta(
    evidence: EvidenceRecord,
    points: list[SurveyPointRecord],
    scale_json: dict[str, Any] | None,
) -> None:
    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    meta["survey_points"] = [asdict(point) for point in points]
    if scale_json is not None:
        meta["scale_json"] = scale_json
    evidence.meta = meta  # type: ignore[assignment]
