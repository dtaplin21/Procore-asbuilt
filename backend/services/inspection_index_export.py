"""Build a structured inventory of what was indexed for an inspection run."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.evidence_page_investigation import extract_inspection_document
from ai.pipelines.pdf_link_follower import extract_pdf_hyperlinks
from ai.pipelines.survey_point_extractor import extract_stations_from_text
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.drawing_overlay import DrawingOverlay
from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_text_element import DrawingTextElement
from models.inspection_run import InspectionRun
from models.models import Drawing, EvidenceRecord
from services.storage import storage_key_to_abs_path

_TEXT_PREVIEW_CHARS = 1200


def build_inspection_index_inventory(
    session: Session,
    *,
    project_id: int,
    run_id: int,
) -> dict[str, Any]:
    run = session.get(InspectionRun, run_id)
    if run is None or cast(int, run.project_id) != project_id:
        raise LookupError("Inspection run not found")
    if run.evidence_id is None:
        raise ValueError("Inspection run has no evidence file")

    evidence = session.get(EvidenceRecord, cast(int, run.evidence_id))
    master = session.get(Drawing, cast(int, run.master_drawing_id))
    if evidence is None:
        raise LookupError("Evidence not found")

    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    mi = meta.get("matchInvestigation") or {}

    report: dict[str, Any] = {
        "run_id": run.id,
        "project_id": project_id,
        "run": {
            "status": run.status,
            "error_message": run.error_message,
            "updated_at": str(run.updated_at),
            "completed_at": str(run.completed_at),
        },
        "evidence": {
            "id": evidence.id,
            "title": evidence.title,
            "text_content_length": len(evidence.text_content or ""),
            "station_from": meta.get("station_from"),
            "station_to": meta.get("station_to"),
            "station_range_source_drawing_id": meta.get("station_range_source_drawing_id"),
            "merged_text_length": meta.get("merged_text_length"),
            "survey_points_in_meta": meta.get("survey_points"),
        },
        "master_drawing": {
            "id": master.id if master else None,
            "name": master.name if master else None,
            "index_status": master.index_status if master else None,
            "registration_json": getattr(master, "registration_json", None) if master else None,
        },
        "match_investigation": mi,
    }

    ext = (
        session.query(DocumentExtraction)
        .filter(DocumentExtraction.file_id == str(evidence.id))
        .order_by(DocumentExtraction.id.desc())
        .first()
    )
    if ext:
        clues = (
            session.query(DocumentClue)
            .filter(DocumentClue.document_extraction_id == ext.id)
            .order_by(DocumentClue.id)
            .all()
        )
        report["document_extraction"] = {
            "id": ext.id,
            "document_type": ext.document_type,
            "universal_fields_json": ext.universal_fields_json,
            "type_specific_fields_json": ext.type_specific_fields_json,
            "clues": [
                {
                    "clue_type": c.clue_type,
                    "clue_value": c.clue_value,
                    "source": c.source,
                    "confidence": c.confidence,
                }
                for c in clues
            ],
        }

    storage_key = cast(str | None, evidence.storage_key)
    if storage_key:
        ev_path = storage_key_to_abs_path(storage_key)
        report["evidence_pdf"] = {"exists": ev_path.exists()}
        if ev_path.exists():
            doc = extract_inspection_document(ev_path)
            pages = []
            for pi in range(doc.page_count):
                text = doc.page_text(pi)
                pages.append(
                    {
                        "page": pi + 1,
                        "word_count": len([w for w in doc.words if w.page_index == pi]),
                        "char_count": len(text),
                        "stations_found": extract_stations_from_text(text),
                        "text_preview": text[:_TEXT_PREVIEW_CHARS],
                    }
                )
            report["evidence_pdf"]["page_count"] = doc.page_count
            report["evidence_pdf"]["pages"] = pages
            links = extract_pdf_hyperlinks(ev_path)
            report["evidence_pdf"]["hyperlinks"] = [
                {
                    "kind": str(link.kind),
                    "uri": (getattr(link, "uri", None) or "")[:250],
                }
                for link in links
            ]

    linked_ids = list(mi.get("linked_drawing_ids") or [])
    report["linked_drawings_indexed"] = []
    for did in linked_ids:
        drawing = session.get(Drawing, int(did))
        if drawing is None:
            continue
        text_by_page: dict[int, int] = defaultdict(int)
        for (page,) in (
            session.query(DrawingTextElement.page)
            .filter(DrawingTextElement.master_drawing_id == drawing.id)
            .all()
        ):
            text_by_page[int(page)] += 1
        survey = (
            session.query(DrawingSurveyPoint)
            .filter(DrawingSurveyPoint.drawing_id == drawing.id)
            .order_by(DrawingSurveyPoint.page, DrawingSurveyPoint.id)
            .all()
        )
        entry: dict[str, Any] = {
            "id": drawing.id,
            "name": drawing.name,
            "index_status": drawing.index_status,
            "page_count": drawing.page_count,
            "text_element_counts_by_page": dict(sorted(text_by_page.items())),
            "text_element_total": sum(text_by_page.values()),
            "survey_points": [
                {
                    "page": sp.page,
                    "station": sp.station,
                    "northing": sp.northing,
                    "easting": sp.easting,
                    "source": sp.source,
                }
                for sp in survey
            ],
        }
        report["linked_drawings_indexed"].append(entry)

    overlays = (
        session.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .all()
    )
    report["overlays"] = [
        {"id": o.id, "geometry": o.geometry, "meta": o.meta} for o in overlays
    ]
    return report
