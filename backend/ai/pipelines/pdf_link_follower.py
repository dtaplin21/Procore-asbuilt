"""Follow hyperlinks embedded in uploaded PDFs to gather supplemental text.

Phase 1: types only — no extraction or fetch logic wired yet.
See Notes/Cursor Implementation Plan (Phase 0) for v1 limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class PdfLinkKind(str, Enum):
    INTERNAL_PAGE = "internal_page"  # same PDF, goto page N
    EXTERNAL_URI = "external_uri"  # https://...
    NAMED_DEST = "named_dest"  # optional; handle in v2


@dataclass(frozen=True)
class PdfHyperlink:
    page_index: int  # 0-based page where link appears
    kind: PdfLinkKind
    uri: str | None  # external URL or None for internal
    target_page: int | None  # 0-based destination page (internal)
    anchor_text: str | None  # visible link label if available


@dataclass
class LinkFollowResult:
    supplemental_text: str = ""
    cross_refs: list[dict] = field(default_factory=list)
    followed_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)
