# PDF Polyline & Line-Type Reading

**Goal:** Distinguish drawn line types on master plans (solid property line vs. dashed existing utility vs. dash-dot proposed phase line) and tie them to legend semantics for sewer scope / registration.

**Golden case:** drawing **1691** (`Master.pdf`, project **688**).

**Related:** `Notes/sewer_scope_precision_plan.md`, `Notes/sheet_digitization_plan.md`.

**Separate track:** Multi-orientation OCR + hybrid text index — **text** anchors only. This doc is **vector/raster linework** only.

**How to use:** Implement **Step 0 → 3** for CAD PDFs like 1691. Step 4 only when Step 0 says raster.

---

## Fork: vector PDF vs. raster

| Case | Gate | Approach |
|------|------|----------|
| Vector CAD export | Substantial stroked `'l'` in `get_drawings()` | PyMuPDF segments → chains → style signatures → legend swatch match |
| Raster / flat | Below threshold | Existing `line_extractor` + dash CV (`line_dash_classifier`) |

### Master 1691 (validated)

| Signal | ~Value |
|--------|--------|
| Drawing paths | 41k |
| `'l'` ops | 130k |
| Non-empty PDF `dashes` | **0** (all `'[] 0'`) |
| Multi-segment stroke paths | ~3.3k paths with 8–200 segments |

Dashes are **micro-segments**, not PDF dash operators. Classify via **width + gap rhythm**, not `path["dashes"]` alone.

---

## Today vs. target

| Piece | Today | Target |
|-------|--------|--------|
| `line_extractor.py` | LSD/Hough on PNG; `line_type=None` | Unchanged as **fallback**; optional dash typing in Step 4 |
| `get_drawings()` | Unused | Step 0–1 |
| `SheetLine` | `points`, `viewport_id`, `confidence`, `line_type` | + `source`, `style_signature`, populated `line_type` |
| `sheet_digitization.py` | PNG lines only | Gate → vector **or** raster |
| `scope_line_tracer.py` | Nearest high-conf plan line, ignores type | Prefer line whose `line_type` matches utility legend codes |
| `drawing_legend_line_types` | Text names only | + per-sheet swatch templates in graph `meta` |

---

## Step 0 — Per-sheet source gate ✅ (in repo)

**Added:** `backend/ai/pipelines/pdf_line_source_gate.py`  
**Tests:** `backend/tests/test_pdf_line_source_gate.py`  
**Audit:** `backend/scripts/audit_pdf_vector_lines.py` (`--drawing-id` / `--pdf`, optional `--histogram-width`)

Digitization wiring (`meta["pdf_line_source"]`) remains **Step 3**.

Decide `vector` vs `raster` once per page before digitization.

```python
"""Choose vector vs raster line extraction for a PDF page."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import fitz


class PdfLineSource(str, Enum):
    VECTOR = "vector"
    RASTER = "raster"


@dataclass(frozen=True)
class PdfLineSourceStats:
    path_count: int
    line_op_count: int
    stroked_path_count: int


# Tunable: below this → treat as raster-only sheet.
_MIN_LINE_OPS_FOR_VECTOR = 500
_MIN_STROKED_PATHS_FOR_VECTOR = 100


def _count_drawing_ops(drawings: list[dict]) -> tuple[int, int, int]:
    path_count = len(drawings)
    line_ops = 0
    stroked = 0
    for path in drawings:
        items = path.get("items") or []
        has_line = any(item[0] == "l" for item in items if item)
        if has_line and path.get("type") == "s":  # stroke
            stroked += 1
        for item in items:
            if item and item[0] == "l":
                line_ops += 1
    return path_count, line_ops, stroked


def classify_pdf_line_source(
    pdf_path: Path | str,
    *,
    page: int = 1,
) -> tuple[PdfLineSource, PdfLineSourceStats]:
    doc = fitz.open(str(pdf_path))
    try:
        page_obj = doc.load_page(page - 1)
        drawings = page_obj.get_drawings()
    finally:
        doc.close()

    path_count, line_ops, stroked = _count_drawing_ops(drawings)
    stats = PdfLineSourceStats(path_count, line_ops, stroked)
    if line_ops >= _MIN_LINE_OPS_FOR_VECTOR and stroked >= _MIN_STROKED_PATHS_FOR_VECTOR:
        return PdfLineSource.VECTOR, stats
    return PdfLineSource.RASTER, stats
```

