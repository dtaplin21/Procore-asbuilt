"""Tests for multi-candidate location match generation (PR-C C-1)."""

from __future__ import annotations

import uuid
from typing import cast

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import (
    LocationMatchCandidate,
    _filter_off_page_candidates,
    _filter_sheet_only_candidates,
    generate_all_location_candidates,
    resolve_evidence_location,
)
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.drawing_region import DrawingRegion
from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, EvidenceRecord
from services.storage import StorageService


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def test_filter_sheet_only_candidates_drops_sheet_ref_only_support() -> None:
    sheet_only = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.7,
        bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        page=1,
        supporting_clues=("clue:C4.20",),
    )
    mixed = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.8,
        bbox_fractional=(0.2, 0.2, 0.3, 0.3),
        page=1,
        supporting_clues=("clue:C4.20", "location:COLO"),
    )
    no_clues = LocationMatchCandidate(
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=0.9,
        bbox_fractional=(0.3, 0.3, 0.4, 0.4),
        page=1,
    )

    filtered = _filter_sheet_only_candidates([sheet_only, mixed, no_clues])

    assert sheet_only not in filtered
    assert mixed in filtered
    assert no_clues in filtered


def test_filter_off_page_candidates_drops_title_block_only_bboxes() -> None:
    on_page = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.8,
        bbox_fractional=(0.2, 0.2, 0.3, 0.3),
        page=1,
        supporting_clues=("location:COLO",),
    )
    off_page = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.7,
        bbox_fractional=(0.226, 1.277, 0.241, 1.362),
        page=1,
        supporting_clues=("clue:UCSF PROJECT NUMBER",),
    )
    no_bbox = LocationMatchCandidate(
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=0.9,
        bbox_fractional=None,
        page=1,
    )

    filtered = _filter_off_page_candidates([on_page, off_page, no_bbox])

    assert on_page in filtered
    assert off_page not in filtered
    assert no_bbox in filtered


def test_generate_all_location_candidates_produces_provenance_rich_set(
    db_session,
    project,
) -> None:
    """Golden-style dossier: survey points + region tags + clue tiles → >= 3 candidates."""
    storage = StorageService(db_session)
    master = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key=f"drawings/{_unique()}.pdf",
        content_type="application/pdf",
    )
    master_id = cast(int, master.id)

    northing = 2131764.84
    easting = 6051541.82
    station = "12+50"
    label_bbox = {"x0": 0.12, "y0": 0.18, "x1": 0.18, "y1": 0.22}

    db_session.add(
        DrawingSurveyPoint(
            drawing_id=master_id,
            page=1,
            northing=northing,
            easting=easting,
            station=station,
            structure_label="SS-1",
            label_bbox_json=label_bbox,
            source="auto_index",
        )
    )
    db_session.add(
        DrawingRegion(
            master_drawing_id=master_id,
            label="Colo Parking",
            page=1,
            geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.08, "height": 0.09},
            inspection_type_tags=["Underground Sanitary Sewer #1"],
            location_tags=["COLO"],
        )
    )
    db_session.add(
        DrawingTextElement(
            master_drawing_id=master_id,
            page=1,
            text="COLO sanitary sewer",
            text_normalized="colo sanitary sewer",
            bbox_json={"x0": 0.11, "y0": 0.19, "x1": 0.17, "y1": 0.21},
            ocr_confidence=0.95,
            source="native_pdf",
        )
    )

    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade="33-Sanitary Sewerage",
        spec_section=None,
        title="Inspection report",
        storage_key=f"evidence/{_unique()}.pdf",
        content_type="application/pdf",
        text_content="Underground Sanitary Sewer at COLO parking lot STA. 12+50",
        meta={
            "survey_points": [
                {
                    "page": 1,
                    "northing": northing,
                    "easting": easting,
                    "station": station,
                    "label_bbox_json": label_bbox,
                }
            ],
        },
    )
    evidence_id = cast(int, evidence.id)

    extraction = DocumentExtraction(
        file_id=str(evidence_id),
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
                confidence=0.90,
                location_relevant=True,
            ),
            DocumentClue(
                document_extraction_id=extraction.id,
                clue_type="station",
                clue_value="STA. 12+50",
                source="inspection_report",
                confidence=0.88,
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
        ]
    )
    db_session.commit()

    candidates = generate_all_location_candidates(
        db_session,
        evidence_id=evidence_id,
        master_drawing_id=master_id,
        page=1,
    )

    with_clues = [c for c in candidates if c.supporting_clues]
    assert len(with_clues) >= 3

    methods = {c.method for c in with_clues}
    assert ResolutionMethod.COORDINATE_LOOKUP in methods
    assert ResolutionMethod.STATION_LOOKUP in methods
    assert ResolutionMethod.REFERENCE_LOOKUP in methods

    for candidate in with_clues:
        assert candidate.bbox_fractional is not None
        assert all(not clue.endswith(":C4.20") for clue in candidate.supporting_clues)


def test_resolve_evidence_location_delegates_to_generate_all(
    db_session,
    project,
) -> None:
    storage = StorageService(db_session)
    master = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key=f"drawings/{_unique()}.pdf",
        content_type="application/pdf",
    )
    master_id = cast(int, master.id)

    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="Minimal evidence",
        storage_key=f"evidence/{_unique()}.pdf",
    )
    db_session.add(evidence)
    db_session.commit()
    evidence_id = cast(int, evidence.id)

    result = resolve_evidence_location(
        db_session,
        evidence_id=evidence_id,
        master_drawing_id=master_id,
        page=1,
    )

    assert result.master_drawing_id == master_id
