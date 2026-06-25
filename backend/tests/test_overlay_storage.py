"""Tests for services.overlay_storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.inspection_mapping import (
    DrawingOverlayRecord,
    EvidenceInput,
    NormalizedEvidenceTags,
    UnresolvedEvidenceRecord,
    map_evidence_to_overlay,
)
from ai.pipelines.positioned_term_extractor import PositionedTerm
from ai.pipelines.term_extractor import ConfidenceLabel, ExtractedTerm
from models.models import Drawing, DrawingOverlay, EvidenceRecord, UnresolvedEvidence
from services.inspection_vocabulary import VocabCategory
from services.overlay_storage import (
    create_drawing_overlay,
    create_drawing_overlays,
    flag_unresolved_evidence,
    list_unresolved_evidence,
)
from services.storage import StorageService


def _drawing_overlay_record(
    *,
    record_id: str,
    drawing_id: str,
    inspection_run_id: str,
    bbox: tuple[float, float, float, float] | None,
    label: str,
    severity: str,
    tags: NormalizedEvidenceTags,
    created_at: datetime,
) -> DrawingOverlayRecord:
    return DrawingOverlayRecord(  # type: ignore[call-arg]
        id=record_id,
        drawing_id=drawing_id,
        inspection_run_id=inspection_run_id,
        bbox=bbox,
        label=label,
        severity=severity,
        tags=tags,
        created_at=created_at,
    )


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

    tags = NormalizedEvidenceTags()
    tags.inspection_statuses = ["Rejected"]
    record = _drawing_overlay_record(
        record_id="overlay_ev1_region_1",
        drawing_id=str(master_drawing.id),
        inspection_run_id=str(run.id),
        bbox=(0.1, 0.2, 0.4, 0.5),
        label="Rough In — Utility MR",
        severity="high",
        tags=tags,
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

    flag_unresolved_evidence(db_session, unresolved)

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


def test_create_drawing_overlay_raises_without_bbox(
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
    record = map_evidence_to_overlay(
        EvidenceInput(
            evidence_id="unresolved",
            inspection_run_id=str(run.id),
            drawing_id=str(master_drawing.id),
            note_text="",
            bbox=None,
        )
    )
    with pytest.raises(ValueError, match="no bbox"):
        create_drawing_overlay(db_session, record)


def test_list_unresolved_evidence_excludes_resolved_by_default(
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
    flag_unresolved_evidence(
        db_session,
        [
            UnresolvedEvidenceRecord(
                evidence_id=str(evidence.id),
                inspection_run_id=str(run.id),
                master_drawing_id=str(master_drawing.id),
                reason="Needs review",
                extracted_terms=[_positioned("Roof", VocabCategory.LOCATION_TERM)],
            )
        ],
    )

    open_items = list_unresolved_evidence(db_session, cast(int, master_drawing.id))
    assert len(open_items) == 1

    setattr(open_items[0], "resolved_by_human", True)
    db_session.commit()

    assert list_unresolved_evidence(db_session, cast(int, master_drawing.id)) == []
    assert len(
        list_unresolved_evidence(
            db_session,
            cast(int, master_drawing.id),
            include_resolved=True,
        )
    ) == 1
