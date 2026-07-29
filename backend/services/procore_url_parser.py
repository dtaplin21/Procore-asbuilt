"""Extract Procore entity IDs from URLs embedded in PDF hyperlinks.

Many Procore links carry location, drawing, or inspection IDs in the path or query
even when the HTML page requires login. No OAuth is needed for this parsing step.

Numeric location IDs are stored in ``cross_refs_json`` for a future Procore API
lookup phase. Short location codes (e.g. ``COLO``) can feed the clue pipeline
directly via optional ``clue_hint`` entries (v1.5).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

LOCATION_PATTERNS = [
    re.compile(r"/projects/\d+/locations/([^/?#]+)", re.I),
    re.compile(r"location_id=(\d+)", re.I),
]


def parse_procore_url(url: str) -> dict | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None

    for pat in LOCATION_PATTERNS:
        match = pat.search(url)
        if match:
            return {
                "kind": "procore_location",
                "value": match.group(1),
                "uri": url,
            }

    # Try drawing/sheet refs in query or fragment
    # Try inspection ID if present
    return None


def build_procore_cross_ref(
    parsed: dict,
    *,
    source_page: int | None = None,
    anchor_text: str | None = None,
) -> dict:
    """Shape a parsed Procore ref for ``EvidenceRecord.cross_refs_json`` storage."""
    cross_ref = dict(parsed)
    if source_page is not None:
        cross_ref["source_page"] = source_page
    if anchor_text:
        cross_ref["anchor_text"] = anchor_text

    value = str(cross_ref.get("value") or "")
    if cross_ref.get("kind") == "procore_location":
        cross_ref["resolve_via_api"] = _is_numeric_id(value)
        clue_hint = clue_hint_from_procore_ref(parsed)
        if clue_hint is not None:
            cross_ref["clue_hint"] = clue_hint

    return cross_ref


def clue_hint_from_procore_ref(parsed: dict) -> dict | None:
    """Optional v1.5: location codes usable as matching clues without API lookup."""
    if parsed.get("kind") != "procore_location":
        return None

    value = str(parsed.get("value") or "").strip()
    if not value or _is_numeric_id(value):
        return None

    return {
        "type": "location_code",
        "value": value,
        "source": "procore_url",
    }


def _is_numeric_id(value: str) -> bool:
    return value.isdigit()
