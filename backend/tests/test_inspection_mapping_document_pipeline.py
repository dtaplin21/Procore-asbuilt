"""
End-to-end test of the full document pipeline:
extract_document -> extract_positioned_terms -> resolve_locations_per_term
-> DrawingOverlayRecord, as wired together in
inspection_mapping.map_document_to_overlays.

Matching is on INSPECTION TYPE + LOCATION TERM, not sheet identifiers —
master drawings in this system aren't expected to carry sheet-numbering
metadata, so sheet identifiers are not used to resolve a location.

Uses the same monkeypatch approach as test_document_text_extraction.py to
fake the OCR/PDF-text-layer backends deterministically.
"""

from __future__ import annotations

import pytest

from ai.pipelines import document_text_extraction as dte
from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)
from ai.pipelines.drawing_location_resolver import MasterRegion, RegistrationTransform
from ai.pipelines.inspection_mapping import DocumentEvidenceInput, map_document_to_overlays


def _word(text: str, x: float, page_index: int = 0, y: float = 100) -> PositionedWord:
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=x, y=y, width=10 * len(text), height=14, page_width=1000, page_height=1000
        ),
        page_index=page_index,
    )


def _layout(
    words: list[str],
    start_x: float = 0,
    gap: float = 5,
    page_index: int = 0,
    y: float = 100,
) -> list[PositionedWord]:
    out: list[PositionedWord] = []
    x = start_x
    for w in words:
        out.append(_word(w, x, page_index=page_index, y=y))
        x += 10 * len(w) + gap
    return out


def _region(
    region_id: str,
    inspection_types: tuple[str, ...] = (),
    location_labels: tuple[str, ...] = (),
    x=0,
    y=0,
    w=200,
    h=200,
) -> MasterRegion:
    return MasterRegion(
        region_id=region_id,
        master_drawing_id="master_1",
        inspection_types=inspection_types,
        location_labels=location_labels,
        bbox_on_master=BoundingBox(
            x=x, y=y, width=w, height=h, page_width=1000, page_height=1000
        ),
    )


class TestReferenceLookupPipeline:
    """Case B: typed inspection report naming type + location by reference."""

    def test_pdf_report_resolves_via_type_and_location(self, monkeypatch: pytest.MonkeyPatch) -> None:
        words = _layout(
            [
                "Underground",
                "Fire",
                "Water",
                "Rough",
                "In",
                "at",
                "Utility",
                "MR",
                "Status",
                "Rejected",
                "Repair",
                "required",
            ]
        )
        fake_doc = ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF, page_count=1, words=words
        )
        monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
        monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)

        region = _region(
            "region_a",
            inspection_types=("Underground Fire Water Rough In",),
            location_labels=("Utility MR",),
        )
        evidence = DocumentEvidenceInput(
            evidence_id="ev1",
            inspection_run_id="run1",
            master_drawing_id="master_1",
            file_path="report.pdf",
            region_index=[region],
        )

        overlays, unresolved = map_document_to_overlays(evidence)

        assert unresolved == []
        assert len(overlays) == 1
        overlay = overlays[0]
        assert overlay.drawing_id == "master_1"
        assert overlay.bbox == region.bbox_on_master.to_fractional()
        assert "Rejected" in overlay.tags.inspection_statuses
        assert "Repair" in overlay.tags.field_conditions
        assert overlay.severity == "high"
        assert "Underground Fire Water Rough In" in overlay.label
        assert "Utility MR" in overlay.label

    def test_location_only_still_resolves_when_type_is_absent_or_unmatched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        words = _layout(["Status", "update", "for", "Mechanical", "Room", "Passed"])
        fake_doc = ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF, page_count=1, words=words
        )
        monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
        monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)

        region = _region("region_b", location_labels=("Mechanical Room",))
        evidence = DocumentEvidenceInput(
            evidence_id="ev_loc_only",
            inspection_run_id="run1",
            master_drawing_id="master_1",
            file_path="report.pdf",
            region_index=[region],
        )

        overlays, unresolved = map_document_to_overlays(evidence)
        assert unresolved == []
        assert len(overlays) == 1
        assert overlays[0].bbox == region.bbox_on_master.to_fractional()

    def test_unmatched_type_and_location_reports_unresolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        words = _layout(["Final", "inspection", "at", "Roof"])
        fake_doc = ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF, page_count=1, words=words
        )
        monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
        monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)

        region = _region(
            "region_a", inspection_types=("Flush",), location_labels=("Yard",)
        )
        evidence = DocumentEvidenceInput(
            evidence_id="ev2",
            inspection_run_id="run1",
            master_drawing_id="master_1",
            file_path="report.pdf",
            region_index=[region],
        )

        overlays, unresolved = map_document_to_overlays(evidence)
        assert overlays == []
        assert len(unresolved) == 1
        assert "Final" in unresolved[0].reason or "Roof" in unresolved[0].reason

    def test_sheet_identifier_in_text_is_ignored_for_matching(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        words = _layout(
            ["Final", "inspection", "Mechanical", "Room", "Sheet", "Z9.99", "Passed"]
        )
        fake_doc = ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF, page_count=1, words=words
        )
        monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
        monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)

        region = _region(
            "region_a",
            inspection_types=("Final",),
            location_labels=("Mechanical Room",),
        )
        evidence = DocumentEvidenceInput(
            evidence_id="ev_sheet_irrelevant",
            inspection_run_id="run1",
            master_drawing_id="master_1",
            file_path="report.pdf",
            region_index=[region],
        )

        overlays, unresolved = map_document_to_overlays(evidence)
        assert unresolved == []
        assert len(overlays) == 1
        assert overlays[0].bbox == region.bbox_on_master.to_fractional()


class TestAlignmentPipeline:
    """Case A: photo of a marked-up region with successful visual registration."""

    def test_photo_resolves_via_alignment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        words = _layout(["Hydrostatic", "Test", "Passed"], y=200)
        monkeypatch.setattr(
            dte, "_ocr_image", lambda p, page_index=0: (words, 1000, 1000)
        )

        identity = RegistrationTransform(
            scale_x=1.0, scale_y=1.0, translate_x=0.0, translate_y=0.0
        )
        evidence = DocumentEvidenceInput(
            evidence_id="ev3",
            inspection_run_id="run2",
            master_drawing_id="master_1",
            file_path="site_photo.jpg",
            region_index=[],
            registration_transform=identity,
        )

        overlays, unresolved = map_document_to_overlays(evidence)
        assert unresolved == []
        assert len(overlays) == 1
        overlay = overlays[0]
        assert "Passed" in overlay.tags.inspection_statuses
        assert overlay.severity == "info"
        assert overlay.bbox is not None


class TestNoVocabularyFound:
    def test_document_with_no_recognizable_terms_is_unresolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        words = _layout(["the", "quick", "brown", "fox"])
        fake_doc = ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF, page_count=1, words=words
        )
        monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
        monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)

        evidence = DocumentEvidenceInput(
            evidence_id="ev4",
            inspection_run_id="run1",
            master_drawing_id="master_1",
            file_path="irrelevant.pdf",
        )
        overlays, unresolved = map_document_to_overlays(evidence)
        assert overlays == []
        assert len(unresolved) == 1
        assert unresolved[0].extracted_terms == []
