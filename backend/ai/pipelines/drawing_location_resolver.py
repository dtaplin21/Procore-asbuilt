"""
Maps positioned vocabulary terms to locations on the master drawing.

Two resolution strategies:

  Case A — ALIGNMENT: a RegistrationTransform (from a prior visual-registration
  step) maps evidence-page fractional coordinates onto the master drawing.
  Used for photos / scanned pages where the whole document aligns to a region.

  Case B — REFERENCE_LOOKUP: sheet identifiers or location labels extracted
  from the document are matched against a MasterRegion index built from the
  master drawing's region/sheet metadata.

  UNRESOLVED: returned explicitly when neither strategy applies — callers
  must surface this for human follow-up rather than guessing a location.

Producing a RegistrationTransform is a separate upstream concern (feature
match / vision pipeline). This module consumes it when present.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai.pipelines.positioned_term_extractor import PositionedTerm
from services.inspection_vocabulary import VocabCategory


class ResolutionMethod(str, Enum):
    ALIGNMENT = "alignment"
    REFERENCE_LOOKUP = "reference_lookup"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class MasterRegion:
    """A resolvable area on the master drawing, keyed by sheet id and/or labels."""

    region_id: str
    bbox_fractional: tuple[float, float, float, float]
    sheet_identifiers: tuple[str, ...] = ()
    location_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegistrationTransform:
    """Illustrative affine-ish map from evidence fractional coords to master."""

    master_drawing_id: str
    evidence_to_master_scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    confidence: float = 1.0


@dataclass(frozen=True)
class ResolvedLocation:
    master_drawing_id: str
    method: ResolutionMethod
    bbox_fractional: tuple[float, float, float, float] | None = None
    matched_region: MasterRegion | None = None
    notes: str | None = None


def _normalize_sheet_id(value: str) -> str:
    return value.strip().upper()


def _lookup_region_by_sheet(
    sheet_id: str,
    region_index: list[MasterRegion],
) -> MasterRegion | None:
    key = _normalize_sheet_id(sheet_id)
    for region in region_index:
        if any(_normalize_sheet_id(candidate) == key for candidate in region.sheet_identifiers):
            return region
    return None


def _lookup_region_by_location(
    location_label: str,
    region_index: list[MasterRegion],
) -> MasterRegion | None:
    needle = location_label.strip().lower()
    for region in region_index:
        if any(needle == candidate.strip().lower() for candidate in region.location_labels):
            return region
    return None


def _align_term_bbox(
    term: PositionedTerm,
    transform: RegistrationTransform,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = term.bbox.to_fractional()
    scale = transform.evidence_to_master_scale
    return (
        x0 * scale + transform.offset_x,
        y0 * scale + transform.offset_y,
        x1 * scale + transform.offset_x,
        y1 * scale + transform.offset_y,
    )


def _resolve_single_term(
    term: PositionedTerm,
    *,
    master_drawing_id: str,
    region_index: list[MasterRegion],
    master_sheet_identifier: str | None,
    registration_transform: RegistrationTransform | None,
) -> ResolvedLocation:
    if term.term.category == VocabCategory.SHEET_IDENTIFIER:
        matched = _lookup_region_by_sheet(term.term.canonical, region_index)
        if matched is not None:
            return ResolvedLocation(
                master_drawing_id=master_drawing_id,
                method=ResolutionMethod.REFERENCE_LOOKUP,
                bbox_fractional=matched.bbox_fractional,
                matched_region=matched,
                notes=f"Matched sheet identifier {term.term.canonical}",
            )
        return ResolvedLocation(
            master_drawing_id=master_drawing_id,
            method=ResolutionMethod.UNRESOLVED,
            notes=f"No master region for sheet identifier {term.term.canonical}",
        )

    if term.term.category == VocabCategory.LOCATION_TERM:
        matched = _lookup_region_by_location(term.term.canonical, region_index)
        if matched is not None:
            return ResolvedLocation(
                master_drawing_id=master_drawing_id,
                method=ResolutionMethod.REFERENCE_LOOKUP,
                bbox_fractional=matched.bbox_fractional,
                matched_region=matched,
                notes=f"Matched location label {term.term.canonical}",
            )

    if registration_transform is not None:
        if (
            master_sheet_identifier is not None
            and term.term.category == VocabCategory.SHEET_IDENTIFIER
            and _normalize_sheet_id(term.term.canonical)
            != _normalize_sheet_id(master_sheet_identifier)
        ):
            return ResolvedLocation(
                master_drawing_id=master_drawing_id,
                method=ResolutionMethod.UNRESOLVED,
                notes=(
                    "Sheet identifier on evidence does not match master drawing "
                    f"({term.term.canonical} vs {master_sheet_identifier})"
                ),
            )
        return ResolvedLocation(
            master_drawing_id=master_drawing_id,
            method=ResolutionMethod.ALIGNMENT,
            bbox_fractional=_align_term_bbox(term, registration_transform),
            notes="Aligned via registration transform",
        )

    return ResolvedLocation(
        master_drawing_id=master_drawing_id,
        method=ResolutionMethod.UNRESOLVED,
        notes="No reference match and no registration transform available",
    )


def resolve_locations_per_term(
    *,
    document_terms: list[PositionedTerm],
    master_drawing_id: str,
    region_index: list[MasterRegion] | None = None,
    master_sheet_identifier: str | None = None,
    registration_transform: RegistrationTransform | None = None,
) -> list[tuple[PositionedTerm, ResolvedLocation]]:
    """Resolve each positioned term to a master-drawing location."""
    regions = region_index or []
    return [
        (
            term,
            _resolve_single_term(
                term,
                master_drawing_id=master_drawing_id,
                region_index=regions,
                master_sheet_identifier=master_sheet_identifier,
                registration_transform=registration_transform,
            ),
        )
        for term in document_terms
    ]
