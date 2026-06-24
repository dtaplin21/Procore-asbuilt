"""Tests for services.overlay_storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.inspection_mapping import (
    DrawingOverlayRecord,
    NormalizedEvidenceTags,
    UnresolvedEvidenceRecord,
)
from ai.pipelines.positioned_term_extractor import PositionedTerm
from ai.pipelines.term_extractor import ConfidenceLabel, ExtractedTerm
from models.models import Drawing, DrawingOverlay, EvidenceRecord, UnresolvedEvidence
from services.inspection_vocabulary import VocabCategory
from services.overlay_storage import create_drawing_overlays, flag_unresolved_evidence
from services.storage import StorageService


def _positioned(canonical: str, category: VocabCategory) -> PositionedTerm:
    from ai.pipelines.document_text_extraction import BoundingBox

    return PositionedTerm(
        term=ExtractedTerm(
            category=category,
            canonical=canonical,
            matched_text=canonical,
            start=0,
            end=len(canonical),
            confidence_score=0.9,
            confidence_label=ConfidenceLabel.HIGH,
        ),
        page_index=0,
        bbox=BoundingBox(0, 0, 10, 10, 100, 100),
    )


@pytest.fixture
def master_drawing(db_session: Session, project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)
    return drawing


def test_create_drawing_overlays_persists_geometry_and_meta(
    db_session: Session,
    project,
    master_drawing: Drawing,
) -> None:
    storage = StorageService(db_session)
    run = storage.create_inspection_run(
        project_id=cast(int, project.id),
        master_drawing_id=cast(int, master_drawing.id),
        evidence_id=None,
        inspection_type="general",
    )

    record = DrawingOverlayRecord(
        id="overlay_ev1_region_1",
        drawing_id=str(master_drawing.id),
        inspection_run_id=str(run.id),
        bbox=(0.1, 0.2, 0.4, 0.5),
        label="Rough In — Utility MR",
        severity="high",
        tags=NormalizedEvidenceTags(inspection_statuses=["Rejected"]),
        created_at=cast(datetime, run.created_at),
    )

    saved = create_drawing_overlays(db_session, [record])
    assert len(saved) == 1
    overlay = saved[0]
    geometry = cast(dict[str, Any], overlay.geometry)
    assert float(geometry["x"]) == pytest.approx(0.1)
    assert float(geometry["width"]) == pytest.approx(0.3)
    status_value = str(getattr(overlay, "status"))
    assert status_value == "fail"
    assert str(getattr(overlay, "label")) == "Rough In — Utility MR"
    assert str(getattr(overlay, "severity")) == "high"
    assert getattr(overlay, "tags_json") is not None


def test_flag_unresolved_evidence_writes_table_and_meta(
    db_session: Session,
    project,
    master_drawing: Drawing,
) -> None:
    storage = StorageService(db_session)
    run = storage.create_inspection_run(
        project_id=cast(int, project.id),
        master_drawing_id=cast(int, master_drawing.id),
        evidence_id=None,
        inspection_type="general",
    )
    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title="report.pdf",
        storage_key="projects/1/evidence/test.pdf",
        content_type="application/pdf",
    )

    unresolved = [
        UnresolvedEvidenceRecord(
            evidence_id=str(evidence.id),
            inspection_run_id=str(run.id),
            master_drawing_id=str(master_drawing.id),
            reason="No match",
            extracted_terms=[_positioned("Roof", VocabCategory.LOCATION_TERM)],
        )
    ]

    flag_unresolved_evidence(
        db_session,
        unresolved,
        evidence_id=cast(int, evidence.id),
        project_id=cast(int, project.id),
    )

    rows = (
        db_session.query(UnresolvedEvidence)
        .filter(UnresolvedEvidence.evidence_id == evidence.id)
        .all()
    )
    assert len(rows) == 1
    assert str(getattr(rows[0], "reason")) == "No match"

    db_session.refresh(evidence)
    meta = cast(dict[str, Any], evidence.meta)
    assert "documentPipelineUnresolved" in meta
