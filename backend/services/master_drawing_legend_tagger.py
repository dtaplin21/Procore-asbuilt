"""Legend enrichment for indexed master drawing text elements (Phase 4)."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from models.drawing_text_element import DrawingTextElement
from services.legend_lookup import expand_abbreviation, find_codes_for_term

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/]*$")


def is_single_token(text: str) -> bool:
    stripped = text.strip()
    if not stripped or " " in stripped:
        return False
    return bool(_TOKEN_RE.match(stripped))


def legend_tags_for_text_element(row: DrawingTextElement) -> list[str]:
    """Searchable tag strings derived from a text element's legend fields."""
    tags: set[str] = set()
    text = str(row.text).strip()
    if text:
        tags.add(text.upper())

    expansion = row.legend_expansion
    if isinstance(expansion, str) and expansion.strip():
        tags.add(expansion.strip().upper())

    codes = row.legend_codes_json
    if isinstance(codes, list):
        for code in codes:
            code_text = str(code).strip()
            if code_text:
                tags.add(code_text.upper())

    return sorted(tags)


def enrich_text_element(
    session: Session,
    row: DrawingTextElement,
    *,
    project_id: int | None,
) -> bool:
    """Apply legend lookup to one persisted text element. Returns True if enriched."""
    text = str(row.text).strip()
    if not text:
        return False

    expansion: str | None = None
    codes: list[str] = []

    if is_single_token(text):
        expansion = expand_abbreviation(session, text, project_id)
        if expansion:
            codes = find_codes_for_term(session, expansion, project_id)
            token_upper = text.upper()
            if token_upper not in codes:
                codes = sorted({token_upper, *codes})
    else:
        codes = find_codes_for_term(session, text, project_id)

    changed = False
    if expansion:
        row.legend_expansion = expansion  # type: ignore[assignment]
        changed = True
    if codes:
        row.legend_codes_json = codes  # type: ignore[assignment]
        changed = True

    return changed


def enrich_text_elements_with_legend(
    session: Session,
    drawing_id: int,
    project_id: int | None,
) -> int:
    """Tag all text elements for a drawing using project/global legend reference."""
    rows = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .order_by(DrawingTextElement.id.asc())
        .all()
    )

    enriched = 0
    for row in rows:
        if enrich_text_element(session, row, project_id=project_id):
            enriched += 1

    if enriched:
        session.flush()
    return enriched