**Wire (Step 3 preview)** — `digitize_drawing_page` needs the source PDF path (store on `Drawing` or pass from indexer):

```python
from ai.pipelines.pdf_line_source_gate import PdfLineSource, classify_pdf_line_source

source, line_stats = classify_pdf_line_source(master_pdf_path, page=page)
meta["pdf_line_source"] = source.value
meta["pdf_line_source_stats"] = {
    "path_count": line_stats.path_count,
    "line_op_count": line_stats.line_op_count,
    "stroked_path_count": line_stats.stroked_path_count,
}
```

---

## Step 1 — Vector ingest (segments → chains → style) ✅ (in repo)

**Added:** `backend/ai/pipelines/pdf_vector_line_extractor.py` — types, `extract_pdf_vector_segments`, `segments_to_chains` (per-path dash preservation + solid colinear merge), `extract_pdf_vector_chains`, `chains_to_sheet_lines`  
**Tests:** `backend/tests/test_pdf_vector_line_extractor.py`  
**Reuse:** `_merge_colinear_segments` from `line_extractor.py` (fractional `dist_tol` for solid merge only)

### 1a — Types

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LineStyleKind = Literal["solid", "dashed", "dash_dot", "unknown"]


@dataclass(frozen=True)
class PdfVectorSegment:
    x0: float
    y0: float
    x1: float
    y1: float
    stroke_width: float
    color: tuple[int, int, int] | None
    path_index: int
    segment_index: int


@dataclass(frozen=True)
class LineStyleSignature:
    """Comparable fingerprint for legend swatch matching."""
    stroke_width_bucket: float  # e.g. round(width, 2)
    mean_segment_len_frac: float
    mean_gap_len_frac: float
    segment_count: int
    kind_guess: LineStyleKind


@dataclass(frozen=True)
class PdfVectorChain:
    points: tuple[tuple[float, float], ...]  # fractional 0–1
    stroke_width: float
    color: tuple[int, int, int] | None
    style: LineStyleSignature
    source_path_indices: tuple[int, ...]
```

### 1b — Display-space segment extraction ✅

**Shared helper:** `backend/ai/pipelines/pdf_display_space.py`  
- `pdf_point_to_display_fractional(page, x, y)` — vector `'l'` endpoints  
- `pdf_rect_to_display_fractional(page, x0, y0, x1, y1)` — same math as `document_text_extraction._word_rect_in_page_display_space` (OCR / native word boxes)

**Implementation:** `extract_pdf_vector_segments()` in `pdf_vector_line_extractor.py`  
- Stroked paths only (`type == "s"`), `'l'` items only  
- Skips segments shorter than `min_segment_len_frac` (default `0.0005`)  
- Skips segments whose midpoint falls in the title block (`TITLE_BLOCK_X_MIN/Y_MIN`)  
- Stroke color via `_parse_stroke_color()` (0–1 or 0–255 RGB tuples)

**Tests:** `test_extract_segments_maps_to_fractional_display_space`, `test_extract_segments_on_rotated_page_stays_in_fractional_range`

### 1c — Chain merge + faux-dash style signature

Merge colinear segments (same path or neighbor paths with same width). Along the chain axis, alternate **ink** (segment) vs **gap** (distance between consecutive segment endpoints) to infer dashed vs solid when PDF `dashes` is empty.

```python
import math

from ai.pipelines.line_extractor import _merge_colinear_segments  # or shared module


