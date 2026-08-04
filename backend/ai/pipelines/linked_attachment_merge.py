"""Merges OCR'd linked-attachment content into the text handed to the classifier/

extractor pipeline, within a fixed word budget.

Bug this fixes: the previous behavior accepted attachments in fetch order and
dropped everything once a size cap was hit. A large boilerplate document (a
78-page product submittal) fetched first could consume the entire budget,
silently excluding a small, highly relevant document (a 2-page install drawing
with station numbers and coordinates) fetched afterward. See
pdf_link_supplemental_truncated in the old flow.

Fix: rank attachments by a relevance heuristic first (filename signal + inverse
size), then fill the budget in that order. An attachment is only truncated if it
doesn't fully fit in what's left of the budget — it is never dropped in favor of
a lower-priority attachment that happened to be processed earlier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Word budget for combined linked-attachment content. This is a word count, not a
# token count -- ADAPT: if your model client meters by tokens, convert with a
# rough words-to-tokens multiplier (~1.3) or swap in your tokenizer's count
# function inside merge_linked_attachments_within_budget below.
LINKED_CONTENT_WORD_BUDGET = 6000

# Filenames matching these patterns get priority: these attachment types are the
# ones most likely to carry location-relevant clues (station numbers,
# coordinates, sheet callouts) rather than general boilerplate.
PRIORITY_FILENAME_PATTERNS = [
    r"\binstall\b",
    r"\bplan\b",
    r"\bprofile\b",
    r"\bas-?built\b",
    r"\bdrawing\b",
    r"\bsheet\b",
    r"\bmarkup\b",
    r"\bredline\b",
]

# Filenames matching these patterns get deprioritized: typically long,
# boilerplate, or non-location-specific documents.
DEPRIORITIZED_FILENAME_PATTERNS = [
    r"\bsubmittal\b",
    r"\bproduct data\b",
    r"\bspec(ification)?\b",
    r"\bcut sheet\b",
    r"\bwarranty\b",
    r"\bcatalog\b",
]


@dataclass
class LinkedAttachment:
    url: str
    filename: str
    text: str
    word_count: int
    pages: int


def _priority_score(attachment: LinkedAttachment) -> int:
    """Higher score = higher priority to include in full. Combines a filename
    signal with an inverse-size preference, since a short, specifically-named
    document is more likely to be information-dense for location matching than
    a long boilerplate one."""
    normalized = re.sub(r"[_\-\.]+", " ", attachment.filename.lower())
    score = 0
    for pattern in PRIORITY_FILENAME_PATTERNS:
        if re.search(pattern, normalized):
            score += 100
    for pattern in DEPRIORITIZED_FILENAME_PATTERNS:
        if re.search(pattern, normalized):
            score -= 100
    # Inverse-size tiebreaker so two similarly-named attachments don't tie
    # arbitrarily, and so unmatched-by-pattern short docs still rank above
    # unmatched-by-pattern long ones.
    score += max(0, 50 - attachment.pages)
    return score


def merge_linked_attachments_within_budget(
    attachments: list[LinkedAttachment],
    word_budget: int = LINKED_CONTENT_WORD_BUDGET,
) -> dict:
    """Returns:
        {
            "merged_text": str,
            "included": [filename, ...],   # fully or partially included
            "truncated": [filename, ...],   # subset of included that got cut short
            "dropped": [filename, ...],     # excluded entirely (budget exhausted first)
        }
    """
    ranked = sorted(attachments, key=_priority_score, reverse=True)

    remaining_budget = word_budget
    included: list[str] = []
    dropped: list[str] = []
    truncated: list[str] = []
    merged_parts: list[str] = []

    for attachment in ranked:
        if remaining_budget <= 0:
            dropped.append(attachment.filename)
            continue

        words = attachment.text.split()
        if len(words) <= remaining_budget:
            merged_parts.append(_format_block(attachment, attachment.text))
            included.append(attachment.filename)
            remaining_budget -= len(words)
        else:
            truncated_text = " ".join(words[:remaining_budget])
            merged_parts.append(
                _format_block(attachment, truncated_text, was_truncated=True)
            )
            included.append(attachment.filename)
            truncated.append(attachment.filename)
            remaining_budget = 0

    return {
        "merged_text": "\n\n".join(merged_parts),
        "included": included,
        "dropped": dropped,
        "truncated": truncated,
    }


def _format_block(
    attachment: LinkedAttachment, text: str, was_truncated: bool = False
) -> str:
    suffix = " [TRUNCATED]" if was_truncated else ""
    return f"--- Linked content ({attachment.url}){suffix} ---\n{text}"
