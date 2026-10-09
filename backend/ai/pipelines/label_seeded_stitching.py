"""Step 4 — trace utility runs outward from plan label codes (stub — code — stub)."""

from __future__ import annotations

import collections
import dataclasses
import math
from typing import Any, Callable, Iterable, Sequence

from ai.pipelines.legend_line_typing import COLOR_TOL, WIDTH_TOL, ChainTyping

SEED_RADIUS = 0.025
PERP_TOL = 0.0035
PARALLEL_TOL_DEG = 7.0
GAP_MAX = 0.032
GAP_ANGLE_TOL_DEG = 7.0
GAP_PERP_TOL = 0.0035
JOIN_TOL = 0.0010
JOIN_ANGLE_TOL_DEG = 40.0
MIN_STUB = 0.0015
MAX_STEPS = 400
GLYPH_PAD = 0.0012
CHAIN_RUN_PROXIMITY = 0.004


@dataclasses.dataclass(frozen=True)
class Seg:
    x0: float
    y0: float
    x1: float
    y1: float
    color: tuple[int, int, int] | None = None
    width: float = 0.0
    path_index: int = -1

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def mid(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclasses.dataclass(frozen=True)
class Label:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def c(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclasses.dataclass
class TracedRun:
    points: list[tuple[float, float]]
    labels: list[Label]
    stub_indices: list[int]
    gaps_bridged: int
    length: float
    stop_reasons: tuple[str, str]
    status: str
    ambiguous: bool = False


def _unit(dx: float, dy: float) -> tuple[float, float]:
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 0 else (0.0, 0.0)


def _angle_between_lines(a: tuple[float, float], b: tuple[float, float]) -> float:
    d = abs(a[0] * b[0] + a[1] * b[1])
    return math.degrees(math.acos(max(-1.0, min(1.0, d))))


def _angle_between_dirs(a: tuple[float, float], b: tuple[float, float]) -> float:
    d = a[0] * b[0] + a[1] * b[1]
    return math.degrees(math.acos(max(-1.0, min(1.0, d))))


def _perp_dist(p: tuple[float, float], origin: tuple[float, float], d: tuple[float, float]) -> float:
    vx, vy = p[0] - origin[0], p[1] - origin[1]
    return abs(vx * d[1] - vy * d[0])


class _Grid:
    def __init__(self, segs: Sequence[Seg], cell: float = 0.02):
        self.cell = cell
        self.cells: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
        for i, s in enumerate(segs):
            for x, y in ((s.x0, s.y0), (s.x1, s.y1), s.mid):
                self.cells[(int(x / cell), int(y / cell))].append(i)

    def near(self, p: tuple[float, float], r: float) -> set[int]:
        c = self.cell
        out: set[int] = set()
        for gx in range(int((p[0] - r) / c), int((p[0] + r) / c) + 1):
            for gy in range(int((p[1] - r) / c), int((p[1] + r) / c) + 1):
                out.update(self.cells.get((gx, gy), ()))
        return out


def _same_style(a: Seg, b: Seg, width_tol: float = WIDTH_TOL) -> bool:
    return a.color == b.color and abs(a.width - b.width) <= width_tol


def _walk(
    start: tuple[float, float],
    direction: tuple[float, float],
    first: int,
    segs: Sequence[Seg],
    usable: set[int],
    grid: _Grid,
    used: set[int],
) -> tuple[list[tuple[float, float]], list[int], int, str, bool]:
    pts: list[tuple[float, float]] = []
    stubs: list[int] = []
    gaps = 0
    pos, d, cur = start, direction, first
    ambiguous = False
    for _ in range(MAX_STEPS):
        cands: list[tuple[float, int, tuple[float, float], tuple[float, float], bool]] = []
        for j in grid.near(pos, GAP_MAX):
            if j in used or j not in usable or j == cur:
                continue
            s = segs[j]
            if not _same_style(segs[first], s):
                continue
            for near_end, far_end in (((s.x0, s.y0), (s.x1, s.y1)), ((s.x1, s.y1), (s.x0, s.y0))):
                v = (near_end[0] - pos[0], near_end[1] - pos[1])
                dist = math.hypot(*v)
                if dist > GAP_MAX:
                    continue
                if dist > 1e-9 and (v[0] * d[0] + v[1] * d[1]) < 0:
                    continue
                sd = _unit(far_end[0] - near_end[0], far_end[1] - near_end[1])
                if dist <= JOIN_TOL:
                    if _angle_between_dirs(sd, d) > JOIN_ANGLE_TOL_DEG:
                        continue
                    touching = True
                else:
                    if s.length < MIN_STUB * 2:
                        continue
                    if _angle_between_dirs(sd, d) > GAP_ANGLE_TOL_DEG:
                        continue
                    if _perp_dist(near_end, pos, d) > GAP_PERP_TOL:
                        continue
                    touching = False
                cands.append((dist, j, near_end, far_end, touching))
        if not cands:
            return pts, stubs, gaps, "dead_end", ambiguous
        cands.sort(key=lambda c: c[0])
        best = cands[0]
        if len(cands) > 1:
            second = cands[1]
            sd_a = _unit(best[3][0] - best[2][0], best[3][1] - best[2][1])
            sd_b = _unit(second[3][0] - second[2][0], second[3][1] - second[2][1])
            if (
                second[0] - best[0] < 0.0006
                and _angle_between_dirs(sd_a, sd_b) > 12.0
                and second[1] != best[1]
            ):
                return pts, stubs, gaps, "branch", True
        dist, j, near_end, far_end, touching = best
        if not touching:
            gaps += 1
            pts.append(near_end)
        elif dist > 1e-9:
            pts.append(near_end)
        pts.append(far_end)
        stubs.append(j)
        used.add(j)
        d = _unit(far_end[0] - near_end[0], far_end[1] - near_end[1])
        pos, cur = far_end, j
    return pts, stubs, gaps, "max_steps", ambiguous


def _seed_stubs(
    label: Label,
    segs: Sequence[Seg],
    usable: set[int],
    grid: _Grid,
    style_filter: Callable[[Seg], bool] | None,
) -> tuple[int, int, tuple[float, float]] | None:
    c = label.c
    cand: list[tuple[int, tuple[float, float], tuple[float, float], float]] = []
    for j in grid.near(c, SEED_RADIUS):
        if j not in usable:
            continue
        s = segs[j]
        if s.length < MIN_STUB * 2:
            continue
        if style_filter is not None and not style_filter(s):
            continue
        d = _unit(s.x1 - s.x0, s.y1 - s.y0)
        if _perp_dist(c, (s.x0, s.y0), d) > PERP_TOL:
            continue
        e0 = math.hypot(s.x0 - c[0], s.y0 - c[1])
        e1 = math.hypot(s.x1 - c[0], s.y1 - c[1])
        near_d, near_p = (e0, (s.x0, s.y0)) if e0 <= e1 else (e1, (s.x1, s.y1))
        if near_d > SEED_RADIUS:
            continue
        cand.append((j, d, near_p, near_d))
    best = None
    for a in range(len(cand)):
        for b in range(a + 1, len(cand)):
            ja, da, pa, na = cand[a]
            jb, db, pb, nb = cand[b]
            if not _same_style(segs[ja], segs[jb]):
                continue
            if _angle_between_lines(da, db) > PARALLEL_TOL_DEG:
                continue
            va = (pa[0] - c[0], pa[1] - c[1])
            vb = (pb[0] - c[0], pb[1] - c[1])
            if va[0] * vb[0] + va[1] * vb[1] >= 0:
                continue
            score = na + nb
            if best is None or score < best[0]:
                best = (score, ja, jb, da)
    if best is None:
        return None
    return best[1], best[2], best[3]


def trace_runs(
    segments: Sequence[Seg],
    labels: Iterable[Label],
    *,
    text_boxes: Iterable[Label] = (),
    style_filter: Callable[[Seg], bool] | None = None,
) -> list[TracedRun]:
    segs = list(segments)
    boxes = list(text_boxes)

    box_grid_cell = 0.02
    box_cells: dict[tuple[int, int], list[Label]] = collections.defaultdict(list)
    for b in boxes:
        for gx in range(int(b.x0 / box_grid_cell), int(b.x1 / box_grid_cell) + 1):
            for gy in range(int(b.y0 / box_grid_cell), int(b.y1 / box_grid_cell) + 1):
                box_cells[(gx, gy)].append(b)

    def in_text_fast(s: Seg) -> bool:
        mx, my = s.mid
        for b in box_cells.get((int(mx / box_grid_cell), int(my / box_grid_cell)), ()):
            if b.x0 - GLYPH_PAD <= mx <= b.x1 + GLYPH_PAD and b.y0 - GLYPH_PAD <= my <= b.y1 + GLYPH_PAD:
                return True
        return False

    usable = {
        i
        for i, s in enumerate(segs)
        if s.length >= MIN_STUB
        and not in_text_fast(s)
        and (style_filter is None or style_filter(s))
    }
    grid = _Grid(segs)

    runs: list[TracedRun] = []
    for label in labels:
        seed = _seed_stubs(label, segs, usable, grid, style_filter)
        if seed is None:
            continue
        ja, jb, _dline = seed
        used: set[int] = {ja, jb}
        sa, sb = segs[ja], segs[jb]
        c = label.c
        pa_near = (
            (sa.x0, sa.y0)
            if math.hypot(sa.x0 - c[0], sa.y0 - c[1]) <= math.hypot(sa.x1 - c[0], sa.y1 - c[1])
            else (sa.x1, sa.y1)
        )
        pa_far = (sa.x1, sa.y1) if pa_near == (sa.x0, sa.y0) else (sa.x0, sa.y0)
        pb_near = (
            (sb.x0, sb.y0)
            if math.hypot(sb.x0 - c[0], sb.y0 - c[1]) <= math.hypot(sb.x1 - c[0], sb.y1 - c[1])
            else (sb.x1, sb.y1)
        )
        pb_far = (sb.x1, sb.y1) if pb_near == (sb.x0, sb.y0) else (sb.x0, sb.y0)

        dir_a = _unit(pa_far[0] - pa_near[0], pa_far[1] - pa_near[1])
        dir_b = _unit(pb_far[0] - pb_near[0], pb_far[1] - pb_near[1])

        pts_a, stubs_a, gaps_a, why_a, amb_a = _walk(pa_far, dir_a, ja, segs, usable, grid, used)
        pts_b, stubs_b, gaps_b, why_b, amb_b = _walk(pb_far, dir_b, jb, segs, usable, grid, used)

        poly = list(reversed(pts_a)) + [pa_far, pa_near, c, pb_near, pb_far] + pts_b
        clean: list[tuple[float, float]] = []
        for p in poly:
            if clean and math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) < 1e-9:
                continue
            clean.append(p)
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(clean, clean[1:]))
        runs.append(
            TracedRun(
                points=clean,
                labels=[label],
                stub_indices=[ja, jb, *stubs_a, *stubs_b],
                gaps_bridged=gaps_a + gaps_b + 1,
                length=length,
                stop_reasons=(why_a, why_b),
                status="traced",
                ambiguous=amb_a or amb_b,
            )
        )
    return _merge_runs(runs)


