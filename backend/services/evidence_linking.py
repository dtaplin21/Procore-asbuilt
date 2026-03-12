import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models.models import Drawing, EvidenceRecord, EvidenceDrawingLink


SHEET_REF_PATTERN = re.compile(r"\b([A-Z]{1,3}-?\d{2,4}[A-Z]?)\b", re.IGNORECASE)


def extract_sheet_refs(text: Optional[str]) -> List[str]:
    if not text:
        return []

    matches = SHEET_REF_PATTERN.findall(text)
    normalized: List[str] = []
    seen = set()

    for match in matches:
        ref = match.upper().replace(" ", "")
        if ref not in seen:
            seen.add(ref)
            normalized.append(ref)

    return normalized


def _normalize_name(value: str) -> str:
    return value.upper().replace(" ", "").replace("_", "").strip()


def find_project_drawings_for_refs(
    db: Session,
    project_id: int,
    refs: List[str],
) -> List[Dict[str, Any]]:
    drawings = db.query(Drawing).filter(Drawing.project_id == project_id).all()
    matches: List[Dict[str, Any]] = []

    for drawing in drawings:
        drawing_name = _normalize_name(drawing.name or "")
        for ref in refs:
            normalized_ref = _normalize_name(ref)
            if normalized_ref in drawing_name or drawing_name.startswith(normalized_ref):
                matches.append(
                    {
                        "drawing_id": drawing.id,
                        "drawing_name": drawing.name,
                        "matched_text": ref,
                        "confidence": 0.9,
                        "source": "regex",
                        "link_type": "sheet_ref",
                    }
                )
    return matches


def replace_evidence_drawing_links(
    db: Session,
    evidence: EvidenceRecord,
) -> List[EvidenceDrawingLink]:
    refs = extract_sheet_refs(evidence.text_content)
    matches = find_project_drawings_for_refs(db, evidence.project_id, refs)

    # merge sheet_refs into existing cross_refs_json (preserve rfi_number, etc.)
    existing = list(evidence.cross_refs_json or [])
    non_sheet = [c for c in existing if isinstance(c, dict) and c.get("kind") != "sheet_ref"]
    new_sheet_refs = [{"kind": "sheet_ref", "value": ref} for ref in refs]
    evidence.cross_refs_json = non_sheet + new_sheet_refs

    # remove old auto-generated regex links
    old_links = (
        db.query(EvidenceDrawingLink)
        .filter(
            EvidenceDrawingLink.evidence_id == evidence.id,
            EvidenceDrawingLink.source == "regex",
        )
        .all()
    )
    for link in old_links:
        db.delete(link)

    db.flush()

    created_links: List[EvidenceDrawingLink] = []
    seen_pairs = set()

    for match in matches:
        pair = (evidence.id, match["drawing_id"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        link = EvidenceDrawingLink(
            project_id=evidence.project_id,
            evidence_id=evidence.id,
            drawing_id=match["drawing_id"],
            link_type=match["link_type"],
            matched_text=match["matched_text"],
            confidence=match["confidence"],
            source=match["source"],
            is_primary=False,
        )
        db.add(link)
        created_links.append(link)

    db.add(evidence)
    db.commit()

    for link in created_links:
        db.refresh(link)
    db.refresh(evidence)

    return created_links
