"""Extract the date the INSPECTION was performed, as stated in document
text — distinct from when the file was uploaded to our system (that's
tracked separately as `uploaded_at`, set automatically at upload time;
see backend/models/drawing_overlay.py and inspection_mapping.py).

Strategy, in order:
  1. Look for an explicit label ("Inspection date:", "Date of
     inspection:", "Inspected on", "Date:") and take the date
     immediately following it. This is the most precise signal — it
     won't mistake an unrelated date (e.g. "next re-inspection scheduled
     for...") for the inspection date.
  2. If no labeled date is found, fall back to the FIRST recognizable
     date anywhere in the document. Most inspection forms state their
     date near the top even without an exact label phrase, and a
     conservative "give up and return None" default would silently miss
     a large share of real documents that don't happen to use one of a
     few exact label strings.

Recognizes: ISO (2026-06-24), slash-numeric (06/24/2026 or 6/24/26),
dash-numeric (06-24-2026), and written month-name dates in either order
("June 24, 2026" or "24 June 2026"), including abbreviated months and
ordinal suffixes ("24th").

Self-contained: stdlib `re` and `datetime` only.
"""

from __future__ import annotations

import re
from datetime import date

from ai.pipelines.document_text_extraction import ExtractedDocument

_MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_PATTERN = "|".join(sorted(_MONTH_NAMES.keys(), key=len, reverse=True))

# --- Labeled-anchor patterns (tried first, for precision) ------------------
_INSPECTION_DATE_ANCHOR = re.compile(
    r"(?:inspection\s+date|date\s+of\s+inspection|inspected\s+on|inspection\s+on)"
    r"\s*[:\-]?\s*",
    re.IGNORECASE,
)
_DATE_LABEL = re.compile(r"\bdate\s*:\s*", re.IGNORECASE)

# --- Date format patterns (tried in this order, both for anchored and
# fallback search) -----------------------------------------------------
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_DASH_DATE = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{2,4})\b")
_MONTH_DAY_YEAR = re.compile(
    rf"\b({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_DAY_MONTH_YEAR = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_PATTERN})\.?,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)


def _normalize_two_digit_year(year: int) -> int:
    """00-69 -> 2000-2069, 70-99 -> 1970-1999 (standard pivot-year rule)."""
    if year >= 100:
        return year
    return 2000 + year if year <= 69 else 1900 + year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _try_iso(text: str) -> tuple[date, re.Match] | None:
    m = _ISO_DATE.search(text)
    if not m:
        return None
    d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (d, m) if d else None


def _try_slash(text: str) -> tuple[date, re.Match] | None:
    m = _SLASH_DATE.search(text)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    year = _normalize_two_digit_year(int(m.group(3)))
    d = _safe_date(year, month, day)
    return (d, m) if d else None


def _try_dash(text: str) -> tuple[date, re.Match] | None:
    m = _DASH_DATE.search(text)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    year = _normalize_two_digit_year(int(m.group(3)))
    d = _safe_date(year, month, day)
    return (d, m) if d else None


def _try_month_day_year(text: str) -> tuple[date, re.Match] | None:
    m = _MONTH_DAY_YEAR.search(text)
    if not m:
        return None
    month = _MONTH_NAMES[m.group(1).lower()]
    day, year = int(m.group(2)), int(m.group(3))
    d = _safe_date(year, month, day)
    return (d, m) if d else None


def _try_day_month_year(text: str) -> tuple[date, re.Match] | None:
    m = _DAY_MONTH_YEAR.search(text)
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTH_NAMES[m.group(2).lower()]
    year = int(m.group(3))
    d = _safe_date(year, month, day)
    return (d, m) if d else None


# Order matters: ISO is unambiguous and tried first; numeric slash/dash
# next; written month-name formats last (they're the least likely to
# false-positive against unrelated numbers, so trying them last is safe).
_FORMAT_TRIES = (_try_iso, _try_slash, _try_dash, _try_month_day_year, _try_day_month_year)


def _first_date_in_span(text: str) -> date | None:
    """Try every format against `text`, return the EARLIEST match across
    all formats (not just the first format that happens to match) —
    important because e.g. a slash-date could appear before an ISO date
    in the same span.
    """
    candidates: list[tuple[int, date]] = []
    for fn in _FORMAT_TRIES:
        result = fn(text)
        if result is not None:
            d, m = result
            candidates.append((m.start(), d))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


def extract_primary_date(text: str) -> date | None:
    """Return the date the inspection was performed, if findable in the
    document text. None if no recognizable date is present anywhere —
    never guessed from the upload time or any other source.
    """
    if not text or not text.strip():
        return None

    # Step 1: precise, labeled search.
    for anchor in (_INSPECTION_DATE_ANCHOR, _DATE_LABEL):
        for match in anchor.finditer(text):
            window = text[match.end(): match.end() + 48]
            candidate = _first_date_in_span(window)
            if candidate is not None:
                return candidate

    # Step 2: fall back to the first date anywhere in the document.
    return _first_date_in_span(text)


def extract_inspection_date(document: ExtractedDocument | str) -> date | None:
    """Convenience wrapper accepting either an ExtractedDocument or raw
    text — matches the call signature used elsewhere in this pipeline.
    """
    text = document.full_text() if isinstance(document, ExtractedDocument) else document
    return extract_primary_date(text)
