"""
Resolves a PositionedTerm (a vocabulary match with a bounding box on some
source document) to a location on the MASTER drawing — the final step
before producing a DrawingOverlay.

Two distinct cases, auto-detected per document:

  CASE A — "alignment": the imported document IS a marked-up copy/region
  of the master drawing itself (e.g. a redlined export of a sheet, a photo
  taken square-on of a posted sheet). Position on the doc maps to position
  on the master via a geometric transform (offset + scale, optionally
  rotation) once the document is registered against the master.

  CASE B — "reference": the imported document is a separate report/form
  that NAMES a location (an inspection type/title plus a location term —
  e.g. "Underground Fire Water Rough In" at "Utility MR") rather than
  visually being part of the master drawing. The named inspection type +
  location is looked up against the master drawing's own region index to
  get a location — no geometric alignment possible or needed.

  NOTE: sheet identifiers (e.g. "U1.C4.31") are intentionally NOT used for
  matching here. Master drawings in this system aren't expected to carry
  that sheet-numbering metadata, so matching on it would never resolve.
  The primary, reliable signal is the INSPECTION TYPE/TITLE combined with
  a LOCATION TERM — both of these are controlled-vocabulary categories
  (VocabCategory.INSPECTION_TYPE, VocabCategory.LOCATION_TERM) that are
  expected to actually appear in both the evidence document and the
  master drawing's region index.

Detection: if we have a successful visual registration (the document was
matched/aligned against the master drawing image itself) and nothing in
the document's extracted inspection-type/location terms contradicts that
this is the right master drawing, treat it as Case A. Otherwise, if the
document names an inspection type and/or location term, treat it as
Case B. A document can also fail to resolve at all (no usable type or
location term, and no successful visual registration) — that's reported
explicitly rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai.pipelines.document_text_extraction import BoundingBox
from ai.pipelines.positioned_term_extractor import PositionedTerm
from services.inspection_vocabulary import VocabCategory


class ResolutionMethod(str, Enum):
    ALIGNMENT = "alignment"  # Case A — geometric registration to master
    REFERENCE_LOOKUP = "reference_lookup"  # Case B — named-location lookup
    UNRESOLVED = "unresolved"  # neither path produced a location


@dataclass(frozen=True)
class MasterRegion:
    """One entry in the master drawing's region index — the lookup table
    Case B resolves against. This is the master-drawing-side data that
    should already exist from inspection_mapping.py's region detection
    (drawing_regions table per the refactor plan).

    Lookup key: inspection_types + location_labels together. A region
    represents a place on the master drawing that one or more inspection
    types are expected/known to occur at (e.g. "Underground Fire Water
    Rough In" at "Utility MR"). Sheet identifiers are deliberately not
    part of this index — master drawings here don't carry that metadata.
    """

    region_id: str
    master_drawing_id: str
    inspection_types: tuple[str, ...]
    location_labels: tuple[str, ...]
    bbox_on_master: BoundingBox


@dataclass(frozen=True)
class RegistrationTransform:
    """Affine transform mapping source-document fractional coordinates
    to master-drawing fractional coordinates. Computed by whatever visual
    registration step runs upstream of this module (e.g. feature-matching
    the source page against the master sheet it claims to be) — that
    registration algorithm is out of scope here; this module consumes its
    output. translate_x/y and scale are in the master drawing's
    fractional (0-1) coordinate space.
    """

    scale_x: float
    scale_y: float
    translate_x: float
    translate_y: float
    rotation_degrees: float = 0.0

    def apply(self, x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        """Apply to a fractional bbox (rotation ignored for v1 — square-on
        captures are the common case per the OCR/photo answer; rotated
        registration can be added when that case is observed in practice).
        """
        nx0 = x0 * self.scale_x + self.translate_x
        ny0 = y0 * self.scale_y + self.translate_y
        nx1 = x1 * self.scale_x + self.translate_x
        ny1 = y1 * self.scale_y + self.translate_y
        return (nx0, ny0, nx1, ny1)


@dataclass(frozen=True)
class ResolvedLocation:
    """The final output: a location on the MASTER drawing, in fractional
    coordinates, plus how we got there. This is what feeds directly into
    DrawingOverlay construction.
    """

    master_drawing_id: str
    method: ResolutionMethod
    bbox_fractional: tuple[float, float, float, float] | None
    matched_region: MasterRegion | None
    confidence_score: float
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "masterDrawingId": self.master_drawing_id,
            "method": self.method.value,
            "bboxFractional": self.bbox_fractional,
            "matchedRegionId": self.matched_region.region_id if self.matched_region else None,
            "confidenceScore": self.confidence_score,
            "notes": self.notes,
        }


def _actionable_terms(document_terms: list[PositionedTerm]) -> list[PositionedTerm]:
    return [
        term
        for term in document_terms
        if term.term.category != VocabCategory.SHEET_IDENTIFIER
    ]


def _document_inspection_types(terms: list[PositionedTerm]) -> list[str]:
    return [
        t.term.canonical
        for t in terms
        if t.term.category == VocabCategory.INSPECTION_TYPE
    ]


def _document_location_terms(terms: list[PositionedTerm]) -> list[str]:
    return [
        t.term.canonical
        for t in terms
        if t.term.category == VocabCategory.LOCATION_TERM
    ]


def detect_resolution_case(
    document_terms: list[PositionedTerm],
    has_registration_transform: bool,
) -> ResolutionMethod:
    """Decide which case a document falls into, BEFORE attempting full
    resolution — used by resolve_locations() but also exposed standalone
    so calling code (or a human reviewer) can inspect the routing
    decision independently of the result.

    Rules (checked in order):
      1. If we have a successful visual registration transform, trust it
         and treat the document as ALIGNMENT — a successful registration
         IS the location signal in this case; no separate identifier
         cross-check is needed (master drawings here don't carry sheet
         numbers to cross-check against in the first place).
      2. Else if the document names an inspection type and/or a location
         term, it's REFERENCE_LOOKUP (even if that specific combination
         later fails to match any known region — that's a resolution
         failure within the REFERENCE_LOOKUP path, not a routing
         failure).
      3. Else UNRESOLVED — nothing to go on.
    """
    terms = _actionable_terms(document_terms)
    if has_registration_transform:
        return ResolutionMethod.ALIGNMENT

    has_signal = bool(_document_inspection_types(terms)) or bool(
        _document_location_terms(terms)
    )
    if has_signal:
        return ResolutionMethod.REFERENCE_LOOKUP

    return ResolutionMethod.UNRESOLVED


def _resolve_via_alignment(
    term: PositionedTerm,
    master_drawing_id: str,
    transform: RegistrationTransform,
    region_index: list[MasterRegion],
) -> ResolvedLocation:
    x0, y0, x1, y1 = term.bbox.to_fractional()
    master_bbox = transform.apply(x0, y0, x1, y1)

    matched_region = _best_overlapping_region(master_bbox, region_index)

    return ResolvedLocation(
        master_drawing_id=master_drawing_id,
        method=ResolutionMethod.ALIGNMENT,
        bbox_fractional=master_bbox,
        matched_region=matched_region,
        confidence_score=0.9 if matched_region else 0.75,
        notes=(
            "Resolved by geometric registration of the source document "
            "against the master drawing."
        ),
    )


def _best_overlapping_region(
    bbox_fractional: tuple[float, float, float, float],
    region_index: list[MasterRegion],
) -> MasterRegion | None:
    """Find the master region whose own bbox overlaps the resolved
    location most, if any — lets an alignment-resolved overlay still pick
    up a region's metadata (location labels) for display.
    """
    best: MasterRegion | None = None
    best_overlap = 0.0
    x0, y0, x1, y1 = bbox_fractional
    for region in region_index:
        rx0, ry0, rx1, ry1 = region.bbox_on_master.to_fractional()
        overlap = _box_overlap_area((x0, y0, x1, y1), (rx0, ry0, rx1, ry1))
        if overlap > best_overlap:
            best_overlap = overlap
            best = region
    return best if best_overlap > 0 else None


def _box_overlap_area(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _resolve_via_reference_lookup(
    document_terms: list[PositionedTerm],
    master_drawing_id: str,
    region_index: list[MasterRegion],
) -> ResolvedLocation:
    terms = _actionable_terms(document_terms)
    doc_types = _document_inspection_types(terms)
    doc_locations = _document_location_terms(terms)

    def _type_match(region: MasterRegion) -> bool:
        return any(
            t.lower() == known.lower()
            for t in doc_types
            for known in region.inspection_types
        )

    def _location_match(region: MasterRegion) -> bool:
        return any(
            loc.lower() == known.lower()
            for loc in doc_locations
            for known in region.location_labels
        )

    if doc_types and doc_locations:
        for region in region_index:
            if _type_match(region) and _location_match(region):
                return ResolvedLocation(
                    master_drawing_id=master_drawing_id,
                    method=ResolutionMethod.REFERENCE_LOOKUP,
                    bbox_fractional=region.bbox_on_master.to_fractional(),
                    matched_region=region,
                    confidence_score=0.92,
                    notes="Matched by inspection type and location together.",
                )

    for region in region_index:
        if _location_match(region):
            return ResolvedLocation(
                master_drawing_id=master_drawing_id,
                method=ResolutionMethod.REFERENCE_LOOKUP,
                bbox_fractional=region.bbox_on_master.to_fractional(),
                matched_region=region,
                confidence_score=0.75,
                notes="Matched by location term alone (no inspection-type confirmation).",
            )

    if doc_types:
        type_matches = [r for r in region_index if _type_match(r)]
        if len(type_matches) == 1:
            region = type_matches[0]
            return ResolvedLocation(
                master_drawing_id=master_drawing_id,
                method=ResolutionMethod.REFERENCE_LOOKUP,
                bbox_fractional=region.bbox_on_master.to_fractional(),
                matched_region=region,
                confidence_score=0.55,
                notes="Matched by inspection type alone (single unambiguous region).",
            )
        if len(type_matches) > 1:
            return ResolvedLocation(
                master_drawing_id=master_drawing_id,
                method=ResolutionMethod.REFERENCE_LOOKUP,
                bbox_fractional=None,
                matched_region=None,
                confidence_score=0.0,
                notes=(
                    f"Inspection type {doc_types!r} matches "
                    f"{len(type_matches)} regions on master drawing "
                    f"{master_drawing_id!r} with no location term to "
                    f"disambiguate. Needs a human to pick the right one "
                    f"or for the evidence to name a location."
                ),
            )

    referenced = doc_types + doc_locations
    return ResolvedLocation(
        master_drawing_id=master_drawing_id,
        method=ResolutionMethod.REFERENCE_LOOKUP,
        bbox_fractional=None,
        matched_region=None,
        confidence_score=0.0,
        notes=(
            f"Document referenced {referenced!r} but none matched a known "
            f"region on master drawing {master_drawing_id!r}. Needs a "
            f"human to add/correct the region index entry."
        ),
    )


def resolve_document_location(
    document_terms: list[PositionedTerm],
    master_drawing_id: str,
    region_index: list[MasterRegion],
    registration_transform: RegistrationTransform | None = None,
    representative_term: PositionedTerm | None = None,
) -> ResolvedLocation:
    """Resolve where a document's extracted terms belong on the master drawing."""
    terms = _actionable_terms(document_terms)
    case = detect_resolution_case(terms, registration_transform is not None)

    if case == ResolutionMethod.ALIGNMENT:
        assert registration_transform is not None
        term_for_box = representative_term or (terms[0] if terms else None)
        if term_for_box is None:
            return ResolvedLocation(
                master_drawing_id=master_drawing_id,
                method=ResolutionMethod.UNRESOLVED,
                bbox_fractional=None,
                matched_region=None,
                confidence_score=0.0,
                notes="Alignment available but no term/box to map.",
            )
        return _resolve_via_alignment(
            term_for_box, master_drawing_id, registration_transform, region_index
        )

    if case == ResolutionMethod.REFERENCE_LOOKUP:
        return _resolve_via_reference_lookup(terms, master_drawing_id, region_index)

    return ResolvedLocation(
        master_drawing_id=master_drawing_id,
        method=ResolutionMethod.UNRESOLVED,
        bbox_fractional=None,
        matched_region=None,
        confidence_score=0.0,
        notes=(
            "No inspection type, location term, or successful visual "
            "registration found — cannot place this evidence on the "
            "master drawing automatically."
        ),
    )


