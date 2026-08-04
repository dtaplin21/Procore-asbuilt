"""Expand construction clues into common drawing abbreviations and related search terms."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

EXPANSIONS = {
    "sanitary sewerage": ["sanitary sewer", "sanitary", "sewer", "SS", "SAN", "sewer lateral"],
    "sanitary sewer": ["SS", "SAN", "sewer lateral", "cleanout", "manhole"],
    "manhole": ["MH", "M.H."],
    "cleanout": ["CO", "C.O."],
    "storm drainage": ["storm drain", "SD", "storm"],
    "parking lot": ["lot", "pavement", "asphalt", "parking"],
    "colo": ["Colo", "COLO parking lot", "colocated", "colocation"],
    "utility line": ["utility", "util line"],
    "trench": ["utility trench", "excavation"],
}


def expand_clue_value(
    value: str,
    *,
    session: Session | None = None,
    project_id: int | None = None,
) -> list[str]:
    if not value:
        return []

    normalized = value.lower()
    expanded = [value]

    for key, terms in EXPANSIONS.items():
        if key in normalized:
            expanded.extend(terms)

    if session is not None:
        from services.legend_lookup import expand_abbreviation, find_codes_for_term

        if len(value.split()) > 1:
            expanded.extend(find_codes_for_term(session, value, project_id))
        else:
            expansion = expand_abbreviation(session, value, project_id)
            if expansion:
                expanded.append(expansion)

    seen: set[str] = set()
    result: list[str] = []

    for term in expanded:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            result.append(term)

    return result
