"""
backend/tests/test_drawing_location_resolver.py
"""

from __future__ import annotations

import pytest

from ai.pipelines.document_text_extraction import BoundingBox
from ai.pipelines.drawing_location_resolver import (
    MasterRegion,
    RegistrationTransform,
    ResolutionMethod,
    detect_resolution_case,
    resolve_document_location,
    resolve_locations_per_term,
)
from ai.pipelines.positioned_term_extractor import PositionedTerm
from ai.pipelines.term_extractor import ConfidenceLabel, ExtractedTerm
from services.inspection_vocabulary import VocabCategory


def _term(category: VocabCategory, canonical: str, x=0, y=0, w=100, h=20) -> PositionedTerm:
    extracted = ExtractedTerm(
        category=category,
        canonical=canonical,
        matched_text=canonical,
        start=0,
        end=len(canonical),
        confidence_score=0.95,
        confidence_label=ConfidenceLabel.HIGH,
    )
    bbox = BoundingBox(x=x, y=y, width=w, height=h, page_width=1000, page_height=1000)
    return PositionedTerm(term=extracted, page_index=0, bbox=bbox)


def _region(
    region_id: str,
    inspection_types: tuple[str, ...] = (),
    location_labels: tuple[str, ...] = (),
    x=0,
    y=0,
    w=100,
    h=100,
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


IDENTITY_TRANSFORM = RegistrationTransform(
    scale_x=1.0, scale_y=1.0, translate_x=0.0, translate_y=0.0
)


class TestCaseDetection:
    def test_no_signal_is_unresolved(self) -> None:
        result = detect_resolution_case([], has_registration_transform=False)
        assert result == ResolutionMethod.UNRESOLVED

    def test_inspection_type_with_no_registration_is_reference_lookup(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_TYPE, "Hydrostatic Test")]
        result = detect_resolution_case(terms, has_registration_transform=False)
        assert result == ResolutionMethod.REFERENCE_LOOKUP

    def test_location_term_with_no_registration_is_reference_lookup(self) -> None:
        terms = [_term(VocabCategory.LOCATION_TERM, "Mechanical Room")]
        result = detect_resolution_case(terms, has_registration_transform=False)
        assert result == ResolutionMethod.REFERENCE_LOOKUP

    def test_successful_registration_is_alignment_regardless_of_terms(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_TYPE, "Final")]
        result = detect_resolution_case(terms, has_registration_transform=True)
        assert result == ResolutionMethod.ALIGNMENT

    def test_successful_registration_with_no_terms_at_all_is_still_alignment(self) -> None:
        result = detect_resolution_case([], has_registration_transform=True)
        assert result == ResolutionMethod.ALIGNMENT


class TestAlignmentResolution:
    def test_identity_transform_preserves_fractional_position(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_STATUS, "Rejected", x=100, y=200, w=50, h=20)]
        result = resolve_document_location(
            document_terms=terms,
            master_drawing_id="master_1",
            region_index=[],
            registration_transform=IDENTITY_TRANSFORM,
        )
        assert result.method == ResolutionMethod.ALIGNMENT
        x0, y0, x1, y1 = result.bbox_fractional or (0, 0, 0, 0)
        expected_x0, expected_y0, expected_x1, expected_y1 = terms[0].bbox.to_fractional()
        assert x0 == pytest.approx(expected_x0)
        assert y0 == pytest.approx(expected_y0)
        assert x1 == pytest.approx(expected_x1)
        assert y1 == pytest.approx(expected_y1)

    def test_scaled_transform_repositions_correctly(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_STATUS, "Rejected", x=0, y=0, w=100, h=100)]
        transform = RegistrationTransform(
            scale_x=0.5, scale_y=0.5, translate_x=0.25, translate_y=0.25
        )
        result = resolve_document_location(
            document_terms=terms,
            master_drawing_id="master_1",
            region_index=[],
            registration_transform=transform,
        )
        x0, y0, x1, y1 = result.bbox_fractional or (0, 0, 0, 0)
        assert x0 == pytest.approx(0.25)
        assert y0 == pytest.approx(0.25)
        assert x1 == pytest.approx(0.30)
        assert y1 == pytest.approx(0.30)

    def test_alignment_annotates_with_overlapping_master_region(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_STATUS, "Rejected", x=0, y=0, w=100, h=100)]
        region = _region(
            "region_a",
            inspection_types=("Final",),
            location_labels=("Utility MR",),
            x=0,
            y=0,
            w=200,
            h=200,
        )
        result = resolve_document_location(
            document_terms=terms,
            master_drawing_id="master_1",
            region_index=[region],
            registration_transform=IDENTITY_TRANSFORM,
        )
        assert result.matched_region is not None
        assert result.matched_region.region_id == "region_a"

    def test_alignment_with_no_overlapping_region_has_no_matched_region(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_STATUS, "Rejected", x=900, y=900, w=50, h=50)]
        region = _region("region_a", x=0, y=0, w=100, h=100)
        result = resolve_document_location(
            document_terms=terms,
            master_drawing_id="master_1",
            region_index=[region],
            registration_transform=IDENTITY_TRANSFORM,
        )
        assert result.matched_region is None
        assert result.confidence_score < 0.9


