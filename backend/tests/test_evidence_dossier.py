"""Tests for evidence dossier assembly (PR-A A-2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from ai.agents.evidence_dossier import EvidenceDossier, LinkedAttachmentSummary, build_evidence_dossier
from ai.agents.tools.master_search import expand_term_with_legend
from ai.agents.tools.pdf_investigation import PdfInvestigationResult
from ai.pipelines.pdf_link_follower import LinkFollowResult
from ai.pipelines.drawing_location_resolver import MasterRegion
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.models import Drawing, EvidenceDrawingLink, EvidenceRecord
from scripts.seed_legend_reference import seed
from services.evidence_investigation_persistence import EvidenceInvestigationPersistResult
from services.storage import StorageService


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def test_expand_term_with_legend_ss_to_sanitary_sewer(db_session: Session) -> None:
    seed(db_session, project_id=None)
    db_session.commit()

    terms = expand_term_with_legend(db_session, "SS", project_id=None)

    assert "SS" in terms
    assert "SANITARY SEWER" in terms


def test_build_evidence_dossier_expands_clues_and_loads_master_context(
    db_session: Session,
    project,
) -> None:
    seed(db_session, project_id=None)
    db_session.commit()

    storage = StorageService(db_session)
    master = Drawing(
        project_id=project.id,
        source="upload",
        name="Master.pdf",
        storage_key=f"drawings/{_unique()}.pdf",
        content_type="application/pdf",
        index_status="ready",
    )
    db_session.add(master)
    db_session.flush()

    storage.create_drawing_region(
        cast(int, master.id),
        label="Colo Parking",
        geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.08, "height": 0.09},
        inspection_type_tags=["Underground Sanitary Sewer #1"],
        location_tags=["COLO"],
    )

    aux = Drawing(
        project_id=project.id,
        source="linked_evidence",
        name="C4.20 Install.pdf",
        storage_key=f"linked/{_unique()}.pdf",
        content_type="application/pdf",
        index_status="ready",
    )
    db_session.add(aux)
    db_session.flush()

    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade="33-Sanitary Sewerage",
        spec_section=None,
        title="Inspection report",
        storage_key=f"evidence/{_unique()}.pdf",
        content_type="application/pdf",
        text_content=(
            "--- Linked content (https://example.com/C4.20.pdf) ---\n"
            "Sheet C4.20 install detail\n"
            "Underground Sanitary Sewer at COLO parking lot"
        ),
        meta={
            "evidence_kind": "form",
            "pdfLinkFollow": {"followed": 1, "skipped": 0, "errors": []},
            "survey_points": [
                {
                    "page": 1,
                    "northing": 2131764.84,
                    "easting": 6051541.82,
                    "station": "11+14.23",
                }
            ],
        },
    )
    db_session.add(
        EvidenceDrawingLink(
            project_id=cast(int, project.id),
            evidence_id=cast(int, evidence.id),
            drawing_id=cast(int, aux.id),
            link_type="sheet_ref",
            matched_text="C4.20",
            source="pdf_link",
            confidence=0.9,
        )
    )
    db_session.flush()

    extraction = DocumentExtraction(
        file_id=str(evidence.id),
        document_type="inspection_report",
        classification_confidence=0.91,
        universal_fields_json={"location_text": "COLO"},
        type_specific_fields_json={"inspection_name": "Underground Sanitary Sewer #1"},
    )
    db_session.add(extraction)
    db_session.flush()
    db_session.add_all(
        [
            DocumentClue(
                document_extraction_id=extraction.id,
                clue_type="location_text",
                clue_value="COLO",
                source="inspection_report",
                confidence=0.9,
                location_relevant=True,
            ),
            DocumentClue(
                document_extraction_id=extraction.id,
                clue_type="trade",
                clue_value="33-Sanitary Sewerage",
                source="inspection_report",
                confidence=0.85,
                location_relevant=True,
            ),
            DocumentClue(
                document_extraction_id=extraction.id,
                clue_type="abbreviation",
                clue_value="SS",
                source="inspection_report",
                confidence=0.8,
                location_relevant=True,
            ),
        ]
    )
    db_session.commit()

    dossier = build_evidence_dossier(
        db_session,
        evidence_id=cast(int, evidence.id),
        master_drawing_id=cast(int, master.id),
        page=1,
        investigate=False,
    )

    assert isinstance(dossier, EvidenceDossier)
    assert dossier.evidence_id == evidence.id
    assert dossier.master_drawing_id == master.id
    assert dossier.evidence_kind.value == "form"
    assert len(dossier.clues) == 3
    assert dossier.expanded_clues
    expanded_flat = {
        value.lower()
        for clue in dossier.expanded_clues
        for value in clue.expanded_values
    }
    assert "ss" in expanded_flat or "sanitary sewer" in expanded_flat
    assert any("colo" in value for value in expanded_flat)

    assert dossier.master_context.total_region_count >= 1
    assert dossier.master_context.regions
    assert all(isinstance(region, MasterRegion) for region in dossier.master_context.regions)
    assert dossier.master_context.candidate_tiles
    assert any("COLO" in tile.text.upper() for tile in dossier.master_context.candidate_tiles)

    assert dossier.auxiliary_drawings
    assert any(cast(int, drawing.id) == aux.id for drawing in dossier.auxiliary_drawings)
    assert dossier.linked_attachments
    assert any(att.drawing_id == aux.id for att in dossier.linked_attachments)
    assert dossier.survey_points_meta
    assert "Linked content" not in dossier.base_text or "COLO" in dossier.base_text

    # Sheet numbers may be listed for aux discovery only — never a match-key field.
    assert not hasattr(dossier, "sheet_number")
    assert not hasattr(dossier.master_context, "sheet_number")
    assert "sheet_number" not in dossier.investigation_meta
    assert "C4.20" in dossier.investigation_meta.get("sheet_refs", [])
    for region in dossier.master_context.regions:
        assert not hasattr(region, "sheet_number")
        assert not hasattr(region, "sheet_ref")


def test_build_evidence_dossier_missing_evidence_raises(
    db_session: Session,
) -> None:
    try:
        build_evidence_dossier(
            db_session,
            evidence_id=9_999_999,
            master_drawing_id=1,
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not found" in str(exc).lower()


@patch("services.evidence_investigation_persistence.persist_evidence_investigation")
@patch("ai.pipelines.pdf_link_follower.follow_pdf_links")
@patch("ai.agents.evidence_dossier.resolve_stored_file_path")
@patch("ai.agents.tools.pdf_investigation.run_pdf_investigation")
def test_build_evidence_dossier_investigates_and_persists_once(
    mock_run_pdf: MagicMock,
    mock_resolve_path: MagicMock,
    mock_follow_pdf_links: MagicMock,
    mock_persist: MagicMock,
    db_session: Session,
    project,
) -> None:
    seed(db_session, project_id=None)
    db_session.commit()

    storage = StorageService(db_session)
    master = Drawing(
        project_id=project.id,
        source="upload",
        name="Master.pdf",
        storage_key=f"drawings/{_unique()}.pdf",
        content_type="application/pdf",
        index_status="ready",
    )
    db_session.add(master)
    db_session.flush()

    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade="33-Sanitary Sewerage",
        spec_section=None,
        title="Inspection report",
        storage_key=f"evidence/{_unique()}.pdf",
        content_type="application/pdf",
        text_content="Underground Sanitary Sewer at COLO parking lot",
        meta={"evidence_kind": "form"},
    )
    db_session.commit()

    mock_resolve_path.return_value = Path("/tmp/evidence.pdf")
    payload = PdfInvestigationResult(
        link_result=LinkFollowResult(followed_count=1),
        merged_text="Location: COLO STA 10+50\nUnderground Sanitary Sewer at COLO parking lot",
        base_text="Underground Sanitary Sewer at COLO parking lot",
        summaries=(
            LinkedAttachmentSummary(
                url="https://example.com/install.pdf",
                filename="install.pdf",
                page_count=1,
                text_preview="Location: COLO STA 10+50",
                drawing_id=None,
            ),
        ),
        links_followed=1,
        pages_rendered=1,
        ocr_word_counts={"https://example.com/install.pdf": 42},
        errors=(),
    )
    mock_run_pdf.return_value = payload
    mock_persist.return_value = EvidenceInvestigationPersistResult(
        linked_drawing_ids=[501],
        extraction_id=999,
        survey_point_count=2,
        drawing_ids_needing_index=[501],
    )

    dossier = build_evidence_dossier(
        db_session,
        evidence_id=cast(int, evidence.id),
        master_drawing_id=cast(int, master.id),
        investigate=True,
    )

    mock_run_pdf.assert_called_once()
    mock_persist.assert_called_once()
    persist_kwargs = mock_persist.call_args.kwargs
    assert persist_kwargs["payload"] is payload
    assert persist_kwargs["evidence_id"] == cast(int, evidence.id)
    assert mock_follow_pdf_links.call_count <= 1

    assert dossier.investigation_meta["links_followed"] == 1
    assert dossier.investigation_meta["pages_rendered"] == 1
    assert dossier.investigation_meta["ocr_word_counts"]["https://example.com/install.pdf"] == 42
    assert any(
        att.url == "https://example.com/install.pdf"
        for att in dossier.linked_attachments
    )
    assert any(
        "COLO" in att.text_preview for att in dossier.linked_attachments
    )


@patch("services.evidence_investigation_persistence.persist_evidence_investigation")
@patch("ai.agents.tools.pdf_investigation.run_pdf_investigation")
def test_build_evidence_dossier_skips_investigation_when_cache_fresh(
    mock_run_pdf: MagicMock,
    mock_persist: MagicMock,
    db_session: Session,
    project,
) -> None:
    fresh_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    storage = StorageService(db_session)
    master = Drawing(
        project_id=project.id,
        source="upload",
        name="Master.pdf",
        storage_key=f"drawings/{_unique()}.pdf",
        content_type="application/pdf",
        index_status="ready",
    )
    db_session.add(master)
    db_session.flush()

    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title="Cached investigation",
        storage_key=f"evidence/{_unique()}.pdf",
        content_type="application/pdf",
        text_content="Cached evidence text",
        meta={
            "matchInvestigation": {
                "followed": 2,
                "skipped": 0,
                "errors": [],
                "linked_drawing_ids": [101],
                "at": fresh_at,
            }
        },
    )
    db_session.commit()

    build_evidence_dossier(
        db_session,
        evidence_id=cast(int, evidence.id),
        master_drawing_id=cast(int, master.id),
        investigate=True,
    )

    mock_run_pdf.assert_not_called()
    mock_persist.assert_not_called()


def test_build_evidence_dossier_loads_scoped_survey_points_from_indexed_auxiliary(
    db_session: Session,
    project,
) -> None:
    storage = StorageService(db_session)
    master = Drawing(
        project_id=project.id,
        source="upload",
        name="Master.pdf",
        storage_key=f"drawings/{_unique()}.pdf",
        content_type="application/pdf",
        index_status="ready",
        processing_status="ready",
    )
    db_session.add(master)
    db_session.flush()
    storage.create_drawing_region(
        cast(int, master.id),
        label="Campus",
        geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.08, "height": 0.09},
    )

    aux = Drawing(
        project_id=project.id,
        source="linked_evidence",
        name="Install.pdf",
        storage_key=f"linked/{_unique()}.pdf",
        content_type="application/pdf",
        index_status="ready",
        processing_status="ready",
        page_meta_json=[{"page": 1, "width_pt": 2592.0, "height_pt": 1728.0, "rotation": 0}],
    )
    db_session.add(aux)
    db_session.flush()
    storage.create_drawing_region(
        cast(int, aux.id),
        label="Install detail",
        geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.08, "height": 0.09},
    )

    from models.drawing_text_element import DrawingTextElement

    db_session.add_all(
        [
            DrawingTextElement(
                master_drawing_id=cast(int, aux.id),
                page=1,
                text="N 2131764.84",
                text_normalized="n 2131764.84",
                bbox_json={"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.22},
                ocr_confidence=0.95,
                source="native_pdf",
            ),
            DrawingTextElement(
                master_drawing_id=cast(int, aux.id),
                page=1,
                text="E 6051541.82",
                text_normalized="e 6051541.82",
                bbox_json={"x0": 0.12, "y0": 0.20, "x1": 0.16, "y1": 0.22},
                ocr_confidence=0.95,
                source="native_pdf",
            ),
        ]
    )

    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade="33-Sanitary Sewerage",
        spec_section=None,
        title="Inspection report",
        storage_key=f"evidence/{_unique()}.pdf",
        content_type="application/pdf",
        text_content="Underground Sanitary Sewer at COLO parking lot",
        meta={"evidence_kind": "form"},
    )
    db_session.add(
        EvidenceDrawingLink(
            project_id=cast(int, project.id),
            evidence_id=cast(int, evidence.id),
            drawing_id=cast(int, aux.id),
            link_type="sheet_ref",
            matched_text="Install",
            source="pdf_link",
            confidence=0.9,
        )
    )
    db_session.commit()

    dossier = build_evidence_dossier(
        db_session,
        evidence_id=cast(int, evidence.id),
        master_drawing_id=cast(int, master.id),
        investigate=False,
    )

    aux_key = str(aux.id)
    scoped_counts = dossier.investigation_meta.get("scoped_point_counts", {})
    assert scoped_counts.get(aux_key, 0) > 0
    assert dossier.investigation_meta.get("auxiliary_index_pending") is False
    assert any(
        point.meta_json.get("drawing_id") == cast(int, aux.id)
        for point in dossier.master_context.scoped_survey_points
    )