def _merge_runs(runs: list[TracedRun]) -> list[TracedRun]:
    runs = sorted(runs, key=lambda r: -r.length)
    merged: list[TracedRun] = []
    for r in runs:
        mine = set(r.stub_indices)
        for m in merged:
            if mine & set(m.stub_indices):
                m.labels.extend(lab for lab in r.labels if lab not in m.labels)
                m.stub_indices = sorted(set(m.stub_indices) | mine)
                m.ambiguous = m.ambiguous or r.ambiguous
                break
        else:
            merged.append(r)
    return merged


def resolve_family_with_runs(
    runs: Sequence[TracedRun],
    code_to_type_id: dict[str, int],
    code: str,
) -> dict[int, int]:
    type_id = code_to_type_id[code]
    return {i: type_id for r in runs for i in r.stub_indices}


def segments_from_pdf_vector_segments(segments: Sequence[Any]) -> list[Seg]:
    out: list[Seg] = []
    for s in segments:
        out.append(
            Seg(
                float(s.x0),
                float(s.y0),
                float(s.x1),
                float(s.y1),
                color=getattr(s, "color", None),
                width=float(getattr(s, "stroke_width", getattr(s, "width", 0.0))),
                path_index=int(getattr(s, "path_index", -1)),
            )
        )
    return out