def _style_from_chain(
    points: tuple[tuple[float, float], ...],
    *,
    stroke_width: float,
    micro_segment_count: int,
) -> LineStyleSignature:
    # Project consecutive vertices onto chain axis; measure run lengths.
    gaps: list[float] = []
    runs: list[float] = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        runs.append(math.hypot(x1 - x0, y1 - y0))
    for i in range(len(points) - 2):
        ax, ay = points[i + 1]
        bx, by = points[i + 2]
        gaps.append(math.hypot(bx - ax, by - ay))

    mean_run = sum(runs) / len(runs) if runs else 0.0
    mean_gap = sum(gaps) / len(gaps) if gaps else 0.0
    width_bucket = round(stroke_width, 2)

    kind: LineStyleKind = "unknown"
    if micro_segment_count <= 1 and mean_gap < mean_run * 0.05:
        kind = "solid"
    elif mean_gap > mean_run * 0.3:
        kind = "dashed"
    elif mean_gap > mean_run * 0.1:
        kind = "dash_dot"  # refine with gap periodicity in v2

    return LineStyleSignature(
        stroke_width_bucket=width_bucket,
        mean_segment_len_frac=mean_run,
        mean_gap_len_frac=mean_gap,
        segment_count=micro_segment_count,
        kind_guess=kind,
    )


def segments_to_chains(
    segments: list[PdfVectorSegment],
    *,
    angle_tol_deg: float = 8.0,
    dist_tol_frac: float = 0.002,
) -> list[PdfVectorChain]:
    # Group by width (+ optional color), flatten to merge input, attach style per chain.
    ...


def extract_pdf_vector_chains(
    pdf_path: str | Path,
    *,
    page: int = 1,
    max_chains: int = 2000,
) -> list[PdfVectorChain]:
    segments = extract_pdf_vector_segments(pdf_path, page=page)
    chains = segments_to_chains(segments)
    chains.sort(key=lambda c: -sum(
        math.hypot(c.points[i + 1][0] - c.points[i][0], c.points[i + 1][1] - c.points[i][1])
        for i in range(len(c.points) - 1)
    ))
    return chains[:max_chains]
```

### 1d — Convert chains → `SheetLine` ✅

**Implementation:** `chains_to_sheet_lines()` + `style_signature_as_dict()` in `pdf_vector_line_extractor.py`

- Assigns `viewport_id` via `assign_viewport_id(chain.points[0], viewports)`
- `line_type`: explicit arg (Step 2) or `chain.style.kind_guess` (`unknown` → `None`)
- `source="pdf_vector"`, `style_signature` from `LineStyleSignature`, optional `legend_line_type_id`
- **`SheetLine`** extended in `sheet_entity_graph.py` (`source` defaults to `"raster"` for PNG `line_extractor`)

**Tests:** `test_chains_to_sheet_lines_assigns_viewport`

---

## Step 2 — Legend text rows + graphic swatch templates

**Depends on:** indexed `DrawingTextElement` rows in legend band (`master_drawing_region_builder`: `_LEGEND_BLOCK_X_MAX`, `_LEGEND_BLOCK_Y_MIN/Y_MAX`).

### 2a — Row clustering ✅

**Added:** `backend/ai/pipelines/legend_line_row_builder.py` — `cluster_legend_line_rows()`, `LegendLineRow`  
**Tests:** `backend/tests/test_legend_line_row_builder.py`

- Filters legend band (defaults match region builder), skips junk + `LEGEND` header tokens  
- Clusters by centroid Y (`_ROW_Y_TOLERANCE`), joins tokens left-to-right  
- `swatch_bbox` = strip `_SWATCH_WIDTH_FRAC` left of label union box  

### 2b — Swatch templates ✅ (partial)

**Added:** `backend/ai/pipelines/legend_line_swatch.py`, `services/legend_lookup.match_line_type_by_name`  
**Tests:** `backend/tests/test_legend_line_swatch.py`, `test_legend_lookup_line_type.py`

### 2b — Swatch template extraction + DB link

```python
from ai.pipelines.pdf_vector_line_extractor import (
    LineStyleSignature,
    extract_pdf_vector_segments,
    segments_to_chains,
)
from services.legend_lookup import match_line_type_by_name  # new helper or fuzzy on line_type_name


