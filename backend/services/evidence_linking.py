import re
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from models.models import Drawing, EvidenceRecord, EvidenceDrawingLink


# C-101 / C101 (legacy) and Procore-style C4.20, U1.C4.20
SHEET_REF_PATTERNS = (
    re.compile(r"\b([A-Z]{1,3}-?\d{2,4}[A-Z]?)\b", re.IGNORECASE),
    re.compile(r"\b((?:[A-Z]\d+\.)?[A-Z]\d+\.\d{2,4})\b", re.IGNORECASE),
)
_AUTO_LINK_SOURCES = ("regex", "pdf_link")


def load_linked_drawings(session: Session, evidence_id: int) -> list[Drawing]:
    links = (
        session.query(EvidenceDrawingLink)
        .filter(EvidenceDrawingLink.evidence_id == evidence_id)
        .all()
    )
    drawings: list[Drawing] = []
    seen: set[int] = set()
    for link in links:
        drawing_id = cast(int, link.drawing_id)
        if drawing_id in seen:
            continue
        seen.add(drawing_id)
        drawing = session.get(Drawing, drawing_id)
        if drawing is not None:
            drawings.append(drawing)
    return drawings


def extract_sheet_refs(text: Optional[str]) -> List[str]:
    if not text:
        return []

    normalized: List[str] = []
    seen: set[str] = set()

    for pattern in SHEET_REF_PATTERNS:
        for match in pattern.findall(text):
            ref = match.upper().replace(" ", "")
            if ref not in seen:
                seen.add(ref)
                normalized.append(ref)

    return normalized


def _normalize_name(value: str) -> str:
    return value.upper().replace(" ", "").replace("_", "").replace("-", "").strip()


def find_project_drawings_for_refs(
    db: Session,
    project_id: int,
    refs: List[str],
) -> List[Dict[str, Any]]:
    drawings = db.query(Drawing).filter(Drawing.project_id == project_id).all()
    matches: List[Dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    for drawing in drawings:
        name_raw = cast(Optional[str], drawing.name)
        filename_raw = cast(Optional[str], getattr(drawing, "original_filename", None))
        haystacks = [
            _normalize_name(name_raw or ""),
            _normalize_name(filename_raw or ""),
        ]
        for ref in refs:
            normalized_ref = _normalize_name(ref)
            if not normalized_ref:
                continue
            if not any(
                haystack and (normalized_ref in haystack or haystack.startswith(normalized_ref))
                for haystack in haystacks
            ):
                continue
            key = (cast(int, drawing.id), ref)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                {
                    "drawing_id": cast(int, drawing.id),
                    "drawing_name": name_raw,
                    "matched_text": ref,
                    "confidence": 0.9,
                    "source": "regex",
                    "link_type": "sheet_ref",
                }
            )
    return matches


def find_drawing_links_from_cross_refs(
    db: Session,
    project_id: int,
    cross_refs: List[Any],
) -> List[Dict[str, Any]]:
    """Resolve PDF link cross-refs to project drawings when possible."""
    matches: List[Dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()

    for entry in cross_refs:
        if not isinstance(entry, dict):
            continue

        kind = entry.get("kind")
        value = str(entry.get("value") or "").strip()
        if not value:
            continue

        if kind == "sheet_ref":
            link_type = "sheet_ref"
            refs = [value]
        elif kind == "procore_location" and not value.isdigit():
            link_type = "procore_location"
            refs = [value]
        else:
            continue

        for match in find_project_drawings_for_refs(db, project_id, refs):
            key = (match["drawing_id"], link_type, match["matched_text"])
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                {
                    **match,
                    "source": "pdf_link",
                    "link_type": link_type,
                }
            )

    return matches


def replace_evidence_drawing_links(
    db: Session,
    evidence: EvidenceRecord,
    *,
    commit: bool = True,
) -> List[EvidenceDrawingLink]:
    refs = extract_sheet_refs(cast(Optional[str], evidence.text_content))
    regex_matches = find_project_drawings_for_refs(
        db, cast(int, evidence.project_id), refs
    )

    cross_raw = cast(Optional[List[Any]], evidence.cross_refs_json)
    cross_refs = list(cross_raw or [])
    pdf_matches = find_drawing_links_from_cross_refs(
        db, cast(int, evidence.project_id), cross_refs
    )

    # merge sheet_refs into existing cross_refs_json (preserve rfi_number, etc.)
    existing = list(cross_raw or [])
    non_sheet = [c for c in existing if isinstance(c, dict) and c.get("kind") != "sheet_ref"]
    new_sheet_refs = [{"kind": "sheet_ref", "value": ref} for ref in refs]
    evidence.cross_refs_json = non_sheet + new_sheet_refs  # type: ignore[assignment]

    old_links = (
        db.query(EvidenceDrawingLink)
        .filter(
            EvidenceDrawingLink.evidence_id == evidence.id,
            EvidenceDrawingLink.source.in_(_AUTO_LINK_SOURCES),
        )
        .all()
    )
    for link in old_links:
        db.delete(link)

    db.flush()

    created_links: List[EvidenceDrawingLink] = []
    seen_pairs = set()

    for match in regex_matches + pdf_matches:
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

    if commit:
        db.commit()
        for link in created_links:
            db.refresh(link)
        db.refresh(evidence)
    else:
        db.flush()

    return created_links
