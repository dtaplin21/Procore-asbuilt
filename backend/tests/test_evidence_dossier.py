"""Tests for evidence dossier assembly (PR-A A-2)."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy.orm import Session

from ai.agents.evidence_dossier import EvidenceDossier, build_evidence_dossier
from ai.pipelines.drawing_location_resolver import MasterRegion
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.models import Drawing, EvidenceDrawingLink, EvidenceRecord
from scripts.seed_legend_reference import seed
from services.storage import StorageService


def _unique() -> str:
    return uuid.uuid4().hex[:12]


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