@dataclass(frozen=True)
class LegendLineTemplate:
    legend_line_type_id: int
    line_type_name: str
    abbreviation_code: str | None
    style: LineStyleSignature


def extract_swatch_template(
    pdf_path: str | Path,
    swatch_bbox: tuple[float, float, float, float],
    *,
    page: int = 1,
) -> LineStyleSignature | None:
    x0, y0, x1, y1 = swatch_bbox
    segments = extract_pdf_vector_segments(pdf_path, page=page)
    inside = [
        s for s in segments
        if x0 <= (s.x0 + s.x1) / 2 <= x1 and y0 <= (s.y0 + s.y1) / 2 <= y1
    ]
    if not inside:
        return None
    chains = segments_to_chains(inside)
    if not chains:
        return None
    return chains[0].style


def build_legend_line_templates(
    session,
    pdf_path: str | Path,
    rows: list[LegendLineRow],
    *,
    project_id: int | None,
    page: int = 1,
) -> list[LegendLineTemplate]:
    templates: list[LegendLineTemplate] = []
    for row in rows:
        style = extract_swatch_template(pdf_path, row.swatch_bbox, page=page)
        if style is None:
            continue
        db_row = match_line_type_by_name(session, row.text, project_id=project_id)
        if db_row is None:
            continue
        templates.append(
            LegendLineTemplate(
                legend_line_type_id=int(db_row.id),
                line_type_name=str(db_row.line_type_name),
                abbreviation_code=db_row.abbreviation_code,
                style=style,
            )
        )
    return templates
```

### 2c — Classify plan chains

```python
def _signature_distance(a: LineStyleSignature, b: LineStyleSignature) -> float:
    return (
        abs(a.stroke_width_bucket - b.stroke_width_bucket) * 10.0
        + abs(a.mean_gap_len_frac - b.mean_gap_len_frac)
        + abs(a.mean_segment_len_frac - b.mean_segment_len_frac)
    )


def classify_chains_with_templates(
    chains: list[PdfVectorChain],
    templates: list[LegendLineTemplate],
) -> list[tuple[PdfVectorChain, str | None, int | None]]:
    """Returns (chain, line_type_name, legend_line_type_id)."""
    out: list[tuple[PdfVectorChain, str | None, int | None]] = []
    for chain in chains:
        if not templates:
            out.append((chain, None, None))
            continue
        best = min(templates, key=lambda t: _signature_distance(chain.style, t.style))
        out.append((chain, best.line_type_name, best.legend_line_type_id))
    return out
