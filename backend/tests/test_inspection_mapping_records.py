"""Tests for illustrative overlay mapping entry points."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

from datetime import datetime, timezone

import pytest

from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)
from ai.pipelines.drawing_location_resolver import MasterRegion
from ai.pipelines.inspection_mapping import (
    DocumentEvidenceInput,
    EvidenceInput,
    map_document_to_overlays,
    map_evidence_to_overlay,
    normalize_evidence_text,
)
from ai.pipelines.positioned_term_extractor import PositionedTerm
from ai.pipelines.term_extractor import ExtractedTerm
from services.inspection_vocabulary import VocabCategory


def test_normalize_evidence_text_buckets_categories() -> None:
    tags = normalize_evidence_text("Rough-In Passed in Utility MR per Sheet U1.C4.31")

    assert "Rough In" in tags.inspection_types
    assert "Passed" in tags.inspection_statuses
    assert "Utility MR" in tags.locations
    assert tags.confidence_label in (
        "High Confidence",
        "Medium Confidence",
        "Low Confidence",
    )


def test_map_evidence_to_overlay_builds_record() -> None:
    overlay = map_evidence_to_overlay(
        EvidenceInput(
            evidence_id="ev-1",
            inspection_run_id="run-1",
            drawing_id="dwg-1",
            note_text="Fire Protection Failed in Mechanical Room",
            bbox=(0.1, 0.2, 0.3, 0.4),
        )
    )

    assert overlay.id == "overlay_ev-1"
    assert overlay.bbox == (0.1, 0.2, 0.3, 0.4)
    assert overlay.severity == "high"
    assert "Mechanical Room" in overlay.label


def test_drawing_overlay_record_to_dict() -> None:
    uploaded = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
    overlay = map_evidence_to_overlay(
        EvidenceInput(
            evidence_id="ev-2",
            inspection_run_id="run-2",
            drawing_id="dwg-2",
            note_text="Approved in Roof Area on 03/10/2026",
            bbox=(0.0, 0.0, 0.1, 0.1),
        )
    )
    overlay.uploaded_at = uploaded
    payload = overlay.to_dict()
    assert payload["drawingId"] == "dwg-2"
    assert payload["uploadedAt"] == uploaded.isoformat()
    assert payload["regionId"] is None


def _positioned_term(
    canonical: str,
    category: VocabCategory,
    x: float = 10.0,
    page_index: int = 0,
) -> PositionedTerm:
    bbox = BoundingBox(x=x, y=20.0, width=40.0, height=12.0, page_width=612.0, page_height=792.0)
    return PositionedTerm(
        term=ExtractedTerm(
            category=category,
            canonical=canonical,
            matched_text=canonical,
            start=0,
            end=len(canonical),
            confidence_score=0.9,
            confidence_label="High Confidence",
        ),
        page_index=page_index,
        bbox=bbox,
    )


def _master_region(
    region_id: str,
    frac: tuple[float, float, float, float],
    *,
    inspection_types: tuple[str, ...] = (),
    location_labels: tuple[str, ...] = (),
) -> MasterRegion:
    x0, y0, x1, y1 = frac
    page_w, page_h = 612.0, 792.0
    return MasterRegion(
        region_id=region_id,
        master_drawing_id="dwg-1",
        inspection_types=inspection_types,
        location_labels=location_labels,
        bbox_on_master=BoundingBox(
            x=x0 * page_w,
            y=y0 * page_h,
            width=(x1 - x0) * page_w,
            height=(y1 - y0) * page_h,
            page_width=page_w,
            page_height=page_h,
        ),
    )


@pytest.fixture
def fake_document_pipeline() -> Iterator[None]:
    document = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=[
            PositionedWord(
                text="Sheet",
                bbox=BoundingBox(10, 20, 40, 12, 612, 792),
                page_index=0,
            ),
            PositionedWord(
                text="U1.C4.31",
                bbox=BoundingBox(60, 20, 50, 12, 612, 792),
                page_index=0,
            ),
        ],
    )
    positioned = [
        _positioned_term("Rough In", VocabCategory.INSPECTION_TYPE, x=10.0),
        _positioned_term("Utility MR", VocabCategory.LOCATION_TERM, x=60.0),
    ]
    with (
        patch(
            "ai.pipelines.inspection_mapping.extract_document",
            return_value=document,
        ),
        patch(
            "ai.pipelines.inspection_mapping.extract_positioned_terms",
            return_value=positioned,
        ),
    ):
        yield


def test_map_document_to_overlays_reference_lookup(fake_document_pipeline: None) -> None:
    overlays, unresolved = map_document_to_overlays(
        DocumentEvidenceInput(
            evidence_id="ev-doc-1",
            inspection_run_id="run-1",
            master_drawing_id="dwg-1",
            file_path="/evidence/native-report.pdf",
            region_index=[
                _master_region(
                    "zone-a",
                    (0.1, 0.2, 0.4, 0.5),
                    location_labels=("Utility MR",),
                    inspection_types=("Rough In",),
                )
            ],
        )
    )

    assert len(overlays) == 1
    assert overlays[0].bbox == (0.1, 0.2, 0.4, 0.5)
    assert unresolved == []


def test_map_document_to_overlays_unresolved_when_no_terms() -> None:
    with patch(
        "ai.pipelines.inspection_mapping.extract_positioned_terms",
        return_value=[],
    ), patch(
        "ai.pipelines.inspection_mapping.extract_document",
        return_value=ExtractedDocument(SourceFormat.IMAGE, 1, []),
    ):
        overlays, unresolved = map_document_to_overlays(
            DocumentEvidenceInput(
                evidence_id="ev-empty",
                inspection_run_id="run-1",
                master_drawing_id="dwg-1",
                file_path="/evidence/blank.png",
            )
        )

    assert overlays == []
    assert len(unresolved) == 1
    assert "No controlled-vocabulary terms" in unresolved[0].reason