def labels_from_bboxes(items: Iterable[tuple[str, tuple[float, float, float, float]]]) -> list[Label]:
    return [Label(text=t, x0=b[0], y0=b[1], x1=b[2], y1=b[3]) for t, b in items]


def _color_close(a: tuple[int, int, int] | None, b: tuple[int, int, int] | None) -> bool:
    if a is None or b is None:
        return a == b
    return all(abs(int(x) - int(y)) <= COLOR_TOL for x, y in zip(a, b))


def style_filter_for_swatch(
    *,
    stroke_width_bucket: float,
    color: tuple[int, int, int] | None,
) -> Callable[[Seg], bool]:
    def filt(s: Seg) -> bool:
        return abs(s.width - stroke_width_bucket) <= WIDTH_TOL and _color_close(s.color, color)

    return filt


def chain_near_traced_run(chain: Any, run: TracedRun, *, tol: float = CHAIN_RUN_PROXIMITY) -> bool:
    for cx, cy in chain.points:
        for rx, ry in run.points:
            if math.hypot(cx - rx, cy - ry) <= tol:
                return True
    return False


def enrich_ambiguous_chain_typings(
    chains: Sequence[Any],
    typings: list[ChainTyping],
    segments: Sequence[Seg],
    text_boxes: Sequence[Label],
    *,
    code_to_template: dict[str, tuple[int, str, Callable[[Seg], bool] | None]],
    plan_bbox: tuple[float, float, float, float] | None = None,
) -> tuple[list[ChainTyping], dict[str, Any]]:
    """Resolve ``ambiguous_family`` chains when label-seeded traces uniquely place them."""
    stats: dict[str, Any] = {"traced_codes": {}, "resolved_chain_count": 0}
    if not code_to_template:
        return typings, stats

    all_boxes = list(text_boxes)
    updated = list(typings)

    def in_plan(lab: Label) -> bool:
        if plan_bbox is None:
            return True
        cx, cy = lab.c
        return plan_bbox[0] <= cx <= plan_bbox[2] and plan_bbox[1] <= cy <= plan_bbox[3]

    for code, (type_id, type_name, style_filter) in code_to_template.items():
        seeds = [
            lab
            for lab in all_boxes
            if lab.text.strip().upper() == code.upper() and in_plan(lab)
        ]
        if not seeds:
            continue
        runs = trace_runs(segments, seeds, text_boxes=all_boxes, style_filter=style_filter)
        stats["traced_codes"][code] = {
            "run_count": len(runs),
            "label_seeds": len(seeds),
            "ambiguous_runs": sum(1 for r in runs if r.ambiguous),
        }
        if not runs:
            continue
        for i, ty in enumerate(updated):
            if ty.status != "ambiguous_family" or type_id not in ty.candidate_type_ids:
                continue
            chain = chains[i]
            matching = [r for r in runs if chain_near_traced_run(chain, r)]
            if len(matching) != 1 or matching[0].ambiguous:
                continue
            updated[i] = ChainTyping(
                i,
                "typed",
                type_name,
                type_id,
                ty.candidate_type_ids,
            )
            stats["resolved_chain_count"] += 1

    return updated, stats


def traced_runs_to_meta(runs: Sequence[TracedRun]) -> list[dict[str, Any]]:
    return [
        {
            "status": r.status,
            "length": r.length,
            "gaps_bridged": r.gaps_bridged,
            "stop_reasons": list(r.stop_reasons),
            "ambiguous": r.ambiguous,
            "label_texts": [lab.text for lab in r.labels],
            "stub_count": len(r.stub_indices),
            "point_count": len(r.points),
        }
        for r in runs
    ]
