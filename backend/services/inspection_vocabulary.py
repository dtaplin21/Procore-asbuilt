"""
Canonical taxonomy for construction inspection terminology.

This is the single source of truth for the controlled vocabulary used to
extract and classify entities out of free-text evidence / inspection notes
(see backend/ai/pipelines/term_extractor.py, which is wired into
inspection_mapping.py).

Mirrored in shared/inspection_vocabulary.ts for the frontend. If you add,
rename, or remove a term here, update the TS mirror in the same PR — see
the contract-sync note at the bottom of this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VocabCategory(str, Enum):
    PROJECT_IDENTIFIER = "project_identifier"
    INSPECTION_TYPE = "inspection_type"
    INSPECTION_STATUS = "inspection_status"
    LOCATION_TERM = "location_term"
    TRADE_TERM = "trade_term"
    DRAWING_TERM = "drawing_term"
    SHEET_IDENTIFIER = "sheet_identifier"
    DOCUMENT_REFERENCE = "document_reference"
    MARKUP_TERM = "markup_term"
    FIELD_CONDITION_TERM = "field_condition_term"
    INSPECTION_ACTION_TERM = "inspection_action_term"
    CONFIDENCE_LABEL = "confidence_label"


class MatchStrategy(str, Enum):
    """How terms in this category should be located in free text."""

    # Exact phrase match, case-insensitive, word-boundary aware. Good for
    # multi-word terms drawn from a closed list ("Hydrostatic Test").
    PHRASE = "phrase"

    # Regex pattern match. Required for structured identifiers like sheet
    # numbers (U1.C4.31) where phrase-matching a finite list is impossible
    # and substring matching would false-positive constantly.
    PATTERN = "pattern"


@dataclass(frozen=True)
class VocabTerm:
    """A single canonical term, plus any alternate surface forms that
    should normalize to it (case/punctuation variants the field notes
    actually use, e.g. "Rough-In", "rough in", "ROUGH IN" -> "Rough In").
    """

    canonical: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VocabCategoryDef:
    category: VocabCategory
    strategy: MatchStrategy
    terms: tuple[VocabTerm, ...] = field(default_factory=tuple)
    # Only used when strategy == PATTERN. Confidence terms also skip
    # matching entirely (see CONFIDENCE_LABEL note below).
    patterns: tuple[str, ...] = field(default_factory=tuple)


def _phrase_terms(*canonicals: str) -> tuple[VocabTerm, ...]:
    return tuple(VocabTerm(canonical=c) for c in canonicals)


# ---------------------------------------------------------------------------
# Taxonomy definition
# ---------------------------------------------------------------------------
# Aliases are seeded conservatively (case/hyphen/spacing variants actually
# seen in field notes). Extend as real-world variants are observed —
# don't guess exhaustively up front.

VOCABULARY: dict[VocabCategory, VocabCategoryDef] = {
    VocabCategory.PROJECT_IDENTIFIER: VocabCategoryDef(
        category=VocabCategory.PROJECT_IDENTIFIER,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Project"),
            VocabTerm("Project Number", aliases=("Project No.", "Project #", "Proj No")),
            VocabTerm("Permit"),
            VocabTerm("Phase"),
            VocabTerm("Area"),
            VocabTerm("Building", aliases=("Bldg",)),
            VocabTerm("Facility"),
            VocabTerm("Campus"),
            VocabTerm("Site"),
            VocabTerm("Utility"),
            VocabTerm("NPC"),
            VocabTerm("UCSF"),
            VocabTerm("Benioff"),
        ),
    ),
    VocabCategory.INSPECTION_TYPE: VocabCategoryDef(
        category=VocabCategory.INSPECTION_TYPE,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Underground Fire Water Rough In", aliases=("UG Fire Water Rough-In",)),
            VocabTerm("Rough In", aliases=("Rough-In", "Rough in")),
            VocabTerm("Final"),
            VocabTerm("Partial Final"),
            VocabTerm("Above Ground", aliases=("Above-Ground", "AG")),
            VocabTerm("Underground", aliases=("Under Ground", "UG")),
            VocabTerm("Hydrostatic Test", aliases=("Hydro Test", "Hydro")),
            VocabTerm("Flush"),
            VocabTerm("Acceptance Test"),
            VocabTerm("Fire Water"),
            VocabTerm("Fire Protection", aliases=("FP",)),
            VocabTerm("Sprinkler"),
            VocabTerm("Underground Piping"),
            VocabTerm("Underground Utilities"),
        ),
    ),
    VocabCategory.INSPECTION_STATUS: VocabCategoryDef(
        category=VocabCategory.INSPECTION_STATUS,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Open"),
            VocabTerm("Closed"),
            VocabTerm("Approved"),
            VocabTerm("Approved As Noted", aliases=("Approved as Noted", "AAN")),
            VocabTerm("Rejected"),
            VocabTerm("Pending"),
            VocabTerm("In Progress"),
            VocabTerm("Scheduled"),
            VocabTerm("Completed"),
            VocabTerm("Passed"),
            VocabTerm("Failed"),
            VocabTerm("Deferred"),
        ),
    ),
    VocabCategory.LOCATION_TERM: VocabCategoryDef(
        category=VocabCategory.LOCATION_TERM,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Utility MR", aliases=("Utility Mechanical Room",)),
            VocabTerm("Mechanical Room", aliases=("Mech Room", "MR")),
            VocabTerm("Equipment Room"),
            VocabTerm("Site"),
            VocabTerm("Yard"),
            VocabTerm("Corridor"),
            VocabTerm("Level"),
            VocabTerm("Floor"),
            VocabTerm("Roof"),
            VocabTerm("Exterior"),
            VocabTerm("Interior"),
            VocabTerm("Building Area"),
            VocabTerm("Grid Line"),
            VocabTerm("Coordinate"),
            VocabTerm("Utility Corridor"),
        ),
    ),
    VocabCategory.TRADE_TERM: VocabCategoryDef(
        category=VocabCategory.TRADE_TERM,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Fire Protection", aliases=("FP",)),
            VocabTerm("Mechanical"),
            VocabTerm("Plumbing"),
            VocabTerm("Electrical"),
            VocabTerm("Structural"),
            VocabTerm("Civil"),
            VocabTerm("Architectural"),
            VocabTerm("Underground Utilities"),
        ),
    ),
    VocabCategory.DRAWING_TERM: VocabCategoryDef(
        category=VocabCategory.DRAWING_TERM,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Drawing"),
            VocabTerm("Sheet"),
            VocabTerm("Sheet Number", aliases=("Sheet No.", "Sheet #")),
            VocabTerm("Plan"),
            VocabTerm("Detail"),
            VocabTerm("Section"),
            VocabTerm("Elevation"),
            VocabTerm("Revision", aliases=("Rev",)),
            VocabTerm("Attachment"),
            VocabTerm("Reference Drawing"),
            VocabTerm("Master Drawing"),
            VocabTerm("Construction Drawing"),
        ),
    ),
    VocabCategory.SHEET_IDENTIFIER: VocabCategoryDef(
        category=VocabCategory.SHEET_IDENTIFIER,
        strategy=MatchStrategy.PATTERN,
        # Examples from the audit: U1.C4.31, U1.C4.32, C4.31, C4.32
        # General shape: optional 1-3 alnum prefix block + dot-separated
        # alnum segments, at least 2 segments, each segment 1-3 chars.
        # Anchored to avoid matching arbitrary decimal numbers like "4.31".
        patterns=(
            r"\b[A-Z]{1,3}\d{0,2}(?:\.[A-Z0-9]{1,4}){1,4}\b",
        ),
    ),
    VocabCategory.DOCUMENT_REFERENCE: VocabCategoryDef(
        category=VocabCategory.DOCUMENT_REFERENCE,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Attachment"),
            VocabTerm("Linked Drawing"),
            VocabTerm("Referenced Drawing"),
            VocabTerm("Supporting Document"),
            VocabTerm("Inspection Package"),
            VocabTerm("Record Drawing"),
        ),
    ),
    VocabCategory.MARKUP_TERM: VocabCategoryDef(
        category=VocabCategory.MARKUP_TERM,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Cloud"),
            VocabTerm("Revision Cloud"),
            VocabTerm("Arrow"),
            VocabTerm("Leader"),
            VocabTerm("Callout"),
            VocabTerm("Note"),
            VocabTerm("Comment"),
            VocabTerm("Markup"),
            VocabTerm("Highlight"),
            VocabTerm("Stamp"),
            VocabTerm("Inspection Tag"),
            VocabTerm("Deficiency Marker"),
        ),
    ),
    VocabCategory.FIELD_CONDITION_TERM: VocabCategoryDef(
        category=VocabCategory.FIELD_CONDITION_TERM,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Installed"),
            VocabTerm("Existing", aliases=("Exist.", "Exist")),
            VocabTerm("New"),
            VocabTerm("Verify"),
            VocabTerm("Confirm"),
            VocabTerm("Relocate"),
            VocabTerm("Remove"),
            VocabTerm("Modify"),
            VocabTerm("Correct"),
            VocabTerm("Repair"),
            VocabTerm("Replace"),
        ),
    ),
    VocabCategory.INSPECTION_ACTION_TERM: VocabCategoryDef(
        category=VocabCategory.INSPECTION_ACTION_TERM,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("Inspect"),
            VocabTerm("Verify"),
            VocabTerm("Observe"),
            VocabTerm("Witness"),
            VocabTerm("Review"),
            VocabTerm("Test"),
            VocabTerm("Approve"),
            VocabTerm("Reject"),
            VocabTerm("Close"),
            VocabTerm("Document"),
        ),
    ),
    VocabCategory.CONFIDENCE_LABEL: VocabCategoryDef(
        category=VocabCategory.CONFIDENCE_LABEL,
        strategy=MatchStrategy.PHRASE,
        terms=(
            VocabTerm("High Confidence"),
            VocabTerm("Medium Confidence"),
            VocabTerm("Low Confidence"),
        ),
    ),
}


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def all_categories() -> tuple[VocabCategory, ...]:
    return tuple(VOCABULARY.keys())


def category_def(category: VocabCategory) -> VocabCategoryDef:
    return VOCABULARY[category]


def canonical_terms(category: VocabCategory) -> tuple[str, ...]:
    """Canonical term strings for a category (PHRASE categories only)."""
    return tuple(t.canonical for t in VOCABULARY[category].terms)


# ---------------------------------------------------------------------------
# Contract-sync note
# ---------------------------------------------------------------------------
# shared/inspection_vocabulary.ts mirrors this file's category names and
# canonical terms (not aliases or regex patterns — those are extraction
# implementation detail the frontend doesn't need). When this file changes
# in a way that affects category names or canonical terms, update the TS
# mirror in the same PR, the same way shared/schema.ts is kept in sync with
# backend/models/schemas.py elsewhere in this refactor.
