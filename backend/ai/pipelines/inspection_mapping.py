"""
Evidence -> regions -> drawing_overlays.

This is the pipeline referenced throughout the drawing-workspace refactor
plan (PR2 / PR3): it takes evidence submitted against an inspection run
(photos, field notes, PDFs with extracted text, etc.), maps that evidence
onto regions on the master drawing, and produces DrawingOverlay records
that the frontend renders via useDrawingOverlays / DrawingViewer.

Two entry points are exposed:

  - map_evidence_to_overlay(EvidenceInput): the original text-only path,
    for evidence that's already plain text with a known bbox (e.g. a
    manually-typed field note pinned by hand to a location). Confidence-
    scored vocabulary tags only; no document parsing or location
    resolution.

  - map_document_to_overlays(DocumentEvidenceInput): the full pipeline —
    takes an actual uploaded file (PDF / image / photo), runs it through
    document_text_extraction -> positioned_term_extractor ->
    drawing_location_resolver, and produces one DrawingOverlayRecord per
    resolved location, with NO location guessed: documents that don't
    resolve come back tagged UNRESOLVED for human follow-up rather than
    silently dropped or mis-placed.

  - run_inspection_mapping(db, run): the persisted DB-backed job that
    classifies inspection type, extracts outcomes, and writes overlay rows.

This module is illustrative for the overlay-record helpers — it shows the
extraction/resolution integration points and the shape of the resulting
records. The real OCR backend (document_text_extraction.py) and the
visual-registration algorithm that produces a RegistrationTransform are
separate, out-of-scope integration points — see those modules' docstrings
for the adapter seams.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional, cast

from ai.pipelines.document_text_extraction import ExtractedDocument, extract_document
from ai.pipelines.drawing_location_resolver import (
    MasterRegion,
    RegistrationTransform,
    ResolutionMethod,
    ResolvedLocation,
    resolve_locations_per_term,
)
from ai.pipelines.positioned_term_extractor import PositionedTerm, extract_positioned_terms
from ai.pipelines.term_extractor import (
    ExtractedTerm,
    extract_terms,
    overall_confidence_label,
)
from models.models import Drawing, DrawingRegion, EvidenceRecord, InspectionRun, Finding
from services.file_storage import get_file_path
from services.inspection_vocabulary import VocabCategory
from services.storage import StorageService

logger = logging.getLogger(__name__)

# Categories used for overlay tag extraction and location resolution.
# Sheet identifiers remain extractable elsewhere but are excluded here.
_RESOLUTION_VOCAB_CATEGORIES: tuple[VocabCategory, ...] = tuple(
    category
    for category in VocabCategory
    if category
    not in (VocabCategory.SHEET_IDENTIFIER, VocabCategory.CONFIDENCE_LABEL)
)

# ---------------------------------------------------------------------------
# Illustrative overlay mapping (text + document paths)
# ---------------------------------------------------------------------------


@dataclass
class EvidenceInput:
    """Raw evidence submitted against an inspection run, prior to mapping."""

    evidence_id: str
    inspection_run_id: str
    drawing_id: str
    note_text: str
    # bbox of the region this evidence was captured against, if already
    # known (e.g. from a photo's pinned location on the master drawing).
    # If None, region inference is out of scope for this module.
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class NormalizedEvidenceTags:
    """The result of running evidence text through the vocabulary
    extractor — what used to be unstructured note text, now classified
    into the controlled taxonomy categories.
    """

    inspection_types: list[str] = field(default_factory=list)
    inspection_statuses: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    trades: list[str] = field(default_factory=list)
    field_conditions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    markup_terms: list[str] = field(default_factory=list)
    raw_terms: list[ExtractedTerm] = field(default_factory=list)
    confidence_label: str = "Low Confidence"

    def to_dict(self) -> dict:
        return {
            "inspectionTypes": self.inspection_types,
            "inspectionStatuses": self.inspection_statuses,
            "locations": self.locations,
            "trades": self.trades,
            "fieldConditions": self.field_conditions,
            "actions": self.actions,
            "markupTerms": self.markup_terms,
            "confidenceLabel": self.confidence_label,
        }


@dataclass
class DrawingOverlayRecord:
    """Shape mirrors the DrawingOverlay model from the refactor plan
    (backend/models/models.py) — inspection_run_id is required per the
    PR7 schema cleanup (the diff_id branch of the old XOR constraint is
    gone), plus the normalized vocabulary tags this module adds.
    """

    id: str
    drawing_id: str
    inspection_run_id: str
    bbox: tuple[float, float, float, float] | None
    label: str
    severity: str
    tags: NormalizedEvidenceTags
    created_at: datetime


_CATEGORY_TO_TAGS_FIELD: dict[VocabCategory, str] = {
    VocabCategory.INSPECTION_TYPE: "inspection_types",
    VocabCategory.INSPECTION_STATUS: "inspection_statuses",
    VocabCategory.LOCATION_TERM: "locations",
    VocabCategory.TRADE_TERM: "trades",
    VocabCategory.FIELD_CONDITION_TERM: "field_conditions",
    VocabCategory.INSPECTION_ACTION_TERM: "actions",
    VocabCategory.MARKUP_TERM: "markup_terms",
}


def normalize_evidence_text(note_text: str) -> NormalizedEvidenceTags:
    """The integration point: run evidence free text through the
    controlled-vocabulary extractor and bucket results into the
    NormalizedEvidenceTags shape consumed by overlay/finding construction.
    """
    terms = extract_terms(note_text, categories=_RESOLUTION_VOCAB_CATEGORIES)
    grouped: dict[str, list[ExtractedTerm]] = {}
    for term in terms:
        grouped.setdefault(term.category.value, []).append(term)

    tags = NormalizedEvidenceTags(raw_terms=terms)
    for category, field_name in _CATEGORY_TO_TAGS_FIELD.items():
        canonicals = [t.canonical for t in grouped.get(category.value, [])]
        deduped = list(dict.fromkeys(canonicals))
        setattr(tags, field_name, deduped)

    tags.confidence_label = overall_confidence_label(terms)
    return tags


def _severity_from_tags(tags: NormalizedEvidenceTags) -> str:
    """Best-effort severity classification from normalized field-condition
    and status tags. Deliberately conservative: anything implying rework
    (Reject / Repair / Replace / Correct) outranks a plain "Pending".
    """
    high_severity_terms = {"Rejected", "Failed", "Repair", "Replace", "Correct"}
    if any(t in high_severity_terms for t in tags.inspection_statuses):
        return "high"
    if any(t in high_severity_terms for t in tags.field_conditions):
        return "high"
    if "Deferred" in tags.inspection_statuses or "Pending" in tags.inspection_statuses:
        return "medium"
    return "info"


def map_evidence_to_overlay(evidence: EvidenceInput) -> DrawingOverlayRecord:
    """Map a single piece of evidence onto a DrawingOverlay record.

    This is the function PR2/PR3 wires the evidence-upload flow into
    (see client/src/hooks/use-inspection-runs.ts on the frontend, and
    backend/api/routes/evidence.py, which should call this — or an async
    job wrapping it — on evidence submission).
    """
    tags = normalize_evidence_text(evidence.note_text)
    severity = _severity_from_tags(tags)

    label = tags.inspection_types[0] if tags.inspection_types else "Inspection finding"
    if tags.locations:
        label = f"{label} — {tags.locations[0]}"

    return DrawingOverlayRecord(
        id=f"overlay_{evidence.evidence_id}",
        drawing_id=evidence.drawing_id,
        inspection_run_id=evidence.inspection_run_id,
        bbox=evidence.bbox,
        label=label,
        severity=severity,
        tags=tags,
        created_at=datetime.now(timezone.utc),
    )


def map_evidence_batch_to_overlays(
    evidence_items: list[EvidenceInput],
) -> list[DrawingOverlayRecord]:
    """Batch entry point — used when an inspection run closes out with
    multiple pieces of evidence at once.
    """
    return [map_evidence_to_overlay(item) for item in evidence_items]


# ---------------------------------------------------------------------------
# Document pipeline — PDFs, images, photos
# ---------------------------------------------------------------------------


@dataclass
class DocumentEvidenceInput:
    """Raw evidence submitted as an actual file (PDF, scanned PDF, photo)
    against an inspection run. This is the input to the full pipeline:
    extract_document -> extract_positioned_terms -> resolve_locations_per_term
    -> DrawingOverlayRecord.
    """

    evidence_id: str
    inspection_run_id: str
    master_drawing_id: str
    file_path: str
    # The master drawing's own region index, used for Case B (reference
    # lookup, matched by inspection type + location) and to annotate
    # Case A (alignment) results.
    region_index: list[MasterRegion] = field(default_factory=list)
    # Result of a prior visual-registration attempt (this document against
    # the master), if one was run. None if not attempted or it failed.
    registration_transform: RegistrationTransform | None = None


@dataclass
class UnresolvedEvidenceRecord:
    """What gets returned for a piece of document evidence that could not
    be placed on the master drawing — reported explicitly so a human can
    fix the region index or retry registration, rather than the evidence
    silently vanishing.
    """

    evidence_id: str
    inspection_run_id: str
    master_drawing_id: str
    reason: str
    extracted_terms: list[PositionedTerm]

    def to_dict(self) -> dict:
        return {
            "evidenceId": self.evidence_id,
            "inspectionRunId": self.inspection_run_id,
            "masterDrawingId": self.master_drawing_id,
            "reason": self.reason,
            "extractedTerms": [t.to_dict() for t in self.extracted_terms],
        }


def _tags_from_positioned_terms(
    terms: list[PositionedTerm],
) -> NormalizedEvidenceTags:
    """Same bucketing as normalize_evidence_text(), but starting from
    already-extracted PositionedTerm instead of re-running extraction on
    a plain string. Keeps document and text paths sharing one tag shape.
    """
    bucket_terms = [pt.term for pt in terms if pt.term.category in _CATEGORY_TO_TAGS_FIELD]
    tags = NormalizedEvidenceTags(raw_terms=bucket_terms)
    for category, field_name in _CATEGORY_TO_TAGS_FIELD.items():
        canonicals = [
            pt.term.canonical for pt in terms if pt.term.category == category
        ]
        deduped = list(dict.fromkeys(canonicals))
        setattr(tags, field_name, deduped)
    tags.confidence_label = overall_confidence_label(bucket_terms)
    return tags


def map_document_to_overlays(
    evidence: DocumentEvidenceInput,
) -> tuple[list[DrawingOverlayRecord], list[UnresolvedEvidenceRecord]]:
    """Full pipeline entry point for an uploaded document (PDF, scanned
    PDF, or photo): extract text, find vocabulary terms with positions,
    resolve each to a location on the master drawing, and produce overlay
    records.

    Returns (overlays, unresolved) rather than raising on partial
    failure: a single multi-page document can have some terms resolve and
    others not, and a caller (e.g. backend/api/routes/evidence.py) needs
    both lists to create overlays for what worked and flag what didn't,
    rather than losing the whole submission to one bad reference.
    """
    document: ExtractedDocument = extract_document(evidence.file_path)
    positioned_terms = extract_positioned_terms(
        document, categories=_RESOLUTION_VOCAB_CATEGORIES
    )

    if not positioned_terms:
        return [], [
            UnresolvedEvidenceRecord(
                evidence_id=evidence.evidence_id,
                inspection_run_id=evidence.inspection_run_id,
                master_drawing_id=evidence.master_drawing_id,
                reason=(
                    "No controlled-vocabulary terms found in the document "
                    "(extraction/OCR may have failed, or the document "
                    "genuinely contains no recognizable inspection "
                    "terminology)."
                ),
                extracted_terms=[],
            )
        ]

    resolved_pairs = resolve_locations_per_term(
        positioned_terms,
        evidence.master_drawing_id,
        evidence.region_index,
        evidence.registration_transform,
    )

    unresolved_terms: list[PositionedTerm] = []
    unresolved_reason: str | None = None
    resolved_terms: list[tuple[PositionedTerm, ResolvedLocation]] = []

    for term, resolved in resolved_pairs:
        if resolved.method == ResolutionMethod.UNRESOLVED or resolved.bbox_fractional is None:
            unresolved_terms.append(term)
            unresolved_reason = resolved.notes or unresolved_reason
        else:
            resolved_terms.append((term, resolved))

    unresolved: list[UnresolvedEvidenceRecord] = []
    if unresolved_terms:
        # One record for the whole document's unresolved terms, not one
        # per term — a failed reference lookup is a single finding-level
        # problem ("this document's location couldn't be placed"), not N
        # separate problems.
        unresolved.append(
            UnresolvedEvidenceRecord(
                evidence_id=evidence.evidence_id,
                inspection_run_id=evidence.inspection_run_id,
                master_drawing_id=evidence.master_drawing_id,
                reason=unresolved_reason or "Could not resolve a location.",
                extracted_terms=unresolved_terms,
            )
        )

    overlays: list[DrawingOverlayRecord] = []
    if resolved_terms:
        method = resolved_terms[0][1].method

        if method == ResolutionMethod.ALIGNMENT:
            # One photo/page = one piece of evidence = one overlay. Union
            # every resolved term's box into a single location, rather
            # than one overlay per recognized word.
            all_terms = [t for t, _ in resolved_terms]
            boxes = [r.bbox_fractional for _, r in resolved_terms if r.bbox_fractional]
            x0 = min(b[0] for b in boxes)
            y0 = min(b[1] for b in boxes)
            x1 = max(b[2] for b in boxes)
            y1 = max(b[3] for b in boxes)
            representative = next(
                (r for _, r in resolved_terms if r.matched_region),
                resolved_terms[0][1],
            )
            overlays.append(
                _build_overlay_record(
                    evidence, all_terms, (x0, y0, x1, y1), representative
                )
            )
        else:
            # REFERENCE_LOOKUP: group by which master region each term
            # resolved to, so a document naming two different type+
            # location combinations produces two overlays.
            groups: dict[str | None, list[tuple[PositionedTerm, ResolvedLocation]]] = {}
            for term, resolved in resolved_terms:
                region_key = (
                    resolved.matched_region.region_id
                    if resolved.matched_region
                    else None
                )
                groups.setdefault(region_key, []).append((term, resolved))

            for region_key, group in groups.items():
                group_terms = [t for t, _ in group]
                representative = group[0][1]
                bbox = representative.bbox_fractional
                if bbox is None:
                    continue
                overlays.append(
                    _build_overlay_record(evidence, group_terms, bbox, representative)
                )

    return overlays, unresolved


def _build_overlay_record(
    evidence: DocumentEvidenceInput,
    terms: list[PositionedTerm],
    bbox_fractional: tuple[float, float, float, float],
    representative: ResolvedLocation,
) -> DrawingOverlayRecord:
    """Shared overlay-construction step used by both the alignment and
    reference-lookup branches of map_document_to_overlays, so label/
    severity logic lives in exactly one place.
    """
    tags = _tags_from_positioned_terms(terms)
    severity = _severity_from_tags(tags)

    label = tags.inspection_types[0] if tags.inspection_types else "Inspection finding"
    if representative.matched_region and representative.matched_region.location_labels:
        label = f"{label} — {representative.matched_region.location_labels[0]}"
    elif tags.locations:
        label = f"{label} — {tags.locations[0]}"

    return DrawingOverlayRecord(
        id=f"overlay_{evidence.evidence_id}_{representative.matched_region.region_id if representative.matched_region else 'unmatched'}",
        drawing_id=representative.master_drawing_id,
        inspection_run_id=evidence.inspection_run_id,
        bbox=bbox_fractional,
        label=label,
        severity=severity,
        tags=tags,
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Persisted inspection-run pipeline (DB-backed job)
# ---------------------------------------------------------------------------

# Known inspection types (for lookup + LLM output constraint)
OUTCOMES = ("pass", "fail", "mixed", "unknown")

FINDING_CONFIDENCE_THRESHOLD = 0.70

KNOWN_INSPECTION_TYPES: List[str] = [
    "hvac",
    "electrical",
    "plumbing",
    "structural",
    "fire_protection",
    "roofing",
    "mep",
    "general",
]

# Lookup: trade or spec_section (normalized) -> inspection_type
# Trade takes precedence; spec_section prefix (e.g. "15830" from "15830 - HVAC Controls") matches
TRADE_TO_INSPECTION: Dict[str, str] = {
    "hvac": "hvac",
    "mechanical": "hvac",
    "electrical": "electrical",
    "plumbing": "plumbing",
    "structural": "structural",
    "concrete": "structural",
    "fire": "fire_protection",
    "fire protection": "fire_protection",
    "roofing": "roofing",
    "mep": "mep",
}
SPEC_PREFIX_TO_INSPECTION: Dict[str, str] = {
    "15830": "hvac",
    "15850": "hvac",
    "16000": "electrical",
    "16100": "electrical",
    "15400": "plumbing",
    "22000": "plumbing",
    "03300": "structural",
    "05100": "structural",
    "15300": "fire_protection",
    "07500": "roofing",
}


def _lookup_inspection_type_from_evidence(evidence: EvidenceRecord) -> Optional[str]:
    """
    Map evidence trade/spec_section to inspection_type via lookup table.
    Returns inspection_type or None if no match.
    """
    trade = (getattr(evidence, "trade", None) or "").strip().lower()
    spec = (getattr(evidence, "spec_section", None) or "").strip().lower()

    if trade and trade in TRADE_TO_INSPECTION:
        return TRADE_TO_INSPECTION[trade]

    if spec:
        spec_num = re.split(r"[\s\-]", spec)[0] if spec else ""
        if spec_num and spec_num in SPEC_PREFIX_TO_INSPECTION:
            return SPEC_PREFIX_TO_INSPECTION[spec_num]

    return None


def _classify_inspection_type_llm(
    title: str,
    trade: Optional[str],
    spec_section: Optional[str],
    text_preview: Optional[str],
) -> str:
    """
    LLM fallback: prompt to output one of KNOWN_INSPECTION_TYPES.
    Returns "unknown" if no API key or on error.
    """
    try:
        from config import settings
        from openai import OpenAI
    except ImportError:
        return "unknown"

    if not getattr(settings, "openai_api_key", None):
        return "unknown"

    client = OpenAI(api_key=settings.openai_api_key)
    types_str = ", ".join(KNOWN_INSPECTION_TYPES)
    hint = []
    if trade:
        hint.append(f"trade: {trade}")
    if spec_section:
        hint.append(f"spec_section: {spec_section}")
    hint_str = "; ".join(hint) if hint else "none"

    prompt = f"""Classify this inspection document into exactly one of these types: {types_str}.

