"""Helpers for master drawing index validation (Phase 5 — source A/B)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from io import StringIO
from typing import Iterable, Sequence

_DEFAULT_CHECKLIST = (
    "SSMH",
    "MLK",
    "HIGHWAY",
    "LINE",
    "PROPERTY",
    "UCSF",
    "STA",
)

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class IndexToken:
    page: int
    centroid_x: float
    centroid_y: float
    source: str
    text: str
    ocr_confidence: float = 1.0

    @property
    def text_normalized(self) -> str:
        return _WHITESPACE_RE.sub(" ", self.text.strip().lower())

    def match_key(self) -> tuple[int, float, float, str]:
        """Stable key for dedupe / set diff (fractional centroid + text)."""
        return (
            self.page,
            round(self.centroid_x, 4),
            round(self.centroid_y, 4),
            self.text_normalized,
        )


def default_validation_keywords() -> tuple[str, ...]:
    return _DEFAULT_CHECKLIST


def parse_audit_tsv(content: str) -> list[IndexToken]:
    """Parse TSV from ``audit_drawing_index_coverage.py --export``."""
    reader = csv.DictReader(StringIO(content), delimiter="\t")
    if not reader.fieldnames:
        return []
    tokens: list[IndexToken] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        tokens.append(
            IndexToken(
                page=int(row.get("page") or 1),
                centroid_x=float(row.get("centroid_x") or 0.0),
                centroid_y=float(row.get("centroid_y") or 0.0),
                source=str(row.get("source") or "unknown"),
                text=text,
                ocr_confidence=float(row.get("ocr_confidence") or 1.0),
            )
        )
    return tokens


def load_audit_tsv_file(path: str) -> list[IndexToken]:
    from pathlib import Path

    return parse_audit_tsv(Path(path).read_text(encoding="utf-8"))


def summarize_sources(tokens: Sequence[IndexToken]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token.source] = counts.get(token.source, 0) + 1
    return dict(sorted(counts.items()))


def filter_tokens(
    tokens: Sequence[IndexToken],
    *,
    sources: Iterable[str] | None = None,
    page: int | None = None,
    gutter_x_max: float | None = None,
) -> list[IndexToken]:
    allowed = {s.strip().lower() for s in sources} if sources else None
    out: list[IndexToken] = []
    for token in tokens:
        if page is not None and token.page != page:
            continue
        if gutter_x_max is not None and token.centroid_x > gutter_x_max:
            continue
        if allowed is not None and token.source.lower() not in allowed:
            continue
        out.append(token)
    return out


def keyword_hits(
    tokens: Sequence[IndexToken],
    keywords: Sequence[str],
    *,
    gutter_x_max: float | None = None,
    page: int | None = 1,
) -> dict[str, list[IndexToken]]:
    """Find tokens whose text contains each keyword (case-insensitive)."""
    scoped = filter_tokens(tokens, page=page, gutter_x_max=gutter_x_max)
    hits: dict[str, list[IndexToken]] = {}
    for keyword in keywords:
        needle = keyword.strip().lower()
        if not needle:
            continue
        matched = [t for t in scoped if needle in t.text_normalized]
        hits[keyword] = matched
    return hits


@dataclass(frozen=True)
class TokenSetDiff:
    only_baseline: tuple[IndexToken, ...]
    only_current: tuple[IndexToken, ...]
    shared: tuple[IndexToken, ...]

    @property
    def only_baseline_count(self) -> int:
        return len(self.only_baseline)

    @property
    def only_current_count(self) -> int:
        return len(self.only_current)


def diff_token_sets(
    baseline: Sequence[IndexToken],
    current: Sequence[IndexToken],
) -> TokenSetDiff:
    base_keys = {t.match_key(): t for t in baseline}
    curr_keys = {t.match_key(): t for t in current}
    shared_keys = base_keys.keys() & curr_keys.keys()
    only_base = tuple(base_keys[k] for k in base_keys if k not in curr_keys)
    only_curr = tuple(curr_keys[k] for k in curr_keys if k not in base_keys)
    shared = tuple(curr_keys[k] for k in sorted(shared_keys))
    return TokenSetDiff(only_baseline=only_base, only_current=only_curr, shared=shared)


def diff_by_source(
    baseline: Sequence[IndexToken],
    current: Sequence[IndexToken],
    *,
    source: str,
) -> TokenSetDiff:
    src = source.strip().lower()
    base_filtered = [t for t in baseline if t.source.lower() == src]
    curr_filtered = [t for t in current if t.source.lower() == src]
    return diff_token_sets(base_filtered, curr_filtered)