def resolve_locations_per_term(
    document_terms: list[PositionedTerm],
    master_drawing_id: str,
    region_index: list[MasterRegion],
    registration_transform: RegistrationTransform | None = None,
) -> list[tuple[PositionedTerm, ResolvedLocation]]:
    """Resolve a separate location per extracted term (Case A per-term bbox)."""
    terms = _actionable_terms(document_terms)
    case = detect_resolution_case(terms, registration_transform is not None)

    results: list[tuple[PositionedTerm, ResolvedLocation]] = []

    if case == ResolutionMethod.ALIGNMENT:
        assert registration_transform is not None
        for term in terms:
            results.append(
                (
                    term,
                    _resolve_via_alignment(
                        term, master_drawing_id, registration_transform, region_index
                    ),
                )
            )
        return results

    if case == ResolutionMethod.REFERENCE_LOOKUP:
        resolved = _resolve_via_reference_lookup(terms, master_drawing_id, region_index)
        return [(term, resolved) for term in terms]

    unresolved = ResolvedLocation(
        master_drawing_id=master_drawing_id,
        method=ResolutionMethod.UNRESOLVED,
        bbox_fractional=None,
        matched_region=None,
        confidence_score=0.0,
        notes="No location signal found in document.",
    )
    return [(term, unresolved) for term in terms]