Document title: {title}
Metadata: {hint_str}
{f'Text preview (first 500 chars): {text_preview[:500]}' if text_preview else ''}

Respond with only the type, e.g. hvac or electrical."""

    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=32,
        )
        raw = (resp.choices[0].message.content or "").strip().lower()
        for t in KNOWN_INSPECTION_TYPES:
            if t in raw or raw == t:
                return t
        return "unknown"
    except Exception as e:
        logger.warning("inspection_type_llm_failed", extra={"error": str(e)})
        return "unknown"


def _extract_outcomes_llm(
    title: str,
    inspection_type: str,
    text_content: Optional[str],
) -> tuple[str, str]:
    """
    Use LLM to extract outcome (pass/fail/mixed/unknown) and short notes from evidence.
    Returns (outcome, notes).
    """
    try:
        from config import settings
        from openai import OpenAI
    except ImportError:
        return "unknown", ""

    if not getattr(settings, "openai_api_key", None):
        return "unknown", ""

    client = OpenAI(api_key=settings.openai_api_key)
    text_preview = (text_content or "")[:2000]

    prompt = f"""Analyze this inspection document and determine the overall outcome.

Document title: {title}
Inspection type: {inspection_type}

Content:
{text_preview or '(No text content available)'}

Respond in exactly this format:
OUTCOME: <pass|fail|mixed|unknown>
NOTES: <short summary, 1-2 sentences>"""

    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        raw = (resp.choices[0].message.content or "").strip().lower()
        outcome = "unknown"
        for o in OUTCOMES:
            if f"outcome: {o}" in raw or raw.startswith(o):
                outcome = o
                break
        notes = ""
        if "notes:" in raw:
            notes = raw.split("notes:")[-1].strip().split("\n")[0].strip()[:500]
        return outcome, notes
    except Exception as e:
        logger.warning("extract_outcomes_llm_failed", extra={"error": str(e)})
        return "unknown", ""

def _should_create_finding(outcome: str, confidence: Optional[float]) -> bool:
    """
    Create a finding when:
    - outcome is fail
    - outcome is mixed
    - confidence is low
    """
    if outcome in ("fail", "mixed"):
        return True

    if confidence is not None and confidence < FINDING_CONFIDENCE_THRESHOLD:
        return True

    return False


def _create_and_persist_finding(
    db: Session,
    ctx: Dict[str, Any],
) -> Optional[Finding]:
    """
    Create a Finding when inspection outcome requires escalation.
    """
    run = ctx["run"]
    evidence = ctx.get("evidence")
    master_drawing = ctx["master_drawing"]
    inspection_result = ctx.get("inspection_result")

    if inspection_result is None:
        return None

    outcome = getattr(inspection_result, "outcome", "unknown") or "unknown"

    # MVP: confidence not yet extracted by LLM, so read from ctx if later added
    confidence = ctx.get("confidence")

    if not _should_create_finding(outcome, confidence):
        return None

    project_id = getattr(run, "project_id", None)
    if project_id is None:
        return None

    evidence_id = getattr(run, "evidence_id", None)
    master_drawing_id = cast(int, master_drawing.id)
    inspection_run_id = cast(int, run.id)
    notes = getattr(inspection_result, "notes", None)

    severity = "high" if outcome == "fail" else "medium"
    evidence_title = getattr(evidence, "title", None) if evidence else None
    drawing_name = getattr(master_drawing, "name", "drawing") or "drawing"
    title = f"Inspection failed: {evidence_title or drawing_name}"[:255]
    description = notes or f"Inspection result marked as {outcome}."
    affected_items = [f"Inspection run #{inspection_run_id}", f"Drawing #{master_drawing_id}"]

    storage = StorageService(db)
    finding = storage.create_finding(
        project_id=project_id,
        type="deviation",
        severity=severity,
        title=title,
        description=description,
        affected_items=affected_items,
        drawing_id=master_drawing_id,
    )
    return finding


def _attach_finding_to_overlays(
    db: Session,
    overlays: List[Any],
    finding: Optional[Finding],
) -> None:
    """
    Store finding linkage in drawing_overlays.meta.
    """
    if not overlays:
        return

    for overlay in overlays:
        current_meta = getattr(overlay, "meta", None) or {}
        if not isinstance(current_meta, dict):
            current_meta = {}

        current_meta["finding_created"] = finding is not None
        if finding is not None:
            current_meta["finding_id"] = getattr(finding, "id", None)

        overlay.meta = current_meta

    db.flush()


# ---------------------------------------------------------------------------
# Step 1 — Load Evidence + Master Drawing, Resolve File Paths
# ---------------------------------------------------------------------------


def _load_evidence_and_master(
    db: Session,
    run: InspectionRun,
) -> Dict[str, Any]:
    """
    Fetch InspectionRun (already passed), EvidenceRecord, Drawing.
    Resolve file paths via file_storage.get_file_path(storage_key).

    Returns dict:
      - run: InspectionRun
      - evidence: EvidenceRecord | None
      - master_drawing: Drawing
      - evidence_path: Path | None (resolved when evidence has storage_key)
      - master_drawing_path: Path | None (resolved when drawing has storage_key)
      - error: str | None (set on failure)
    """
    master_drawing_id = cast(int, run.master_drawing_id)
    evidence_id = getattr(run, "evidence_id", None)

    master_drawing = db.query(Drawing).filter(Drawing.id == master_drawing_id).first()
    if master_drawing is None:
        return {"run": run, "error": "Master drawing not found"}

    evidence: Optional[EvidenceRecord] = None
    if evidence_id is not None:
        evidence = db.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()

    evidence_path: Optional[Path] = None
    master_drawing_path: Optional[Path] = None

    if evidence is not None:
        evidence_key = getattr(evidence, "storage_key", None)
        if evidence_key:
            try:
                evidence_path = get_file_path(evidence_key)
            except Exception as e:
                return {
                    "run": run,
                    "evidence": evidence,
                    "master_drawing": master_drawing,
                    "error": f"Failed to resolve evidence file path: {e}",
                }

    master_key = getattr(master_drawing, "storage_key", None)
    if master_key:
        try:
            master_drawing_path = get_file_path(master_key)
        except Exception as e:
            return {
                "run": run,
                "evidence": evidence,
                "master_drawing": master_drawing,
                "evidence_path": evidence_path,
                "error": f"Failed to resolve master drawing file path: {e}",
            }

    return {
        "run": run,
        "evidence": evidence,
        "master_drawing": master_drawing,
        "evidence_path": evidence_path,
        "master_drawing_path": master_drawing_path,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Step 2 — Classify Inspection Type
# ---------------------------------------------------------------------------


def _classify_and_persist_inspection_type(
    db: Session,
    ctx: Dict[str, Any],
) -> str:
    """
    Classify inspection type via lookup (evidence trade/spec_section) or LLM fallback.
    Persist to inspection_runs.inspection_type.
    Returns the inspection_type string.
    """
    run = ctx["run"]
    evidence = ctx.get("evidence")

    # Run may already have override from request body
    existing = getattr(run, "inspection_type", None)
    if existing and str(existing).strip():
        inspection_type = str(existing).strip().lower()
        for k in KNOWN_INSPECTION_TYPES:
            if k == inspection_type or k in inspection_type:
                inspection_type = k
                break
    elif evidence is not None:
        inspection_type = _lookup_inspection_type_from_evidence(evidence)
        if inspection_type is None:
            title = getattr(evidence, "title", "") or ""
            trade = getattr(evidence, "trade", None)
            spec = getattr(evidence, "spec_section", None)
            text = getattr(evidence, "text_content", None)
            inspection_type = _classify_inspection_type_llm(title, trade, spec, text)
    else:
        inspection_type = "unknown"

    storage = StorageService(db)
    run_id = cast(int, run.id)
    storage.update_inspection_run_status(run_id, run.status, inspection_type=inspection_type)
    return inspection_type


# ---------------------------------------------------------------------------
# Step 3 — Extract Outcomes
# ---------------------------------------------------------------------------


def _extract_and_persist_outcomes(
    db: Session,
    ctx: Dict[str, Any],
) -> Optional[Any]:
    """
    Use LLM to extract outcome (pass/fail/mixed/unknown) and notes.
    Persist by creating inspection_results row.
    Returns the created InspectionResult or None.
    """
    run = ctx["run"]
    evidence = ctx.get("evidence")
    inspection_type = ctx.get("inspection_type", "unknown")

    if evidence is not None:
        title = getattr(evidence, "title", "") or ""
        text = getattr(evidence, "text_content", None)
        outcome, notes = _extract_outcomes_llm(title, inspection_type, text)
    else:
        outcome = "unknown"
        notes = "No evidence document linked"

    outcome = outcome if outcome in OUTCOMES else "unknown"

    storage = StorageService(db)
    run_id = cast(int, run.id)
    result = storage.create_inspection_result(run_id, outcome, notes=notes or None)
    return result


# ---------------------------------------------------------------------------
# Step 3b — Extract controlled-vocabulary tags from evidence text
# ---------------------------------------------------------------------------


def _extract_vocabulary_tags(ctx: Dict[str, Any]) -> list[ExtractedTerm]:
    """Parse evidence text_content for canonical inspection vocabulary."""
    evidence = ctx.get("evidence")
    if evidence is None:
        return []

    text = getattr(evidence, "text_content", None) or ""
    if not str(text).strip():
        return []

    return extract_terms(str(text), categories=_RESOLUTION_VOCAB_CATEGORIES)


def _vocabulary_meta(terms: list[ExtractedTerm]) -> Dict[str, Any]:
    """Serialize extracted terms for overlay meta."""
    if not terms:
        return {}
    return {
        "vocabulary_terms": [t.to_dict() for t in terms],
        "vocabulary_confidence": overall_confidence_label(terms),
    }


# ---------------------------------------------------------------------------
# Step 4 — Map Areas to Master Drawing Coordinates
# ---------------------------------------------------------------------------

# Unknown/unmapped geometry: full-page rect (normalized 0-1)
UNMAPPED_GEOMETRY: Dict[str, Any] = {
    "page": 1,
    "type": "rect",
    "x": 0.0,
    "y": 0.0,
    "width": 1.0,
    "height": 1.0,
    "label": "unmapped",
}


def _resolve_region_geometries(
    db: Session,
    master_drawing_id: int,
    evidence: Optional[EvidenceRecord],
) -> List[tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Resolve overlay geometries from drawing_regions via evidence metadata.

    Evidence meta may contain:
      - region_id: int → single region by id
      - region_ids: list[int] → multiple regions
      - region_label: str → single region by label (case-insensitive)

    Returns list of (geometry, meta). Meta includes "unmapped": True when no region matched.
    """
    meta: Dict[str, Any] = {}
    regions = (
        db.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == master_drawing_id)
        .all()
    )
    region_by_id = {cast(int, r.id): r for r in regions}
    region_by_label = {(getattr(r, "label", "") or "").strip().lower(): r for r in regions}
    out: List[tuple[Dict[str, Any], Dict[str, Any]]] = []

    if evidence is not None:
        ev_meta = getattr(evidence, "meta", None) or {}
        if not isinstance(ev_meta, dict):
            ev_meta = {}

        region_ids = ev_meta.get("region_ids")
        if isinstance(region_ids, list):
            for rid in region_ids:
                if rid in region_by_id:
                    reg = region_by_id[rid]
                    geom = reg.geometry
                    if isinstance(geom, dict):
                        out.append((dict(geom), dict(meta)))

        if not out:
            region_id = ev_meta.get("region_id")
            if region_id is not None and region_id in region_by_id:
                reg = region_by_id[region_id]
                geom = reg.geometry
                if isinstance(geom, dict):
                    out.append((dict(geom), dict(meta)))

        if not out:
            region_label = ev_meta.get("region_label")
            if region_label is not None:
                label_norm = str(region_label).strip().lower()
                if label_norm in region_by_label:
                    reg = region_by_label[label_norm]
                    geom = reg.geometry
                    if isinstance(geom, dict):
                        out.append((dict(geom), dict(meta)))

    if not out:
        meta["unmapped"] = True
        out.append((dict(UNMAPPED_GEOMETRY), meta))

    return out


