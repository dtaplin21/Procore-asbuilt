"""Expands abbreviations to canonical terms and vice versa, using the seeded legend
data. Used by clue expansion / candidate matching to widen search terms so
'sanitary sewer' in an inspection matches 'SS' on a drawing, and an OCR'd 'FDC'
token resolves to 'fire department connection' for candidate scoring.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from models.legend_reference import (
    DrawingLegendAbbreviation,
    DrawingLegendLineType,
    DrawingLegendSymbol,
)


def expand_abbreviation(
    session: Session,
    token: str,
    project_id: int | None = None,
) -> Optional[str]:
    """``SS`` -> ``SANITARY SEWER``. Checks project-specific override first, falls back
    to the general/global entry (``project_id IS NULL``)."""
    token_clean = token.strip().upper()
    if not token_clean:
        return None

    row = None
    if project_id is not None:
        row = (
            session.query(DrawingLegendAbbreviation)
            .filter(
                DrawingLegendAbbreviation.abbreviation == token_clean,
                DrawingLegendAbbreviation.project_id == project_id,
            )
            .one_or_none()
        )
    if row is None:
        row = (
            session.query(DrawingLegendAbbreviation)
            .filter(
                DrawingLegendAbbreviation.abbreviation == token_clean,
                DrawingLegendAbbreviation.project_id.is_(None),
            )
            .one_or_none()
        )

    return str(row.expansion) if row is not None else None


def _abbreviation_code(row: object) -> str | None:
    code = getattr(row, "abbreviation_code", None)
    if code is None:
        return None
    return str(code)


def find_codes_for_term(
    session: Session,
    term: str,
    project_id: int | None = None,
) -> List[str]:
    """``sanitary sewer`` -> ``['SS', 'SSMH', 'SSCO', ...]``. Searches abbreviations,
    line types, and symbols whose expansion/name contains the term."""
    term_lower = term.strip().lower()
    if not term_lower:
        return []

    codes: set[str] = set()

    abbrev_query = session.query(DrawingLegendAbbreviation)
    if project_id is not None:
        abbrev_query = abbrev_query.filter(
            (DrawingLegendAbbreviation.project_id == project_id)
            | (DrawingLegendAbbreviation.project_id.is_(None))
        )
    else:
        abbrev_query = abbrev_query.filter(DrawingLegendAbbreviation.project_id.is_(None))

    for row in abbrev_query.all():
        expansion_lower = str(row.expansion).strip().lower()
        if not expansion_lower:
            continue
        if term_lower in expansion_lower or expansion_lower in term_lower:
            codes.add(str(row.abbreviation))

    line_type_query = session.query(DrawingLegendLineType)
    if project_id is not None:
        line_type_query = line_type_query.filter(
            (DrawingLegendLineType.project_id == project_id)
            | (DrawingLegendLineType.project_id.is_(None))
        )
    else:
        line_type_query = line_type_query.filter(DrawingLegendLineType.project_id.is_(None))

    for row in line_type_query.all():
        line_name_lower = str(row.line_type_name).strip().lower()
        if term_lower in line_name_lower or line_name_lower in term_lower:
            code = _abbreviation_code(row)
            if code is not None:
                codes.add(code)

    symbol_query = session.query(DrawingLegendSymbol)
    if project_id is not None:
        symbol_query = symbol_query.filter(
            (DrawingLegendSymbol.project_id == project_id)
            | (DrawingLegendSymbol.project_id.is_(None))
        )
    else:
        symbol_query = symbol_query.filter(DrawingLegendSymbol.project_id.is_(None))

    for row in symbol_query.all():
        symbol_name_lower = str(row.symbol_name).strip().lower()
        if term_lower in symbol_name_lower or symbol_name_lower in term_lower:
            code = _abbreviation_code(row)
            if code is not None:
                codes.add(code)

    return sorted(codes)
