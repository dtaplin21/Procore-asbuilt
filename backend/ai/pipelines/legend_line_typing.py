"""Steps 2–3: legend line typing (link, refuse to guess, classify before cap).

Family-level width+color matching defers SS/FW/E to label_seeded_stitching (Step 4).
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Callable, Iterable, Sequence

NOISE_WORDS = {
    "LINE",
    "LINES",
    "HCAI",
    "PERMIT",
    "SHOWN",
    "FOR",
    "REFERENCE",
    "ONLY",
    "SEE",
    "DETAIL",
    "DETAILS",
    "SHEET",
    "AND",
    "OR",
    "THE",
    "OF",
    "EXISTING",
    "PROPOSED",
    "NEW",
    "SEPARATE",
    "PHASE",
    "TYPICAL",
    "TYP",
}

# Longest phrase first (substrings like WATER must not win over FIRE WATER).
KEYWORD_CODES: list[tuple[str, str]] = [
    ("FIRE WATER", "FW"),
    ("DOMESTIC WATER", "DW"),
    ("CHILLED WATER", "CHW"),
    ("HOT WATER", "HWS-HWR"),
    ("IRRIGATION", "IRR"),
    ("STEAM", "ST"),
    ("TRENCH DRAIN", "TD"),
    ("CONDENSATE", "CR"),
    ("OVERHEAD ELECTRIC", "OHE"),
    ("UNDERGROUND ELECTRIC", "UGE"),
    ("STREET LIGHT", "SL"),
    ("SANITARY SEWER", "SS"),
    ("STORM DRAIN", "SD"),
    ("ELECTRICAL", "E"),
    ("ELECTRIC", "E"),
    ("SEWER", "SS"),
    ("STORM", "SD"),
    ("WATER", "W"),
    ("GAS", "G"),
]


@dataclasses.dataclass(frozen=True)
class LineTypeRow:
    id: int
    name: str
    abbreviation_code: str | None = None


def _norm(text: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    return " ".join(text.upper().split())


def keywords_from_label(label: str) -> str:
    return " ".join(w for w in _norm(label).split() if w not in NOISE_WORDS)


def code_from_label(label: str) -> str | None:
    kw = keywords_from_label(label)
    padded = f" {kw} "
    for phrase, code in KEYWORD_CODES:
        if f" {phrase} " in padded or kw.startswith(phrase + " ") or kw == phrase:
            return code
    return None


def match_line_type(
    line_types: Sequence[LineTypeRow],
    label: str,
) -> tuple[LineTypeRow | None, str]:
    kw = keywords_from_label(label)
    if not kw:
        return None, "label has no distinguishing words (generic row)"

    code = code_from_label(label)
    if code:
        hits = [t for t in line_types if (t.abbreviation_code or "").upper() == code]
        if len(hits) == 1:
            return hits[0], f"keyword '{kw}' -> code {code}"
        if len(hits) > 1:
            return None, f"code {code} matches {len(hits)} line types (ambiguous)"

    def stem(w: str) -> str:
        return w[:-1] if w.endswith("S") and len(w) > 3 else w

    want = {stem(w) for w in kw.split()}
    scored: list[tuple[int, LineTypeRow]] = []
    for t in line_types:
        have = {stem(w) for w in _norm(t.name).split()}
        if want and want <= have:
            scored.append((len(want), t))
    if len(scored) == 1:
        return scored[0][1], f"all keywords '{kw}' found in '{scored[0][1].name}'"
    if len(scored) > 1:
        return None, f"keywords '{kw}' fit {len(scored)} line types (ambiguous)"
    return None, f"no line type matches keywords '{kw}'"


@dataclasses.dataclass(frozen=True)
class LegendTemplate:
    legend_line_type_id: int
    line_type_name: str
    abbreviation_code: str | None
    style: Any
    row_index: int | None = None


def build_templates(
    rows: Iterable[Any],
    line_types: Sequence[LineTypeRow],
    extract_style: Callable[[tuple[float, float, float, float]], Any | None],
) -> tuple[list[LegendTemplate], list[dict[str, Any]]]:
    templates: list[LegendTemplate] = []
    diag: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        row_index = getattr(row, "index", i)
        entry: dict[str, Any] = {"row": row_index, "label": row.text}
        style = extract_style(tuple(row.swatch_bbox))
        entry["swatch_style_found"] = style is not None
        if style is None:
            entry["skipped"] = "no vector segments inside swatch bbox"
            diag.append(entry)
            continue
        lt, reason = match_line_type(line_types, row.text)
        entry["match_reason"] = reason
        if lt is None:
            entry["skipped"] = "no line type match"
            diag.append(entry)
            continue
        entry["matched"] = {"id": lt.id, "name": lt.name, "code": lt.abbreviation_code}
        templates.append(
            LegendTemplate(lt.id, lt.name, lt.abbreviation_code, style, row_index)
        )
        diag.append(entry)
    return templates, diag


@dataclasses.dataclass(frozen=True)
class SwatchStyle:
    stroke_width_bucket: float
    color: tuple[int, int, int] | None
    kind_guess: str
    stub_len: float
    gap_len: float


def _segment_width(segment: Any) -> float:
    width = getattr(segment, "width", None)
    if width is None:
        width = getattr(segment, "stroke_width", 0.0)
    return float(width)


def extract_swatch_style(
    segments: Sequence[Any],
    bbox: tuple[float, float, float, float],
    *,
    min_len: float = 0.002,
) -> SwatchStyle | None:
    x0, y0, x1, y1 = bbox
    groups: dict[tuple[Any, float], list[tuple[float, float, float]]] = {}
    for s in segments:
        sx0, sy0, sx1, sy1 = float(s.x0), float(s.y0), float(s.x1), float(s.y1)
        if not (
            x0 <= min(sx0, sx1)
            and max(sx0, sx1) <= x1
            and y0 <= min(sy0, sy1)
            and max(sy0, sy1) <= y1
        ):
            continue
        length = ((sx1 - sx0) ** 2 + (sy1 - sy0) ** 2) ** 0.5
        if length < min_len:
            continue
        width = round(_segment_width(s), 2)
        groups.setdefault((s.color, width), []).append((min(sx0, sx1), max(sx0, sx1), length))
    if not groups:
        return None
    (color, width), items = max(groups.items(), key=lambda kv: sum(i[2] for i in kv[1]))
    items.sort()
    gaps = [b[0] - a[1] for a, b in zip(items, items[1:]) if b[0] - a[1] > 0]
    return SwatchStyle(
        stroke_width_bucket=width,
        color=color,
        kind_guess="stub_gap" if gaps else "solid",
        stub_len=sum(i[2] for i in items) / len(items),
        gap_len=(sum(gaps) / len(gaps)) if gaps else 0.0,
    )


WIDTH_TOL = 0.02
COLOR_TOL = 10


def _color_close(a: tuple[int, int, int] | None, b: tuple[int, int, int] | None) -> bool:
    if a is None or b is None:
        return a == b
    return all(abs(int(x) - int(y)) <= COLOR_TOL for x, y in zip(a, b))


def chain_matches(chain: Any, tpl: LegendTemplate) -> bool:
    st = tpl.style
    chain_color = getattr(chain, "color", None)
    tpl_color = getattr(st, "color", None)
    return abs(chain.style.stroke_width_bucket - st.stroke_width_bucket) <= WIDTH_TOL and _color_close(
        chain_color, tpl_color
    )


def template_families(templates: Sequence[LegendTemplate]) -> list[list[LegendTemplate]]:
    families: list[list[LegendTemplate]] = []
    for t in templates:
        for fam in families:
            f0 = fam[0].style
            if abs(f0.stroke_width_bucket - t.style.stroke_width_bucket) <= WIDTH_TOL and _color_close(
                getattr(f0, "color", None),
                getattr(t.style, "color", None),
            ):
                fam.append(t)
                break
        else:
            families.append([t])
    return families


@dataclasses.dataclass(frozen=True)
class ChainTyping:
    chain_index: int
    status: str
    line_type_name: str | None
    legend_line_type_id: int | None
    candidate_type_ids: tuple[int, ...]
    distance: float | None = None


def classify_chains(
    chains: Sequence[Any],
    templates: Sequence[LegendTemplate],
) -> list[ChainTyping]:
    if not templates:
        return [ChainTyping(i, "no_templates", None, None, ()) for i in range(len(chains))]
    out: list[ChainTyping] = []
    for i, ch in enumerate(chains):
        hits = [t for t in templates if chain_matches(ch, t)]
        ids = tuple(sorted({t.legend_line_type_id for t in hits}))
        if not ids:
            out.append(ChainTyping(i, "unmatched", None, None, ()))
        elif len(ids) == 1:
            out.append(ChainTyping(i, "typed", hits[0].line_type_name, ids[0], ids))
        else:
            out.append(ChainTyping(i, "ambiguous_family", None, None, ids))
    return out


def _length(points: Sequence[tuple[float, float]]) -> float:
    return sum(
        ((points[k + 1][0] - points[k][0]) ** 2 + (points[k + 1][1] - points[k][1]) ** 2) ** 0.5
        for k in range(len(points) - 1)
    )


def select_chains_for_storage(
    chains: Sequence[Any],
    typings: Sequence[ChainTyping],
    *,
    plan_bbox: tuple[float, float, float, float] | None,
    wanted_type_ids: Iterable[int] = (),
    max_chains: int = 2000,
) -> tuple[list[int], dict[str, int]]:
    wanted = set(wanted_type_ids)

    def in_plan(ch: Any) -> bool:
        if plan_bbox is None:
            return False
        x, y = ch.points[0]
        return plan_bbox[0] <= x <= plan_bbox[2] and plan_bbox[1] <= y <= plan_bbox[3]

    tiers: dict[int, list[tuple[float, int]]] = {1: [], 2: [], 3: [], 4: [], 5: []}
    for i, (ch, ty) in enumerate(zip(chains, typings)):
        length = _length(ch.points)
        if ty.status == "typed" and ty.legend_line_type_id in wanted:
            tier = 1
        elif ty.status == "typed" and in_plan(ch):
            tier = 2
        elif ty.status == "ambiguous_family" and in_plan(ch):
            tier = 3
        elif in_plan(ch):
            tier = 4
        else:
            tier = 5
        tiers[tier].append((length, i))

    selected: list[int] = []
    counts: dict[str, int] = {}
    for t in (1, 2, 3, 4, 5):
        items = sorted(tiers[t], key=lambda p: -p[0])
        counts[f"tier{t}"] = len(items)
        for _, idx in items:
            if len(selected) < max_chains:
                selected.append(idx)
    counts["selected"] = len(selected)
    counts["dropped"] = len(chains) - len(selected)
    return selected, counts