def _map_and_persist_overlays(
    db: Session,
    ctx: Dict[str, Any],
) -> List[Any]:
    """
    Map areas to master drawing coords via drawing_regions (or unmapped fallback).
    Persist one or more drawing_overlays rows.
    Returns list of created DrawingOverlay.
    """
    run = ctx["run"]
    master_drawing = ctx["master_drawing"]
    evidence = ctx.get("evidence")
    inspection_result = ctx.get("inspection_result")

    master_drawing_id = cast(int, master_drawing.id)
    run_id = cast(int, run.id)

    status = (
        getattr(inspection_result, "outcome", "unknown")
        if inspection_result is not None
        else "unknown"
    )
    if status not in ("pass", "fail", "unknown"):
        status = "unknown"

    vocabulary_terms = ctx.get("vocabulary_terms") or []
    vocab_meta = _vocabulary_meta(vocabulary_terms)

    geometries_and_meta = _resolve_region_geometries(db, master_drawing_id, evidence)
    storage = StorageService(db)
    overlays: List[Any] = []
    for geometry, meta in geometries_and_meta:
        if vocab_meta:
            meta = {**meta, **vocab_meta}
        overlay = storage.create_drawing_overlay(
            master_drawing_id,
            geometry,
            status,
            meta=meta or None,
            inspection_run_id=run_id,
        )
        overlays.append(overlay)
    return overlays


