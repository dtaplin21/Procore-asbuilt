"""Associate sheet labels to symbols with known boxes (digitization A-1).

Heuristic nearest-neighbor first. Optional vision/LLM may ONLY pick among proposed
label indices — never invent coordinates.
"""

from __future__ import annotations

import math
import re
from typing import Any, Sequence

from ai.pipelines.sheet_entity_graph import SheetLabel, SheetSymbol

# Fractional page distance — labels further than this are not associated.
DEFAULT_MAX_DISTANCE = 0.08
# Prefer labels whose center is above the symbol (construction callout pattern).
ABOVE_BONUS = 0.65
BESIDE_Y_TOL = 0.03


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize_symbol_class(
    symbol_class: str,
    *,
    legend_session: Any | None = None,
    project_id: int | None = None,
    label_text: str | None = None,
) -> str:
    """Normalize class / label text via legend abbreviation tables when available."""
    raw = (symbol_class or "").strip()
    if not raw:
        raw = (label_text or "").strip()
    if not raw:
        return ""

    if legend_session is None:
        return raw.lower()

    from services.legend_lookup import expand_abbreviation, find_codes_for_term

    # Token-like classes (SSMH, SSCO) → expansion when known.
    token = re.sub(r"[^A-Za-z0-9]+", "", raw).upper()
    if token:
        expansion = expand_abbreviation(legend_session, token, project_id)
        if expansion:
            return expansion.strip().lower()

    # Free-text / label → preferred legend codes (pick shortest / primary).
    probe = (label_text or raw).strip()
    codes = find_codes_for_term(legend_session, probe, project_id)
    if codes:
        # Prefer exact class match among codes, else first code.
        upper_codes = {c.upper(): c for c in codes}
        if token and token in upper_codes:
            return upper_codes[token].lower()
        return sorted(codes, key=len)[0].lower()

    return raw.lower()


def _pair_score(
    label: SheetLabel,
    symbol: SheetSymbol,
    *,
    max_distance: float,
) -> float | None:
    """Lower is better. None = out of range / incompatible viewport."""
    if (
        label.viewport_id is not None
        and symbol.viewport_id is not None
        and label.viewport_id != symbol.viewport_id
    ):
        return None

    lx, ly = _bbox_center(label.bbox_fractional)
    sx, sy = _bbox_center(symbol.bbox_fractional)
    dist = _distance((lx, ly), (sx, sy))
    if dist > max_distance:
        return None

    score = dist
    # Prefer label above symbol (callout / station text).
    if ly < sy:
        score *= ABOVE_BONUS
    # Prefer horizontal neighbor when y is close (beside).
    elif abs(ly - sy) <= BESIDE_Y_TOL:
        score *= 0.85
    else:
        # Label below symbol — still allowed but penalized.
        score *= 1.15

    # Prefer horizontally aligned callouts.
    score += 0.25 * abs(lx - sx)
    return score


def associate_labels_to_symbols(
    labels: Sequence[SheetLabel],
    symbols: Sequence[SheetSymbol],
    *,
    legend_session: Any | None = None,
    project_id: int | None = None,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    use_llm: bool = False,
) -> list[dict[str, Any]]:
    """Associate each symbol to at most one nearby label (greedy nearest).

    ``use_llm`` is reserved for a future vision pass that only chooses among
    candidate label indices — never invents boxes. Ignored in v1.
    """
    del use_llm  # v1: heuristic only

    candidates: list[tuple[float, int, int]] = []
    for si, symbol in enumerate(symbols):
        for li, label in enumerate(labels):
            score = _pair_score(label, symbol, max_distance=max_distance)
            if score is None:
                continue
            candidates.append((score, si, li))

    candidates.sort(key=lambda item: item[0])
    used_symbols: set[int] = set()
    used_labels: set[int] = set()
    associations: list[dict[str, Any]] = []

    for score, si, li in candidates:
        if si in used_symbols or li in used_labels:
            continue
        used_symbols.add(si)
        used_labels.add(li)
        symbol = symbols[si]
        label = labels[li]
        normalized = normalize_symbol_class(
            symbol.symbol_class,
            legend_session=legend_session,
            project_id=project_id,
            label_text=label.text,
        )
        associations.append(
            {
                "symbol_index": si,
                "label_index": li,
                "symbol_class": symbol.symbol_class,
                "label_text": label.text,
                "normalized_class": normalized,
                "viewport_id": symbol.viewport_id or label.viewport_id,
                "method": "nearest_neighbor",
                "distance": float(
                    _distance(
                        _bbox_center(label.bbox_fractional),
                        _bbox_center(symbol.bbox_fractional),
                    )
                ),
                "score": float(score),
                "confidence": float(min(symbol.confidence, label.confidence)),
            }
        )

    associations.sort(key=lambda row: int(row["symbol_index"]))
    return associations
