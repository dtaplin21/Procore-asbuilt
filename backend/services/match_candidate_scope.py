"""Narrow inspection match search using sheet cross-references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy.orm import Session

from models.models import EvidenceDrawingLink, EvidenceRecord
from services.evidence_linking import extract_sheet_refs, find_project_drawings_for_refs
from services.evidence_text import build_full_evidence_text


@dataclass(frozen=True)
class MatchScope:
    master_drawing_id: int
    auxiliary_drawing_ids: tuple[int, ...]
    preferred_pages: tuple[int, ...]
    sheet_refs: tuple[str, ...]


def build_match_scope(
    session: Session,
    *,
    evidence_id: int,
    master_drawing_id: int,
) -> MatchScope:
    evidence = session.get(EvidenceRecord, evidence_id)
    refs: list[str] = []
    auxiliary: list[int] = []

    if evidence is not None:
        refs = extract_sheet_refs(build_full_evidence_text(evidence))
        project_id = cast(int, evidence.project_id)
        for match in find_project_drawings_for_refs(session, project_id, refs):
            auxiliary.append(int(match["drawing_id"]))

        linked_rows = (
            session.query(EvidenceDrawingLink)
            .filter(EvidenceDrawingLink.evidence_id == evidence_id)
            .all()
        )
        for link in linked_rows:
            auxiliary.append(cast(int, link.drawing_id))

    auxiliary_ids = tuple(
        drawing_id
        for drawing_id in dict.fromkeys(auxiliary)
        if drawing_id != master_drawing_id
    )

    return MatchScope(
        master_drawing_id=master_drawing_id,
        auxiliary_drawing_ids=auxiliary_ids,
        preferred_pages=(1,),
        sheet_refs=tuple(refs),
    )