# ---------------------------------------------------------------------------
# Main Pipeline (Steps 1 + 2 + 3 + 4 + 5)
# ---------------------------------------------------------------------------


def run_inspection_mapping(db: Session, run: InspectionRun) -> Dict[str, Any]:
    """
    Run inspection mapping pipeline.

    Step 1: Load evidence + master drawing, resolve file paths.
    Step 2: Classify inspection type (lookup or LLM), persist to inspection_runs.inspection_type.
    Step 3: Extract outcomes (LLM), persist inspection_results row.
    Step 4: Map areas to master coords via drawing_regions, persist drawing_overlays.
    Step 5: Create finding when outcome is fail/mixed; attach finding_id to overlay meta.
    Step 6: Update run status (processing → complete/failed), started_at, completed_at, error_message.

    Returns dict with:
      - run, evidence, master_drawing (loaded records)
      - evidence_path, master_drawing_path (resolved Paths when storage_key present)
      - inspection_type (str, after classification)
      - inspection_result (created row)
      - drawing_overlays (list of created overlay rows)
      - finding (created when outcome fail/mixed, else None)
      - error (str | None, set on failure)
    """
    storage = StorageService(db)
    run_id = cast(int, run.id)
    now = datetime.now(timezone.utc)

    def _mark_failed(err: str) -> None:
        """Update run status to failed. Must not raise so request does not crash."""
        try:
            storage.update_inspection_run_status(
                run_id,
                "failed",
                completed_at=datetime.now(timezone.utc),
                error_message=err,
            )
        except Exception as status_err:
            logger.exception(
                "inspection_mapping_status_update_failed",
                extra={"run_id": run_id, "original_error": err},
            )

    try:
        # Step 6 — Start: status = processing, started_at
        storage.update_inspection_run_status(
            run_id,
            "processing",
            started_at=now,
        )

        ctx = _load_evidence_and_master(db, run)
        if ctx.get("error"):
            _mark_failed(ctx["error"])
            return ctx

        inspection_type = _classify_and_persist_inspection_type(db, ctx)
        ctx["inspection_type"] = inspection_type

        result = _extract_and_persist_outcomes(db, ctx)
        ctx["inspection_result"] = result

        vocabulary_terms = _extract_vocabulary_tags(ctx)
        ctx["vocabulary_terms"] = vocabulary_terms
        if vocabulary_terms:
            ctx["confidence"] = min(t.confidence_score for t in vocabulary_terms)

        overlays = _map_and_persist_overlays(db, ctx)
        ctx["drawing_overlays"] = overlays

        finding = _create_and_persist_finding(db, ctx)
        ctx["finding"] = finding

        _attach_finding_to_overlays(db, overlays, finding)

        # Step 6 — Success: status = complete, completed_at
        storage.update_inspection_run_status(
            run_id,
            "complete",
            completed_at=datetime.now(timezone.utc),
        )

        return ctx

    except Exception as e:
        logger.exception(
            "inspection_mapping_pipeline_failed",
            extra={"run_id": run_id},
        )
        _mark_failed(str(e))
        return {"run": run, "error": str(e)}