class TestReferenceLookupResolution:
    def test_type_and_location_together_is_strongest_match(self) -> None:
        terms = [
            _term(VocabCategory.INSPECTION_TYPE, "Underground Fire Water Rough In"),
            _term(VocabCategory.LOCATION_TERM, "Utility MR"),
        ]
        region = _region(
            "region_a",
            inspection_types=("Underground Fire Water Rough In",),
            location_labels=("Utility MR",),
        )
        result = resolve_document_location(
            document_terms=terms, master_drawing_id="master_1", region_index=[region]
        )
        assert result.method == ResolutionMethod.REFERENCE_LOOKUP
        assert result.matched_region is not None
        assert result.matched_region.region_id == "region_a"
        assert result.bbox_fractional == region.bbox_on_master.to_fractional()
        assert result.confidence_score == pytest.approx(0.92)

    def test_type_and_location_match_is_case_insensitive(self) -> None:
        terms = [
            _term(VocabCategory.INSPECTION_TYPE, "final"),
            _term(VocabCategory.LOCATION_TERM, "utility mr"),
        ]
        region = _region(
            "region_a", inspection_types=("Final",), location_labels=("Utility MR",)
        )
        result = resolve_document_location(
            document_terms=terms, master_drawing_id="master_1", region_index=[region]
        )
        assert result.matched_region is not None

    def test_type_and_location_match_requires_same_region(self) -> None:
        terms = [
            _term(VocabCategory.INSPECTION_TYPE, "Final"),
            _term(VocabCategory.LOCATION_TERM, "Roof"),
        ]
        region_x = _region("region_x", inspection_types=("Final",), location_labels=("Yard",))
        region_y = _region("region_y", inspection_types=("Flush",), location_labels=("Roof",))
        result = resolve_document_location(
            document_terms=terms, master_drawing_id="master_1", region_index=[region_x, region_y]
        )
        assert result.matched_region is not None
        assert result.matched_region.region_id == "region_y"
        assert result.confidence_score == pytest.approx(0.75)

    def test_falls_back_to_location_only_when_no_type_in_document(self) -> None:
        terms = [_term(VocabCategory.LOCATION_TERM, "Mechanical Room")]
        region = _region("region_b", location_labels=("Mechanical Room",))
        result = resolve_document_location(
            document_terms=terms, master_drawing_id="master_1", region_index=[region]
        )
        assert result.matched_region is not None
        assert result.matched_region.region_id == "region_b"
        assert result.confidence_score == pytest.approx(0.75)

    def test_falls_back_to_type_only_when_unambiguous(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_TYPE, "Acceptance Test")]
        region = _region("region_c", inspection_types=("Acceptance Test",))
        result = resolve_document_location(
            document_terms=terms, master_drawing_id="master_1", region_index=[region]
        )
        assert result.matched_region is not None
        assert result.matched_region.region_id == "region_c"
        assert result.confidence_score == pytest.approx(0.55)

    def test_type_only_match_is_unresolved_when_ambiguous(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_TYPE, "Acceptance Test")]
        region_x = _region("region_x", inspection_types=("Acceptance Test",))
        region_y = _region("region_y", inspection_types=("Acceptance Test",))
        result = resolve_document_location(
            document_terms=terms,
            master_drawing_id="master_1",
            region_index=[region_x, region_y],
        )
        assert result.matched_region is None
        assert result.bbox_fractional is None
        assert result.confidence_score == 0.0
        assert "2 regions" in result.notes

    def test_unmatched_reference_reports_explicit_failure(self) -> None:
        terms = [_term(VocabCategory.INSPECTION_TYPE, "Flush")]
        result = resolve_document_location(
            document_terms=terms,
            master_drawing_id="master_1",
            region_index=[_region("region_a", inspection_types=("Final",))],
        )
        assert result.method == ResolutionMethod.REFERENCE_LOOKUP
        assert result.bbox_fractional is None
        assert result.matched_region is None
        assert result.confidence_score == 0.0
        assert "Flush" in result.notes

    def test_no_sheet_identifier_field_on_master_region(self) -> None:
        region = _region("region_a")
        assert not hasattr(region, "sheet_identifier")


class TestUnresolved:
    def test_no_terms_no_registration_is_unresolved(self) -> None:
        result = resolve_document_location(
            document_terms=[], master_drawing_id="master_1", region_index=[]
        )
        assert result.method == ResolutionMethod.UNRESOLVED
        assert result.bbox_fractional is None
        assert result.confidence_score == 0.0


class TestPerTermResolution:
    def test_alignment_resolves_each_term_to_its_own_box(self) -> None:
        terms = [
            _term(VocabCategory.INSPECTION_STATUS, "Rejected", x=0, y=0, w=100, h=100),
            _term(VocabCategory.INSPECTION_STATUS, "Approved", x=500, y=500, w=100, h=100),
        ]
        results = resolve_locations_per_term(
            document_terms=terms,
            master_drawing_id="master_1",
            region_index=[],
            registration_transform=IDENTITY_TRANSFORM,
        )
        assert len(results) == 2
        (_, loc0), (_, loc1) = results
        assert loc0.bbox_fractional != loc1.bbox_fractional

    def test_reference_lookup_shares_one_resolution_across_terms(self) -> None:
        terms = [
            _term(VocabCategory.INSPECTION_TYPE, "Final"),
            _term(VocabCategory.LOCATION_TERM, "Roof"),
            _term(VocabCategory.INSPECTION_STATUS, "Rejected"),
        ]
        region = _region("region_a", inspection_types=("Final",), location_labels=("Roof",))
        results = resolve_locations_per_term(
            document_terms=terms, master_drawing_id="master_1", region_index=[region]
        )
        assert len(results) == 3
        for _, resolved in results:
            assert resolved.matched_region is not None
            assert resolved.matched_region.region_id == "region_a"
