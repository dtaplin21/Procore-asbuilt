"""Phase 8 — master drawing index then inspection match integration."""

from __future__ import annotations

import uuid
from typing import cast

from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.drawing_match_candidate import DrawingMatchCandidate
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, Project
from models.inspection_run import InspectionRun
from scripts.seed_legend_reference import seed
from services.drawing_index_jobs import run_drawing_index_job
from services.inspection_matching_jobs import run_inspection_match_job
from services.master_drawing_legend_tagger import enrich_text_element
from services.storage import StorageService


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def test_master_index_then_inspection_match_finds_candidates(
    db_session,
    seeded_ready_pdf_drawing: Drawing,
    project: Project,
) -> None:
    """Index master OCR/regions first, then run clue matching against text elements."""
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)

    run_drawing_index_job(drawing_id, db_session)
    db_session.commit()

    text_count = (
        db_session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .count()
    )
    assert text_count >= 1

    ss_row = DrawingTextElement(
        master_drawing_id=drawing_id,
        page=1,
        text="SS-3",
        text_normalized="ss-3",
        bbox_json={"x0": 0.10, "y0": 0.10, "x1": 0.14, "y1": 0.12},
        ocr_confidence=0.95,
        source="native_pdf",
    )
    enrich_text_element(db_session, ss_row, project_id=project_id)
    db_session.add(ss_row)
    db_session.commit()

    storage = StorageService(db_session)
    evidence = storage.create_evidence_record(
        project_id=project_id,
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title=f"Inspection {_unique()}",
        storage_key=f"evidence/{_unique()}.pdf",
        content_type="application/pdf",
    )
    evidence_id = cast(int, evidence.id)

    run = InspectionRun(
        project_id=project_id,
        master_drawing_id=drawing_id,
        evidence_id=evidence_id,
        status="complete",
    )
    db_session.add(run)
    db_session.flush()

    extraction = DocumentExtraction(
        file_id=str(evidence_id),
        document_type="inspection_report",
        classification_confidence=0.9,
    )
    db_session.add(extraction)
    db_session.flush()
    db_session.add(
        DocumentClue(
            document_extraction_id=extraction.id,
            clue_type="location_text",
            clue_value="SS-3",
            source="inspection_report",
            confidence=0.90,
            location_relevant=True,
        )
    )
    db_session.commit()

    status = run_inspection_match_job(
        {
            "inspection_id": str(evidence_id),
            "drawing_id": str(drawing_id),
            "page": 1,
            "project_id": project_id,
            "inspection_run_id": cast(int, run.id),
        },
        db_session,
    )

    assert status in ("matched", "needs_review")
    candidate = (
        db_session.query(DrawingMatchCandidate)
        .filter(DrawingMatchCandidate.inspection_id == str(evidence_id))
        .order_by(DrawingMatchCandidate.rank.asc())
        .first()
    )
    assert candidate is not None
    assert float(cast(float, candidate.score)) > 0

    indexed = db_session.get(Drawing, drawing_id)
    assert indexed is not None
    assert cast(str, indexed.index_status) == "ready"
