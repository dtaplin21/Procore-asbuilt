"""Expand construction clues into common drawing abbreviations and related search terms."""

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


def expand_clue_value(value: str) -> list[str]:
    if not value:
        return []

    normalized = value.lower()
    expanded = [value]

    for key, terms in EXPANSIONS.items():
        if key in normalized:
            expanded.extend(terms)

    seen = set()
    result: list[str] = []

    for term in expanded:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            result.append(term)

    return result