```

Persist templates on graph meta (no migration required v1):

```python
graph.meta["legend_line_templates"] = [
    {
        "legend_line_type_id": t.legend_line_type_id,
        "line_type_name": t.line_type_name,
        "abbreviation_code": t.abbreviation_code,
        "style": {
            "stroke_width_bucket": t.style.stroke_width_bucket,
            "mean_segment_len_frac": t.style.mean_segment_len_frac,
            "mean_gap_len_frac": t.style.mean_gap_len_frac,
            "kind_guess": t.style.kind_guess,
        },
    }
    for t in templates
]
```

---

## Step 3 — Wire digitization + scope tracer

### 3a — Extend `SheetLine` (`sheet_entity_graph.py`) ✅

Fields added (defaults keep raster / legacy JSON rows valid): `source`, `style_signature`, `legend_line_type_id`.  
`sheet_entity_graph_to_json` uses `asdict(line)` — new fields persist automatically when set.

### 3b — Orchestrator (`sheet_digitization.py`)

Replace `_extract_lines` with gated dual path:

```python
def _extract_lines(
    *,
    pdf_path: Path | None,
    rendition_png: Path,
    viewports: tuple[DrawingViewport, ...],
    page: int,
    session: Session,
    drawing_id: int,
    project_id: int | None,
) -> list[SheetLine]:
    from ai.pipelines.pdf_line_source_gate import PdfLineSource, classify_pdf_line_source
    from ai.pipelines.line_extractor import extract_line_polylines
    from ai.pipelines.pdf_vector_line_extractor import (
        chains_to_sheet_lines,
        extract_pdf_vector_chains,
        classify_chains_with_templates,
    )
    from ai.pipelines.legend_line_row_builder import cluster_legend_line_rows
    from ai.pipelines.legend_line_swatch import build_legend_line_templates

    if pdf_path is not None and pdf_path.is_file():
        source, _ = classify_pdf_line_source(pdf_path, page=page)
        if source is PdfLineSource.VECTOR:
            chains = extract_pdf_vector_chains(pdf_path, page=page)
            # Legend rows from DB text elements (same as _labels_from_text_elements query)
            rows = cluster_legend_line_rows(_text_elements_for_page(session, drawing_id, page))
            templates = build_legend_line_templates(
                session, pdf_path, rows, project_id=project_id, page=page,
            )
            classified = classify_chains_with_templates(chains, templates)
            lines: list[SheetLine] = []
            for chain, type_name, type_id in classified:
                for sl in chains_to_sheet_lines([chain], viewports, line_type=type_name):
                    lines.append(
                        SheetLine(
                            points=sl.points,
                            viewport_id=sl.viewport_id,
                            confidence=sl.confidence,
                            line_type=type_name,
                            source="pdf_vector",
                            style_signature={
                                "stroke_width_bucket": chain.style.stroke_width_bucket,
                                "mean_gap_len_frac": chain.style.mean_gap_len_frac,
                                "kind_guess": chain.style.kind_guess,
                            },
                            legend_line_type_id=type_id,
                        )
                    )
            return lines

    # Fallback: existing raster path
    if not viewports:
        return extract_line_polylines(rendition_png)
    lines = []
    for viewport in viewports:
        lines.extend(extract_line_polylines(rendition_png, viewport=viewport))
    return lines
```

**Indexer / render job:** pass `pdf_path` into `digitize_drawing_page` (local file from storage, same path used for native text extract).

### 3c — Scope tracer (`scope_line_tracer.py`)

Filter `_best_plan_sheet_line` by legend intent when `line_type` / `legend_line_type_id` present:

```python
def _line_matches_utility_legend(
    raw: dict,
    *,
    legend_codes: set[str],
    session: Session | None,
) -> bool:
    line_type = raw.get("line_type")
    if not line_type:
        return True  # legacy untyped lines — keep current behavior
    type_id = raw.get("legend_line_type_id")
    if type_id is not None and session is not None:
        from models.legend_reference import DrawingLegendLineType
        row = session.get(DrawingLegendLineType, int(type_id))
        if row and row.abbreviation_code and row.abbreviation_code in legend_codes:
            return True
    # Fuzzy: line_type text contains utility/property keywords from dossier
    upper = str(line_type).upper()
    return any(code in upper for code in legend_codes)


# Inside _best_plan_sheet_line loop, after confidence check:
if not _line_matches_utility_legend(raw, legend_codes=legend_codes, session=session):
    continue
```

Thread `legend_codes` from existing `_utility_legend_codes(dossier, session=session)` into `_best_plan_sheet_line`.

### 3d — Tests to add

| Test file | Covers |
|-----------|--------|
| `test_pdf_line_source_gate.py` | 1691 fixture → `VECTOR`; empty PDF → `RASTER` |
| `test_pdf_vector_line_extractor.py` | segment count, display-space mapping, titleblock filter |
| `test_legend_line_swatch.py` | swatch bbox → template signature |
| `test_sheet_digitization.py` | mock vector path → `source=pdf_vector` lines in graph |
| `test_scope_line_tracer.py` | typed line preferred over untyped; wrong type skipped |

---

## Step 4 — Raster dash classifier (fallback only)

**When:** Step 0 returns `RASTER`, or vector path yields `< N` chains in plan viewport.

**Add:** `backend/ai/pipelines/line_dash_classifier.py`  
**Modify:** `line_extractor.py` — optional post-pass before returning `SheetLine`

Sample along a Bresenham ray in the **binary ink** image; measure run/gap lengths in pixels; compare to legend templates from Step 2 (PNG crop) or default thresholds.

```python
"""Dash-pattern typing for raster-extracted polylines."""

