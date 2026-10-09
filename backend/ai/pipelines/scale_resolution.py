"""Line-local scale parsing with graphic scale-bar corroboration."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Any, Iterable

AGREEMENT_REL_TOL = 0.05

_SCALE_RE = re.compile(
    r"""
    (?P<paper>\d+(?:\.\d+)?)
    \s*
    (?:"|INCH(?:ES)?\b|IN\b)
    \s*
    (?P<eq>[=\-–—:])
    \s*
    (?P<ft>\d+(?:\.\d+)?)
    \s*
    (?:'|FEET\b|FOOT\b|FT\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_TICK_RE = re.compile(r"^(\d+(?:\.\d+)?)'$")


@dataclass(frozen=True)
class DisplayScaleWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def group_words_into_lines(words: Iterable[Any]) -> list[list[Any]]:
    """Cluster words into horizontal text lines in display space."""
    items = [w for w in words if str(w.text).strip()]
    if not items:
        return []
    heights = [max(1e-6, w.y1 - w.y0) for w in items]
    med_h = statistics.median(heights)
    y_tol = 0.6 * med_h
    max_gap = max(0.01, 3.0 * med_h)

    items.sort(key=lambda w: (w.y0 + w.y1) / 2)
    rows: list[list[Any]] = []
    row_cy: list[float] = []
    for w in items:
        cy = (w.y0 + w.y1) / 2
        if rows and abs(cy - row_cy[-1]) <= y_tol:
            rows[-1].append(w)
            row_cy[-1] = sum((x.y0 + x.y1) / 2 for x in rows[-1]) / len(rows[-1])
        else:
            rows.append([w])
            row_cy.append(cy)

    lines: list[list[Any]] = []
    for row in rows:
        row.sort(key=lambda w: w.x0)
        current = [row[0]]
        for w in row[1:]:
            if w.x0 - current[-1].x1 > max_gap:
                lines.append(current)
                current = [w]
            else:
                current.append(w)
        lines.append(current)
    return lines


def _line_text(line: list[Any]) -> str:
    return " ".join(str(w.text).strip() for w in line)


def _line_bbox(line: list[Any]) -> list[float]:
    return [
        min(w.x0 for w in line),
        min(w.y0 for w in line),
        max(w.x1 for w in line),
        max(w.y1 for w in line),
    ]


def parse_scale_candidates(words: Iterable[Any]) -> list[dict[str, Any]]:
    """Every scale expression found, one line at a time."""
    out: list[dict[str, Any]] = []
    for line in group_words_into_lines(words):
        text = _line_text(line)
        for m in _SCALE_RE.finditer(text):
            paper = float(m.group("paper"))
            feet = float(m.group("ft"))
            if paper <= 0 or feet <= 0:
                continue
            out.append(
                {
                    "raw_text": m.group(0).strip(),
                    "line_text": text,
                    "paper_in": paper,
                    "real_ft": feet,
                    "real_feet_per_paper_inch": feet / paper,
                    "confidence": 0.90 if m.group("eq") == "=" else 0.80,
                    "bbox": _line_bbox(line),
                }
            )
    return out


def scale_from_tick_labels(
    words: Iterable[Any],
    page_width_in: float,
    *,
    min_ticks: int = 3,
    max_residual_frac: float = 0.03,
) -> dict[str, Any] | None:
    """Feet per paper inch from a graphic scale bar's tick labels."""
    best: dict[str, Any] | None = None
    for line in group_words_into_lines(words):
        pts: list[tuple[float, float]] = []
        for w in line:
            m = _TICK_RE.match(str(w.text).strip())
            if m:
                pts.append((float(m.group(1)), (w.x0 + w.x1) / 2 * page_width_in))
        if len(pts) < min_ticks:
            continue
        pts.sort(key=lambda p: p[1])
        feet = [p[0] for p in pts]
        if feet != sorted(feet) or len(set(feet)) != len(feet):
            continue
        xs = [p[1] for p in pts]
        n = len(pts)
        mx, my = sum(xs) / n, sum(feet) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        if sxx <= 0:
            continue
        slope = sum((x - mx) * (f - my) for x, f in zip(xs, feet)) / sxx
        intercept = my - slope * mx
        span = max(feet) - min(feet)
        worst = max(abs(slope * x + intercept - f) for x, f in zip(xs, feet))
        if slope <= 0 or span <= 0 or worst / span > max_residual_frac:
            continue
        cand = {
            "real_feet_per_paper_inch": slope,
            "ticks_ft": feet,
            "max_residual_frac": worst / span,
            "bbox": _line_bbox(line),
        }
        if best is None or len(feet) > len(best["ticks_ft"]):
            best = cand
    return best


def _agree(a: float, b: float, tol: float = AGREEMENT_REL_TOL) -> bool:
    return abs(a - b) / max(a, b) <= tol


def _scale_json(c: dict[str, Any], page: int, bar: dict[str, Any] | None) -> dict[str, Any]:
    comp = {"numerator": c["paper_in"], "denominator": c["real_ft"], "units": "in=ft"}
    out: dict[str, Any] = {
        "raw_text": c["raw_text"],
        "paper_inches_per_real_foot": c["paper_in"] / c["real_ft"],
        "real_feet_per_paper_inch": c["real_feet_per_paper_inch"],
        "horizontal": comp,
        "vertical": comp,
        "confidence": c["confidence"],
        "page": page,
        "source_bbox": c["bbox"],
    }
    if bar is not None:
        out["corroborated_by_scale_bar"] = True
        out["scale_bar_feet_per_paper_inch"] = bar["real_feet_per_paper_inch"]
        out["confidence"] = min(0.97, c["confidence"] + 0.05)
    return out


def resolve_scale(
    words: Iterable[Any],
    page_width_in: float,
    *,
    page: int = 1,
) -> dict[str, Any]:
    words_list = list(words)
    return _resolve(
        parse_scale_candidates(words_list),
        scale_from_tick_labels(words_list, page_width_in),
        page,
    )


def resolve_scale_from_sources(
    word_lists: Iterable[Iterable[Any]],
    page_width_in: float,
    *,
    page: int = 1,
) -> dict[str, Any]:
    cands: list[dict[str, Any]] = []
    bar: dict[str, Any] | None = None
    for wl in word_lists:
        wl_list = list(wl)
        for c in parse_scale_candidates(wl_list):
            twin = any(
                _agree(c["real_feet_per_paper_inch"], k["real_feet_per_paper_inch"], 1e-6)
                and abs(c["bbox"][0] - k["bbox"][0]) < 0.01
                and abs(c["bbox"][1] - k["bbox"][1]) < 0.01
                for k in cands
            )
            if not twin:
                cands.append(c)
        b = scale_from_tick_labels(wl_list, page_width_in)
        if b is not None and (bar is None or len(b["ticks_ft"]) > len(bar["ticks_ft"])):
            bar = b
    return _resolve(cands, bar, page)


def _resolve(
    cands: list[dict[str, Any]],
    bar: dict[str, Any] | None,
    page: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "none",
        "scale_json": None,
        "candidates": cands,
        "scale_bar": bar,
        "reason": "",
    }

    if not cands and bar is None:
        result["reason"] = "No scale text and no scale bar found."
        return result
    if not cands:
        result["status"] = "bar_only"
        result["reason"] = "Scale bar found but no 'N INCH = M FT' text; not promoting."
        return result

    clusters: list[list[dict[str, Any]]] = []
    for c in sorted(cands, key=lambda item: item["real_feet_per_paper_inch"]):
        if clusters and _agree(clusters[-1][0]["real_feet_per_paper_inch"], c["real_feet_per_paper_inch"]):
            clusters[-1].append(c)
        else:
            clusters.append([c])

    def best_of(cluster: list[dict[str, Any]]) -> dict[str, Any]:
        return max(cluster, key=lambda item: item["confidence"])

    if bar is not None:
        match = [
            cl for cl in clusters if _agree(cl[0]["real_feet_per_paper_inch"], bar["real_feet_per_paper_inch"])
        ]
        if match:
            best = best_of(match[0])
            result["status"] = "corroborated"
            result["scale_json"] = _scale_json(best, page, bar)
            result["other_scales"] = [best_of(cl) for cl in clusters if cl not in match]
            result["reason"] = (
                f"Text {best['real_feet_per_paper_inch']:.2f} ft/in matches scale bar "
                f"{bar['real_feet_per_paper_inch']:.2f} ft/in."
                + (
                    f" {len(result['other_scales'])} other view-local scale(s) kept separate."
                    if result["other_scales"]
                    else ""
                )
            )
        else:
            result["status"] = "conflict"
            result["reason"] = (
                f"Scale bar gives {bar['real_feet_per_paper_inch']:.2f} ft/in but no scale text "
                f"matches: {sorted(round(cl[0]['real_feet_per_paper_inch'], 3) for cl in clusters)}"
            )
        return result

    if len(clusters) == 1:
        best = best_of(clusters[0])
        result["status"] = "text_only"
        result["scale_json"] = _scale_json(best, page, None)
        result["reason"] = "Scale text found; no scale bar to corroborate."
        return result

    result["status"] = "multi_scale"
    result["other_scales"] = [best_of(cl) for cl in clusters]
    result["reason"] = (
        "Several different scales and no scale bar to pick the sheet-level one: "
        f"{sorted(round(cl[0]['real_feet_per_paper_inch'], 3) for cl in clusters)}. "
        "Attach each to its viewport with attach_scales_to_viewports()."
    )
    return result


def attach_scales_to_viewports(
    scale_candidates: list[dict[str, Any]],
    viewports: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """viewport_id -> scale candidate."""
    out: dict[str, dict[str, Any]] = {}
    for c in scale_candidates:
        x0, y0, x1, y1 = c["bbox"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        inside = [
            v
            for v in viewports
            if v["bbox_fractional"][0] <= cx <= v["bbox_fractional"][2]
            and v["bbox_fractional"][1] <= cy <= v["bbox_fractional"][3]
        ]
        if not inside:
            continue
        v = min(
            inside,
            key=lambda item: (item["bbox_fractional"][2] - item["bbox_fractional"][0])
            * (item["bbox_fractional"][3] - item["bbox_fractional"][1]),
        )
        out[v["viewport_id"]] = c
    return out
