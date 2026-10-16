"""Evidence text helpers for full-document scans and model reasoning."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from models.document_clue import DocumentClue
    from ai.agents.evidence_dossier import LinkedAttachmentSummary

_STATION_RE = re.compile(r"\b\d{1,2}\+\d{2}(?:\.\d+)?\b", re.IGNORECASE)
_COORD_RE = re.compile(
    r"\b(?:N\s*[=:]?\s*\d|NORTHING|E\s*[=:]?\s*\d|EASTING|LAT\s|LONG\s|\d{6,7}\.\d{2,})\b",
    re.IGNORECASE,
)
_LOCATION_KEYWORDS = (
    "sewer",
    "sanitary",
    "ssmh",
    "manhole",
    "station",
    "sta.",
    "install",
    "trench",
    "profile",
    "plan",
    "drawing",
    "sheet",
    "c4.20",
    "umr",
    "underground",
    "hardscape",
    "drainage",
)
_DEFAULT_REASONING_MAX_CHARS = 12_000
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


def build_full_evidence_text(evidence: Any) -> str:
    """Return merged evidence text without truncation."""
    return (getattr(evidence, "text_content", None) or "").strip()


def build_location_reasoning_excerpt(
    full_text: str,
    *,
    clues: Sequence[Any] = (),
    linked_attachments: Sequence[Any] = (),
    max_chars: int = _DEFAULT_REASONING_MAX_CHARS,
) -> str:
    """Build a location-focused excerpt for LLM/vision prompts (not the raw doc header).

    Prefer paragraphs that mention stations, coordinates, sewer/install language, and
    linked attachment previews over the first N characters of the merged corpus.
    """
    stripped = (full_text or "").strip()
    if not stripped:
        return ""

    sections: list[str] = []

    clue_lines: list[str] = []
    for clue in clues:
        clue_type = str(getattr(clue, "clue_type", "") or "")
        value = str(getattr(clue, "clue_value", "") or "").strip()
        if value:
            clue_lines.append(f"{clue_type}: {value}")
    if clue_lines:
        sections.append("Extracted clues:\n" + "\n".join(f"- {line}" for line in clue_lines[:40]))

    attachment_lines: list[str] = []
    for attachment in linked_attachments:
        filename = str(getattr(attachment, "filename", "") or "")
        preview = str(getattr(attachment, "text_preview", "") or "").strip()
        if filename:
            line = f"{filename}"
            if preview:
                line += f": {preview[:1200]}"
            attachment_lines.append(line)
    if attachment_lines:
        sections.append(
            "Linked inspection files:\n" + "\n".join(f"- {line}" for line in attachment_lines[:25])
        )

    scored_paragraphs: list[tuple[int, str]] = []
    for paragraph in _PARAGRAPH_SPLIT.split(stripped):
        chunk = paragraph.strip()
        if len(chunk) < 24:
            continue
        score = _location_paragraph_score(chunk)
        if score > 0:
            scored_paragraphs.append((score, chunk))

    scored_paragraphs.sort(key=lambda item: (-item[0], -len(item[1])))
    body_parts: list[str] = []
    used = sum(len(s) for s in sections) + 2
    for _score, paragraph in scored_paragraphs:
        if used + len(paragraph) + 2 > max_chars:
            remaining = max_chars - used - 20
            if remaining > 200:
                body_parts.append(paragraph[:remaining] + "…")
            break
        body_parts.append(paragraph)
        used += len(paragraph) + 2

    if body_parts:
        sections.append("Location-relevant excerpts:\n" + "\n\n".join(body_parts))

    if not sections:
        return stripped[:max_chars]

    combined = "\n\n".join(sections)
    if len(combined) <= max_chars:
        return combined
    return combined[: max_chars - 1] + "…"


def _location_paragraph_score(paragraph: str) -> int:
    upper = paragraph.upper()
    score = 0
    if _STATION_RE.search(paragraph):
        score += 50
    if _COORD_RE.search(paragraph):
        score += 40
    for keyword in _LOCATION_KEYWORDS:
        if keyword.upper() in upper:
            score += 8
    if "--- Linked content" in paragraph:
        score += 30
    if score == 0 and len(paragraph) > 400:
        score = 1
    return score