from __future__ import annotations

import numpy as np

from ai.pipelines.sheet_entity_graph import SheetLine
from ai.pipelines.legend_line_swatch import LegendLineTemplate
from ai.pipelines.pdf_vector_line_extractor import LineStyleSignature


def profile_along_polyline(
    binary_ink: np.ndarray,
    points_frac: tuple[tuple[float, float], ...],
    page_w: int,
    page_h: int,
) -> tuple[list[float], list[float]]:
    """Return (run_lengths_px, gap_lengths_px) sampled along polyline."""
    ...


def classify_raster_line(
    line: SheetLine,
    binary_ink: np.ndarray,
    page_w: int,
    page_h: int,
    templates: list[LegendLineTemplate] | None = None,
) -> SheetLine:
    runs, gaps = profile_along_polyline(binary_ink, line.points, page_w, page_h)
    # Build LineStyleSignature from px stats normalized by page diagonal
    # Nearest template or kind_guess from gap/run ratio
    return SheetLine(
        points=line.points,
        viewport_id=line.viewport_id,
        confidence=line.confidence * 0.85,  # raster typing less certain
        line_type=...,
        source="raster",
        style_signature={...},
    )
```

**Do not** use Step 4 as the primary path for **1691** — vector Step 1–2 supersedes it.

---

## File map (new / touched)

| Step | New modules | Modified |
|------|-------------|----------|
| 0 | `pdf_line_source_gate.py`, `scripts/audit_pdf_vector_lines.py` | — |
| 1 | `pdf_vector_line_extractor.py` | optional `line_geometry.py` split from `line_extractor.py` |
| 2 | `legend_line_row_builder.py`, `legend_line_swatch.py` | `services/legend_lookup.py` (name → `DrawingLegendLineType`) |
| 3 | — | `sheet_entity_graph.py`, `sheet_digitization.py`, `scope_line_tracer.py`, master index/render caller |
| 4 | `line_dash_classifier.py` | `line_extractor.py` |

---

## Priority

| Track | Priority |
|-------|----------|
| Multi-orientation OCR | P0 (text) |
| Legend text row clustering | P1 (feeds Step 2) |
| Steps 0–1 vector spike on 1691 | P1–P2 |
| Step 2 swatch templates | P2 |
| Step 3 wiring + tracer | P2 |
| Step 4 raster dash | P2 only for scans |

---

## Manual validation

```bash
cd backend && PYTHONPATH=. ./venv/bin/python scripts/audit_drawing_index_coverage.py --drawing-id 1691 --project-id 688
```

After Step 1 lands:

```bash
cd backend && PYTHONPATH=. ./venv/bin/python scripts/audit_pdf_vector_lines.py --drawing-id 1691 --histogram-width
```

Golden checks:
- Vector gate → `vector` for 1691.
- Plan viewport chain count ≫ raster-only ~343 (order-of-magnitude more segments before merge).
- After Step 2: legend rows include PROPERTY + LINE; swatch templates stored in `sheetEntityGraph` page meta.
- Scope trace on utility anchor prefers `line_type` matching SS / existing utility codes when present.

---

## Summary

- **1691** = vector micro-segment export; implement **Steps 0–3** on PDF paths, not more OCR.
- **Step 0** gates source; **Step 1** extracts typed geometry; **Step 2** binds legend words to swatch signatures; **Step 3** stores typed `SheetLine`s and teaches `scope_line_tracer` to respect them; **Step 4** is scan fallback only.
