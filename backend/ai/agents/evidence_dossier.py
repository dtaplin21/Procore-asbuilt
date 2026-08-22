"""Structured case file the Inspection Location Agent consumes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.candidate_tile_selector import CandidateTile, find_candidate_tiles_from_clues
from ai.pipelines.clue_expander import expand_clue_value
from ai.pipelines.drawing_location_resolver import MasterRegion
from ai.pipelines.evidence_kind_classifier import EvidenceKind, classify_evidence_kind
from ai.pipelines.location_match_orchestrator import _load_scoped_survey_points
from ai.pipelines.survey_point_extractor import SurveyPointRecord
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.models import Drawing, EvidenceDrawingLink, EvidenceRecord
from services.evidence_linking import load_linked_drawings
from services.evidence_text import build_full_evidence_text
from services.file_storage import resolve_stored_file_path
from services.legend_lookup import find_codes_for_term
from services.match_candidate_scope import build_match_scope
from services.region_index_loader import build_region_index

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
_LINKED_CONTENT_SECTION = re.compile(
    r"(?:^|\n)--- Linked content[^\n]*---\n.*?(?=(?:\n--- Linked content)|(?=\Z))",
    re.DOTALL,
)
_TEXT_PREVIEW_CHARS = 500


@dataclass(frozen=True)
class ExpandedClue:
    original_value: str
    clue_type: str
    expanded_values: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class LinkedAttachmentSummary:
    url: str
    filename: str
    page_count: int
    text_preview: str
    drawing_id: int | None = None  # auxiliary Drawing.id if registered


@dataclass(frozen=True)
class MasterDrawingContext:
    master_drawing_id: int
    regions: tuple[MasterRegion, ...]
    total_region_count: int
    untagged_region_count: int
    scoped_survey_points: tuple[SurveyPointRecord, ...]
    candidate_tiles: tuple[CandidateTile, ...]
    legend_codes_near_candidates: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceDossier:
    evidence_id: int
    project_id: int
    master_drawing_id: int
    evidence: EvidenceRecord
    extraction: DocumentExtraction | None
    clues: tuple[DocumentClue, ...]
    expanded_clues: tuple[ExpandedClue, ...]
    evidence_text: str
    base_text: str
    evidence_kind: EvidenceKind
    linked_attachments: tuple[LinkedAttachmentSummary, ...]
    auxiliary_drawings: tuple[Drawing, ...]
    photo_paths: tuple[Path, ...]
    survey_points_meta: tuple[dict[str, Any], ...]
    master_context: MasterDrawingContext
    investigation_meta: dict[str, Any] = field(default_factory=dict)


def build_evidence_dossier(
    session: Session,
    *,
    evidence_id: int,
    master_drawing_id: int,
    page: int = 1,
) -> EvidenceDossier:
    """Assemble the case file for the Inspection Location Agent."""
    evidence = session.get(EvidenceRecord, evidence_id)
    if evidence is None:
        raise ValueError(f"Evidence {evidence_id} not found")

    project_id = cast(int, evidence.project_id)
    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})

    extraction, clues = _load_extraction_and_clues(session, evidence_id)
    evidence_text = build_full_evidence_text(evidence)
    base_text = _base_text_from_full(evidence_text)
    evidence_kind = _resolve_evidence_kind(session, evidence, extraction, meta)

    expanded_clues = tuple(
        ExpandedClue(
            original_value=str(clue.clue_value),
            clue_type=str(clue.clue_type),
            expanded_values=tuple(
                expand_clue_value(
                    str(clue.clue_value),
                    session=session,
                    project_id=project_id,
                )
            ),
            confidence=float(cast(float | None, clue.confidence) or 0.0),
        )
        for clue in clues
    )

    scope = build_match_scope(
        session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )
    auxiliary_drawings = tuple(load_linked_drawings(session, evidence_id))
    linked_attachments = _linked_attachments(
        session,
        evidence=evidence,
        meta=meta,
        auxiliary_drawings=auxiliary_drawings,
    )
    pdf_investigation_meta: dict[str, Any] = {}
    investigated_attachments, pdf_investigation_meta = _pdf_investigation_for_evidence(evidence)
    linked_attachments = _merge_linked_attachment_summaries(
        linked_attachments,
        investigated_attachments,
    )

    region_index = build_region_index(session, master_drawing_id)
    drawing_ids = (master_drawing_id, *scope.auxiliary_drawing_ids)
    scoped_rows = _load_scoped_survey_points(session, drawing_ids)
    scoped_survey_points = tuple(_scoped_to_survey_record(point) for point in scoped_rows)

    candidate_tiles = tuple(
        find_candidate_tiles_from_clues(
            session,
            drawing_id=master_drawing_id,
            page=page,
            clues=clues,
            project_id=project_id,
        )
    )
    legend_codes = _legend_codes_near_candidates(
        session,
        project_id=project_id,
        expanded_clues=expanded_clues,
        tiles=candidate_tiles,
    )

    master_context = MasterDrawingContext(
        master_drawing_id=master_drawing_id,
        regions=tuple(region_index.regions),
        total_region_count=region_index.total_region_count,
        untagged_region_count=region_index.untagged_region_count,
        scoped_survey_points=scoped_survey_points,
        candidate_tiles=candidate_tiles,
        legend_codes_near_candidates=legend_codes,
    )

    investigation_meta: dict[str, Any] = {
        # Sheet refs list linked/auxiliary drawings only — never master placement keys.
        "sheet_refs": list(scope.sheet_refs),
        "auxiliary_drawing_ids": list(scope.auxiliary_drawing_ids),
        "preferred_pages": list(scope.preferred_pages),
        "pdfLinkFollow": meta.get("pdfLinkFollow"),
        **pdf_investigation_meta,
    }

    return EvidenceDossier(
        evidence_id=evidence_id,
        project_id=project_id,
        master_drawing_id=master_drawing_id,
        evidence=evidence,
        extraction=extraction,
        clues=tuple(clues),
        expanded_clues=expanded_clues,
        evidence_text=evidence_text,
        base_text=base_text,
        evidence_kind=evidence_kind,
        linked_attachments=linked_attachments,
        auxiliary_drawings=auxiliary_drawings,
        photo_paths=_photo_paths(evidence, evidence_kind),
        survey_points_meta=_survey_points_meta(meta),
        master_context=master_context,
        investigation_meta=investigation_meta,
    )


def _load_extraction_and_clues(
    session: Session,
    evidence_id: int,
) -> tuple[DocumentExtraction | None, list[DocumentClue]]:
    extraction = (
        session.query(DocumentExtraction)
        .filter_by(file_id=str(evidence_id))
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )
    if extraction is None:
        return None, []
    clues = (
        session.query(DocumentClue)
        .filter_by(document_extraction_id=extraction.id)
        .order_by(DocumentClue.id.asc())
        .all()
    )
    return extraction, clues


def _resolve_evidence_kind(
    session: Session,
    evidence: EvidenceRecord,
    extraction: DocumentExtraction | None,
    meta: dict[str, Any],
) -> EvidenceKind:
    raw_kind = meta.get("evidence_kind")
    if isinstance(raw_kind, str):
        try:
            return EvidenceKind(raw_kind)
        except ValueError:
            pass

    document_type = str(getattr(extraction, "document_type", "") or "unknown")
    return classify_evidence_kind(
        document_type,
        has_linked_sheet=bool(load_linked_drawings(session, cast(int, evidence.id))),
        native_page1_words=0,
    )


def _base_text_from_full(full: str) -> str:
    if "--- Linked content" not in full:
        return full
    stripped = _LINKED_CONTENT_SECTION.sub("", full).strip()
    return stripped or full


def _survey_points_meta(meta: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    raw = meta.get("survey_points")
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, dict))


def _scoped_to_survey_record(point: Any) -> SurveyPointRecord:
    return SurveyPointRecord(
        page=int(point.page),
        northing=float(point.northing),
        easting=float(point.easting),
        station=cast(str | None, point.station),
        structure_label=cast(str | None, point.structure_label),
        label_bbox_json=dict(point.label_bbox_json),
        northing_bbox_json=None,
        easting_bbox_json=None,
        ocr_confidence=float(point.ocr_confidence),
        meta_json={"drawing_id": int(point.drawing_id)},
    )


def _linked_attachments(
    session: Session,
    *,
    evidence: EvidenceRecord,
    meta: dict[str, Any],
    auxiliary_drawings: tuple[Drawing, ...],
) -> tuple[LinkedAttachmentSummary, ...]:
    """Summaries from pdfLinkFollow meta + EvidenceDrawingLink / aux drawings.

    Sheet numbers may appear in filenames / matched_text for listing only.
    """
    by_drawing: dict[int, LinkedAttachmentSummary] = {}

    for drawing in auxiliary_drawings:
        drawing_id = cast(int, drawing.id)
        by_drawing[drawing_id] = LinkedAttachmentSummary(
            url="",
            filename=str(drawing.name or drawing.original_filename or f"drawing-{drawing_id}"),
            page_count=0,
            text_preview="",
            drawing_id=drawing_id,
        )

    links = (
        session.query(EvidenceDrawingLink)
        .filter(EvidenceDrawingLink.evidence_id == evidence.id)
        .order_by(EvidenceDrawingLink.id.asc())
        .all()
    )
    for link in links:
        drawing_id = cast(int, link.drawing_id)
        drawing = session.get(Drawing, drawing_id)
        filename = (
            str(drawing.name or drawing.original_filename)
            if drawing is not None
            else str(link.matched_text or f"drawing-{drawing_id}")
        )
        preview = str(link.matched_text or "")[:_TEXT_PREVIEW_CHARS]
        existing = by_drawing.get(drawing_id)
        if existing is None:
            by_drawing[drawing_id] = LinkedAttachmentSummary(
                url="",
                filename=filename,
                page_count=0,
                text_preview=preview,
                drawing_id=drawing_id,
            )
        elif preview and not existing.text_preview:
            by_drawing[drawing_id] = LinkedAttachmentSummary(
                url=existing.url,
                filename=existing.filename or filename,
                page_count=existing.page_count,
                text_preview=preview,
                drawing_id=drawing_id,
            )

    # pdfLinkFollow is summary-only today; surface it via empty placeholders when present.
    follow = meta.get("pdfLinkFollow")
    extras: list[LinkedAttachmentSummary] = []
    if isinstance(follow, dict) and follow.get("followed") and not by_drawing:
        extras.append(
            LinkedAttachmentSummary(
                url="",
                filename="pdf-link-follow",
                page_count=0,
                text_preview=f"followed={follow.get('followed')} skipped={follow.get('skipped')}",
                drawing_id=None,
            )
        )

    return tuple(by_drawing.values()) + tuple(extras)


def _attachment_summary_key(summary: LinkedAttachmentSummary) -> str:
    if summary.drawing_id is not None:
        return f"drawing:{summary.drawing_id}"
    return summary.url or summary.filename


def _merge_linked_attachment_summaries(
    base: tuple[LinkedAttachmentSummary, ...],
    investigated: tuple[LinkedAttachmentSummary, ...],
) -> tuple[LinkedAttachmentSummary, ...]:
    """Merge DB/link summaries with PDF investigation results."""
    merged: dict[str, LinkedAttachmentSummary] = {
        _attachment_summary_key(item): item for item in base
    }

    for item in investigated:
        key = _attachment_summary_key(item)
        existing = merged.get(key)
        if existing is None:
            merged[key] = item
            continue
        preview = item.text_preview or existing.text_preview
        merged[key] = LinkedAttachmentSummary(
            url=item.url or existing.url,
            filename=item.filename or existing.filename,
            page_count=item.page_count or existing.page_count,
            text_preview=preview,
            drawing_id=existing.drawing_id or item.drawing_id,
        )

    return tuple(merged.values())


def _pdf_investigation_for_evidence(
    evidence: EvidenceRecord,
) -> tuple[tuple[LinkedAttachmentSummary, ...], dict[str, Any]]:
    """Run PDF link investigation when the evidence file is a PDF."""
    empty_meta: dict[str, Any] = {
        "links_followed": 0,
        "pages_rendered": 0,
        "ocr_word_counts": {},
        "pdf_investigation_errors": [],
    }

    storage_key = cast(str | None, evidence.storage_key)
    if not storage_key:
        return (), empty_meta

    file_path = resolve_stored_file_path(storage_key)
    if file_path is None or file_path.suffix.lower() != ".pdf":
        return (), empty_meta

    try:
        from ai.agents.tools.pdf_investigation import run_pdf_investigation

        result = run_pdf_investigation(file_path)
    except Exception as exc:
        logger.exception(
            "evidence_dossier_pdf_investigation_failed",
            extra={"evidence_id": evidence.id, "file_path": str(file_path)},
        )
        return (), {
            **empty_meta,
            "pdf_investigation_errors": [str(exc)],
        }

    return result.summaries, {
        "links_followed": result.links_followed,
        "pages_rendered": result.pages_rendered,
        "ocr_word_counts": dict(result.ocr_word_counts),
        "pdf_investigation_errors": list(result.errors),
    }


def _photo_paths(evidence: EvidenceRecord, kind: EvidenceKind) -> tuple[Path, ...]:
    if kind != EvidenceKind.PHOTO:
        return ()
    storage_key = cast(str | None, evidence.storage_key)
    if not storage_key:
        return ()
    path = resolve_stored_file_path(storage_key)
    if path is None or path.suffix.lower() not in _IMAGE_EXTENSIONS:
        return ()
    return (path,)


def _legend_codes_near_candidates(
    session: Session,
    *,
    project_id: int,
    expanded_clues: tuple[ExpandedClue, ...],
    tiles: tuple[CandidateTile, ...],
) -> tuple[str, ...]:
    codes: list[str] = []
    seen: set[str] = set()

    for clue in expanded_clues:
        for term in (clue.original_value, *clue.expanded_values):
            for code in find_codes_for_term(session, term, project_id):
                key = code.upper()
                if key not in seen:
                    seen.add(key)
                    codes.append(code)

    tile_haystack = " ".join(tile.text for tile in tiles).upper()
    if tile_haystack:
        codes = [code for code in codes if code.upper() in tile_haystack] or codes

    return tuple(codes)
