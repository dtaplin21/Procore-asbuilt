"""
Inspection mapping pipeline.

Extracts inspection outcomes from evidence docs, maps areas onto the master drawing,
and creates overlays + inspection results.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional, cast

from models.models import Drawing, EvidenceRecord, InspectionRun
from services.file_storage import get_file_path
from services.storage import StorageService

logger = logging.getLogger(__name__)

# Known inspection types (for lookup + LLM output constraint)
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
            model="gpt-4o-mini",
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
# Main Pipeline (Steps 1 + 2)
# ---------------------------------------------------------------------------


def run_inspection_mapping(db: Session, run: InspectionRun) -> Dict[str, Any]:
    """
    Run inspection mapping pipeline.

    Step 1: Load evidence + master drawing, resolve file paths.
    Step 2: Classify inspection type (lookup or LLM), persist to inspection_runs.inspection_type.

    Returns dict with:
      - run, evidence, master_drawing (loaded records)
      - evidence_path, master_drawing_path (resolved Paths when storage_key present)
      - inspection_type (str, after classification)
      - error (str | None, set on failure)
    """
    ctx = _load_evidence_and_master(db, run)
    if ctx.get("error"):
        return ctx

    inspection_type = _classify_and_persist_inspection_type(db, ctx)
    ctx["inspection_type"] = inspection_type
    return ctx
