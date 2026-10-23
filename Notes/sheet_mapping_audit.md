# Sheet mapping audit — count every ink mark, then redraw the save

**Goal:** A sheet is fully mapped only when the PDF is the answer key. Every path item and every native word lands in one bucket: saved as a typed entity, saved as unknown geometry, or ignored with a reason. `mapped + ignored + unaccounted = total`, and `unaccounted` is 0. A second pass reloads the saved graph from the database and redraws it. Red pixels are source ink with no saved geometry under them. Blue pixels are saved geometry with no source ink under them. A fully mapped sheet has a white diff.

**How to use:** Work top to bottom. Paste the appendix into `backend/ai/pipelines/sheet_mapping_audit.py` at step 3. Check a box when that step is done. Step 8 changes when a drawing becomes `ready`. Leave it until step 7 has failed in the right place.

**Drawing this is aimed at:** project `1348`, master drawing `1722`, name `Master.pdf`, one page. The hand check for run `734` is the sanitary profile at `x 0.26–0.35`, `y 0.79–0.81` in display fractions. Overlay `528`’s saved segment is a different line; its bounding box is not this stretch.

---

## Context already in this repo

The audit reads the save. It does not trust the digitizer’s own counters.

| What | Where |
| --- | --- |
| Page graph | `drawings.index_stats_json["sheetEntityGraph"]["1"]`. Key constant: `SHEET_ENTITY_GRAPH_KEY` in `backend/services/sheet_digitization.py`. Writer: `persist_sheet_entity_graph`. |
| One saved line | `lines[]`: `points` are `[x, y]` fractions of the rendered page, `line_typing_status`, `style_signature.stroke_width_bucket` (PDF points), `source` (`pdf_vector` or `raster`). |
| Typed vs saved-but-untyped | `line_typing_status == "typed"` is a typed entity. `unmatched`, `ambiguous_family`, `no_templates`, and null are still saved. They count as mapped unknown. The Oct 9 export’s lines are `no_templates`. |
| Viewports | Table `drawing_viewports`. The graph copies them as `viewports[]` with `bbox_fractional`. |
| Words | Table `drawing_text_elements` (`bbox_json` is `{x0,y0,x1,y1}` fractions, `source` is `native_pdf`, `document_ai`, `tesseract`, `openai_vision`, or `hybrid_pdf`). Graph `labels[]` count as saved text too. |
| PDF | `drawings.storage_key`, file at `backend/uploads/<storage_key>`. `build_drawing_source_storage_key` uses `drawings/source/project-{project_id}/drawing-{drawing_id}/{filename}`. |
| Display frame | `pdf_point_to_display_fractional` and `native_words_display_fractional`. Both use `page.rotation_matrix` and `page.rect`, the same frame as `page.get_pixmap`. `y = 0` is the top of that rendered page. Page `rotation` is `270` and is already applied. Compare nothing in raw PDF user space, and do not flip `y`. |
| Snapshot already on disk | `Notes/drawing-1722-full-index-export.json`, exported `2026-10-09`. `summary_counts.symbols` is 0. `sheetEntityGraph["1"].symbols` is `[]`. One viewport, id `513`, kind `profile`, box `(0.03, 0.45, 0.82, 0.94)`. Re-export before the first real run. The live row may be newer than this file. |
| Rendered page | `drawings/rendered/project-1348/drawing-1722/page-1.png` |

What the extractor still leaves out, in `extract_pdf_vector_segments` (`backend/ai/pipelines/pdf_vector_line_extractor.py`):

- Near-white fills. They are paper. Dark fills, including manholes, are saved as symbols with `detector` `pdf_fill` and `symbol_class` `unclassified_fill`. That is the owned-by-symbols bucket. A later classifier can rename them. Until it does, `grounding_check` stays `WARN` / `EMPTY_OUTPUT` because no classified symbol exists, and the mapping gate does not count those fills as unaccounted.
- A segment whose midpoint has `x >= 0.75` and `y >= 0.75`. Those constants are `TITLE_BLOCK_X_MIN` and `TITLE_BLOCK_Y_MIN` in `backend/ai/pipelines/landmark_extractor.py`. This is the bottom-right corner. It is not the whole right-hand title strip, and it is not the profile band.
- Endpoints closer than `1e-9` of the page. That is a duplicate point, not a hairline rule.

Hairlines are saved. The old `0.0005` segment floor and the `0.002` chain floor are gone, and chain extraction no longer stops at 2,000. On Master.pdf that is about 57,600 straight segments, 7,400 curves, and 21,000 hairline chains.

Those chains do not go in `index_stats_json`. That column is returned on every index-status poll and on the drawing GET. At a few hundred bytes per chain the full set is tens of megabytes, and placement reads it on each match. Raising the cap and leaving the geometry on the drawing row would make the poll and the match pay that cost every time.

Past 2,000 lines, `persist_sheet_entity_graph` writes `drawings/sheet-graph/project-{id}/drawing-{id}/page-{page}-lines.json` and the page graph keeps `line_count` plus `line_storage_key`. `lines` on the row is empty. `load_page_lines` reads the file. Smaller sheets stay inline, which is what the existing tests persist. A re-index that shrinks back under the limit deletes the file. `capture_check` fails only if a caller still truncates. The digitizer does not.

The gray style family is the legend rows whose swatches look alike: sanitary sewer, fire water, and electric (`SEWER LINE`, `FIRE WATER LINE`, `ELECTRICAL LINE` in the 1722 legend block). A chain that was stored with `line_typing_status` `no_templates` is mapped unknown. A chain the extractor never stored is unaccounted, and the diff turns red there. That split is how a typing miss stays separate from a mapping miss.

The Oct 9 graph’s first line (`Notes/drawing-1722-full-index-export.json` around the first `lines[]` entry) has a point at `y ≈ 1.40`. Display fractions live in `[0, 1]`. Points outside that range were stored in the wrong frame. The redraw paints them as stored. Ink that lands off the pixmap stays red in the source. A stroke that crosses the page with no source under it turns blue. `points_outside_display_frame` in the report is that count.

`run_drawing_index_job` marks the drawing `ready` inside `_apply_index_result` and commits before `maybe_digitize_drawing_after_index`. The graph can be missing on a drawing the UI already calls indexed. Step 8 moves `ready` to after this audit. `indexed_at` is what `overlay_index_binding` stamps onto overlays, so it moves with that same write.

Raster-only sheets have no path items and no native words. This audit records `text_case: "raster_only"` and does not pass. Those sheets need OCR and a line detector before a white diff means anything. 1722 has a native text layer (`text_elements: 1116` on the Oct 9 export), so the vector test applies to it.

---

## Holes closed in the pipeline

These are the quiet-failure holes from the 2026-10-17 error-handling case study that this audit can see. The code now records a closed outcome instead of dropping the evidence.

| Check | Was | Now |
| --- | --- | --- |
| CAPTURE | `extract_pdf_vector_segments` kept only straight strokes (`type == "s"` and op `"l"`) and dropped anything shorter than `0.0005` of the page. On Master.pdf that hairline floor is about 21,000 chains, over half the items. `select_chains_for_storage` then dropped everything past 2,000 chains, and `wanted_type_ids` was passed as empty, so a typed sewer line had no priority. 1722 has no plan viewport, so every chain was tier 5. | Curves, rectangles, quads, `fs` strokes, and hairlines are stored. The `0.0005` and `0.002` length floors are gone, and extraction does not truncate. Past 2,000 lines the geometry is `line_storage_key`, not a bigger JSON column. `graph.meta.capture_check` is `OK` / `KEPT` or `FAILED` / `CHAIN_CAP` with `kept` and `dropped`. If any chain is still dropped, `apply_stage_checks_after_digitize` sets `index_status` to `failed` and does not enqueue a rematch. |
| GROUNDING | A drawing could be `ready` with `symbols: []`. The Oct 9 export of 1722 is that case. | `graph.meta.grounding_check` is `WARN` / `EMPTY_OUTPUT` when the symbol list is empty. The index stays `ready` on a warning. `index_stats_json.stageChecks.GROUNDING` repeats it. |
| FRAME | `frame_agreement` was stored and a sentence was appended to `gaps_noticed`. The drawing-level scale was still saved. | Agreement below 0.5 with at least 20 words compared clears `scale_json` and writes `frame_check` `WARN` / `FRAME_DISAGREE`. Viewport scales are left in place. |
| RUN | A match exception now calls `finalize_inspection_run_for_job_failure`, so a `NameError` does not finish as `complete`. An `index_only` job still called `_finalize_inspection_run_after_index`, which set the run to `complete` and the progress label to `Complete`. Run 734 job 407 was that job: linked files were indexed, placement did not run, and the badge still read Complete. Investigation errors were stored on the evidence and did not change the badge. | `index_only` without `chain_match` sets the run to `indexed` and the progress label to `Indexed`. `pdf_investigation_errors` set the run to `failed`. `complete` is only written after a match finishes. A failed capture is still the drawing `index_status` path in the CAPTURE row. |

A sheet indexed before fill ownership still has those paths as `fill_not_extracted`. Re-index 1722 before treating that reason as a current gap. The same is true of curves that were dropped by the older extractor.

The mapping gate does not use those outcomes as `index_status = failed`. `safe_run_drawing_audit` returns `suggested_status`: `ready` when the gate passes, `needs_review` when the audit finished and found a gap, and `failed` only when the audit itself raised. `CAPTURE` / `CHAIN_CAP` is still `failed`, from `apply_stage_checks_after_digitize`, before this gate runs.

## Step 1 — Re-export the live index

The script reads the database itself. The export is so you can look at the graph while you read the diff.

From `backend/`:

```bash
PYTHONPATH=. ./venv/bin/python scripts/export_drawing_index_json.py \
  --drawing-id 1722 \
  --out ../Notes/drawing-1722-full-index-export.json
```

Confirm the PDF path:

```bash
PYTHONPATH=. ./venv/bin/python -c "
from database import SessionLocal
from models.models import Drawing
from services.storage import storage_key_to_abs_path
db = SessionLocal()
d = db.get(Drawing, 1722)
print('storage_key', d.storage_key)
print('exists', storage_key_to_abs_path(d.storage_key).exists() if d.storage_key else False)
print('indexed_at', d.indexed_at, 'status', d.index_status)
db.close()
"
```

- [ ] Export rewritten from the live row
- [ ] `storage_key` file exists on disk

## Step 2 — Prove the tool can fail

Paste the appendix, then run the synthetic page before opening 1722. The synthetic page is one straight line and the word `GAUGE`. The first pass must balance and stay under the red threshold. The second pass deletes that line and the diff must light red. A tool that stays white after the delete is blind.

```bash
cd backend
PYTHONPATH=. ./venv/bin/python -m ai.pipelines.sheet_mapping_audit --self-test
```

- [ ] `--self-test` prints `self-test passed`

## Step 3 — Run 1722

```bash
cd backend
PYTHONPATH=. ./venv/bin/python -m ai.pipelines.sheet_mapping_audit \
  --drawing-id 1722 \
  --page 1 \
  --out ../Notes/drawing-1722-mapping-audit \
  --scale 1 \
  --tile-rows 4 \
  --tile-cols 6
```

`--scale 2` is the full-zoom pass once the first report looks sane. A 3024×2160 pt sheet at scale 2 is a large image. Scale 1 is the page’s own point size.

Writes:

- `original.png` — pixmap of the PDF
- `reconstruction.png` — lines from the reloaded graph only
- `diff.png` — red is missing ink, blue is extra saved ink. Saved word boxes are cleared on both images first, so a stored label does not turn red just because the redraw has no glyphs. Unsaved words stay red.
- `words.png` — green box saved, red box unsaved, gray box title-block ignore. Drawn before that clear, so the letters are still visible.
- `tiles/01_cov-….png` — worst tile first
- `report.json` — counts, reason histogram, unsaved words, tile list

Open `tiles/01_*.png` first. The worst tile is the one to inspect at full zoom.

Expected on the first 1722 run against the index already in the database:

- `unaccounted` above 0 until that drawing is re-indexed. The saved graph was built while curves, rectangles, and fills were dropped. After a re-index, stroked items should come back as `saved_untyped` or `sheet_line`, and dark fills as `owned_by_symbols`.
- Classified `symbols` stay 0 until a detector names them. `grounding_check.reason` stays `EMPTY_OUTPUT`, with `fill_owned_count` for the manhole fills. Those fills are masked out of the ink diff, so they do not keep the coverage gate red.
- `capture_check.outcome` of `FAILED` means the chain cap still dropped geometry. The drawing's `index_status` should be `failed` after the next index, not `ready`.
- `no_templates` lines that were stored count as `saved_untyped`, mapped unknown. They do not hide a missing curve.
- `points_outside_display_frame` may be above 0 on an index built before the display-frame fix. Blue strokes in the wrong place are that bug.
- `text_case` should be `native_text`. `outlined_or_absent` means the sheet has vectors and zero native words. `raster_only` means this test cannot pass yet.
- `passes_gate` should be false. The script does not change `index_status`.

- [ ] `report.json` balances (`mapped + ignored + unaccounted == total`)
- [ ] Worst tile opened and compared with the sheet

## Step 4 — Delete a real line and probe run 734

The sheet reads upright in the display frame. Title block is the bottom-right corner, legend is the top-right, `y = 0` is the top. North on the plan points down; that is a callout on the sheet (`true_north_rotation_deg` `270`, source `pdf_rotation`). It is not a second coordinate system.

Two boxes were easy to mix up:

| Box | Display fractions | What is on the rendered page |
| --- | --- | --- |
| Derived path | `x 0.26–0.35`, `y 0.79–0.81` | Sanitary profile in the lower band: `SS` manholes and the profile grid, inside viewport `(0.03, 0.45, 0.82, 0.94)`. This is the stretch to probe. |
| Overlay `528` bbox | `0.6856, 0.0796, 0.8276, 0.7305` | Axis-aligned box of one saved segment, `(0.8276, 0.0796)` → `(0.6856, 0.7305)`. That segment starts on the legend row `SEWER LINE` and ends on `HIGHWAY 24`. The middle of the box is the storm-drain notes. It is not a utility centerline. |

Those are not the same line with `y` flipped. Measuring the derived path from the bottom of the page (`y' = 1 - y`) lands on the sewer-tank section at the top-left. A 180° flip lands on the north arrow and the permitting notes. Check the path with `y` down from the top of `page.get_pixmap`.

Pick a saved line near the middle of the derived path and delete it from the copy the redraw uses. The database row stays as it is. The diff must turn red on that stroke. Then score that same path.

```bash
cd backend
PYTHONPATH=. ./venv/bin/python -m ai.pipelines.sheet_mapping_audit \
  --drawing-id 1722 \
  --page 1 \
  --out ../Notes/drawing-1722-mapping-audit-drop \
  --drop-line-near 0.305,0.80 \
  --probe 0.26,0.79,0.35,0.81
```

`report.json` → `test_the_test.passed` is true only when the dropped line’s box contains red pixels. Exit code `2` means the diff stayed white and the audit is not ready to be a gate.

If `drop-line-near` exits because no line was close, read `points_outside_display_frame` from the step 3 report. The stored coordinates are outside the display frame, so a fractional probe on the sheet will not find them.

The probe block is the hand check. Red pixels inside `0.26, 0.79, 0.35, 0.81` are profile ink that was not saved. Blue pixels there are saved geometry with no ink under it. A white probe plus a red worst-tile somewhere else means that profile stretch is mapped and the gap is on another part of the sheet.

- [ ] Dropped-line run exits 0 and `test_the_test.passed` is true
- [ ] Probe tile compared by eye with the gauge stretch

## Step 5 — Wire the gate

Do this only after step 4. Until then a coverage number that cannot fail would look the same as a passing sheet.

Save location of the module is `backend/ai/pipelines/sheet_mapping_audit.py`. The index job calls `safe_run_drawing_audit` and writes `suggested_status`. It does not call `run_drawing_audit` directly, and it does not mark the drawing `failed` because the gate found a gap.

`suggested_status` is one of:

- `ready` when `passes_gate` is true
- `needs_review` when the audit finished and the gate did not pass (unaccounted ink, tile coverage, capture, or text). The diff is stored. Matching stays off because the status is not `ready`.
- `failed` only when `safe_run_drawing_audit` caught an exception and no report was produced

In `backend/services/drawing_index_jobs.py`:

1. In `_apply_index_result`, stop writing `index_status = "ready"` and stop writing `indexed_at`. Write `index_status = "processing"` there. Still write `index_stats_json`, scale, and page meta. The drawing stays unpublished until the audit finishes.
2. Keep the commit after `maybe_digitize_drawing_after_index` so the graph is visible to a new session.
3. After that commit, open a new session and call `safe_run_drawing_audit`. That session cannot see the in-memory graph from `digitize_drawing_page`.

```python
from datetime import datetime, timezone
from pathlib import Path

from ai.pipelines.sheet_mapping_audit import safe_run_drawing_audit
from database import SessionLocal
from services.storage import write_bytes_to_storage_key

report = safe_run_drawing_audit(
    drawing_id,
    page=1,
    out_dir=Path("uploads") / "audit-preview" / f"drawing-{drawing_id}",
)
db2 = SessionLocal()
try:
    drawing = db2.get(Drawing, drawing_id)
    stats = dict(drawing.index_stats_json or {})
    gate = dict(report.get("gate") or {})
    diff_path = Path(report["files"]["diff"]) if report.get("files", {}).get("diff") else None
    if diff_path is not None and diff_path.is_file():
        diff_key = f"drawings/audit/project-{drawing.project_id}/drawing-{drawing_id}/page-1-diff.png"
        write_bytes_to_storage_key(diff_key, diff_path.read_bytes())
        gate["diff_storage_key"] = diff_key
    gate["suggested_status"] = report["suggested_status"]
    stats["mappingAudit"] = {"1": gate}
    drawing.index_stats_json = stats
    status = report["suggested_status"]
    drawing.index_status = status
    if status == "failed":
        drawing.index_error = report.get("gate_reason") or report.get("error")
    else:
        drawing.indexed_at = datetime.now(timezone.utc)
        drawing.index_error = None if status == "ready" else report.get("gate_reason")
    db2.commit()
finally:
    db2.close()
```

`master_index_status` includes `needs_review` (`client/src/types/inspection_overlay.ts`). The diff key lives on `index_stats_json.mappingAudit["1"].diff_storage_key`. Threshold is `0.98` minimum tile coverage, and `unaccounted` on paths and on words is 0, and `text_case` is `native_text`.

Call the same hook at the end of `index_inspection_attachment_drawing_sync` if linked sheets should face the same bar.

- [ ] `index_status` is `report["suggested_status"]`
- [ ] A coverage shortfall leaves `needs_review`, stores the diff, and does not set `failed`
- [ ] `indexed_at` is set for `ready` and `needs_review`
- [ ] An audit exception leaves `failed`

---

## Appendix — `backend/ai/pipelines/sheet_mapping_audit.py`

Save this as that path. Run it as `python -m ai.pipelines.sheet_mapping_audit` from `backend/` with `PYTHONPATH=.`.

```python
#!/usr/bin/env python3
"""Audit a saved sheet graph against the PDF that produced it.

The PDF is the answer key. Every drawing item and every native word is
mapped, ignored with a reason, or unaccounted. The redraw uses a graph
reloaded from the database in a new session.

See Notes/sheet_mapping_audit.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import fitz
import numpy as np
from PIL import Image, ImageDraw

TITLE_BLOCK_X_MIN = 0.75  # landmark_extractor.TITLE_BLOCK_X_MIN
TITLE_BLOCK_Y_MIN = 0.75  # landmark_extractor.TITLE_BLOCK_Y_MIN
MATCH_TOL = 0.004
INK_THRESHOLD = 240
COVERAGE_THRESHOLD = 0.98


def _backend_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "ai" / "pipelines").is_dir() and (parent / "database.py").is_file():
            return parent
    return None


def _frac(page: fitz.Page, x: float, y: float) -> tuple[float, float]:
    from ai.pipelines.pdf_display_space import pdf_point_to_display_fractional

    return pdf_point_to_display_fractional(page, x, y)


def _in_title_block(x: float, y: float) -> bool:
    return x >= TITLE_BLOCK_X_MIN and y >= TITLE_BLOCK_Y_MIN


def _paper_color(color: object) -> bool:
    if not isinstance(color, (list, tuple)) or len(color) < 3:
        return False
    try:
        comps = [float(c) for c in color[:3]]
    except (TypeError, ValueError):
        return False
    if max(comps) <= 1.0:
        comps = [c * 255 for c in comps]
    return min(comps) >= 245


@dataclass(frozen=True)
class SourceItem:
    path_index: int
    item_index: int
    kind: str
    samples: tuple[tuple[float, float], ...]
    disposition: str  # mapped | ignored | unaccounted
    bucket: str  # typed | unknown | ignored | ""
    reason: str


def _flatten_curve(page: fitz.Page, points: tuple[Any, ...], steps: int = 8) -> tuple[tuple[float, float], ...]:
    p0, p1, p2, p3 = points
    out: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        x = u**3 * p0.x + 3 * u**2 * t * p1.x + 3 * u * t**2 * p2.x + t**3 * p3.x
        y = u**3 * p0.y + 3 * u**2 * t * p1.y + 3 * u * t**2 * p2.y + t**3 * p3.y
        out.append(_frac(page, x, y))
    return tuple(out)


def _poly_from_points(page: fitz.Page, pts: list[Any]) -> tuple[tuple[float, float], ...]:
    return tuple(_frac(page, float(p.x), float(p.y)) for p in pts)


def inventory_page(page: fitz.Page) -> list[SourceItem]:
    """One record per drawing item. A fill path is one record, not one per edge."""
    found: list[SourceItem] = []
    for path_index, path in enumerate(page.get_drawings()):
        kind = str(path.get("type") or "")
        raw_items = list(path.get("items") or [])
        if kind == "f" or (kind not in {"s", "fs"} and not raw_items):
            samples: tuple[tuple[float, float], ...] = ()
            rect = path.get("rect")
            if rect is not None:
                samples = (
                    _frac(page, float(rect.x0), float(rect.y0)),
                    _frac(page, float(rect.x1), float(rect.y1)),
                )
            if _paper_color(path.get("fill")):
                found.append(SourceItem(path_index, 0, "f", samples, "ignored", "ignored", "fill_paper"))
            elif samples and _in_title_block((samples[0][0] + samples[-1][0]) / 2, (samples[0][1] + samples[-1][1]) / 2):
                found.append(SourceItem(path_index, 0, "f", samples, "ignored", "ignored", "title_block"))
            else:
                found.append(SourceItem(path_index, 0, "f", samples, "unaccounted", "", "fill_not_extracted"))
            continue
        if not raw_items:
            found.append(SourceItem(path_index, 0, kind or "empty", (), "unaccounted", "", "empty_path"))
            continue
        for item_index, item in enumerate(raw_items):
            if not item:
                found.append(SourceItem(path_index, item_index, "empty", (), "ignored", "ignored", "empty_item"))
                continue
            op = str(item[0])
            if op == "l" and len(item) >= 3:
                a = _frac(page, float(item[1].x), float(item[1].y))
                b = _frac(page, float(item[2].x), float(item[2].y))
                length = math.hypot(a[0] - b[0], a[1] - b[1])
                mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
                if length < 1e-9:
                    found.append(SourceItem(path_index, item_index, "l", (a, b), "ignored", "ignored", "degenerate"))
                elif _in_title_block(mx, my):
                    found.append(SourceItem(path_index, item_index, "l", (a, b), "ignored", "ignored", "title_block"))
                else:
                    found.append(SourceItem(path_index, item_index, "l", (a, b), "unaccounted", "", "not_in_graph"))
            elif op == "c" and len(item) >= 5:
                samples = _flatten_curve(page, (item[1], item[2], item[3], item[4]))
                mid = samples[len(samples) // 2]
                if _in_title_block(*mid):
                    found.append(SourceItem(path_index, item_index, "c", samples, "ignored", "ignored", "title_block"))
                else:
                    found.append(SourceItem(path_index, item_index, "c", samples, "unaccounted", "", "curve_not_extracted"))
            elif op == "re" and len(item) >= 2:
                rect = item[1]
                corners = (
                    _frac(page, rect.x0, rect.y0),
                    _frac(page, rect.x1, rect.y0),
                    _frac(page, rect.x1, rect.y1),
                    _frac(page, rect.x0, rect.y1),
                    _frac(page, rect.x0, rect.y0),
                )
                mid = ((corners[0][0] + corners[2][0]) / 2, (corners[0][1] + corners[2][1]) / 2)
                if _in_title_block(*mid):
                    found.append(SourceItem(path_index, item_index, "re", corners, "ignored", "ignored", "title_block"))
                else:
                    found.append(SourceItem(path_index, item_index, "re", corners, "unaccounted", "", "rect_not_extracted"))
            elif op == "qu" and len(item) >= 2:
                quad = item[1]
                pts = [getattr(quad, name) for name in ("ul", "ur", "lr", "ll")]
                samples = _poly_from_points(page, pts)
                cx = sum(p[0] for p in samples) / len(samples) if samples else 0.0
                cy = sum(p[1] for p in samples) / len(samples) if samples else 0.0
                if samples and _in_title_block(cx, cy):
                    found.append(SourceItem(path_index, item_index, "qu", samples, "ignored", "ignored", "title_block"))
                else:
                    found.append(SourceItem(path_index, item_index, "qu", samples, "unaccounted", "", "quad_not_extracted"))
            else:
                found.append(SourceItem(path_index, item_index, op, (), "ignored", "ignored", f"op_{op}"))
    return found


def _near_polyline(samples: tuple[tuple[float, float], ...], poly: list[Any], tol: float) -> bool:
    if len(poly) < 2:
        return False
    segs = list(zip(poly, poly[1:]))

    def dist(px: float, py: float) -> float:
        best = 1e9
        for (x0, y0), (x1, y1) in segs:
            x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
            vx, vy = x1 - x0, y1 - y0
            l2 = vx * vx + vy * vy or 1e-12
            t = max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / l2))
            best = min(best, math.hypot(px - (x0 + t * vx), py - (y0 + t * vy)))
        return best

    return all(dist(x, y) <= tol for x, y in samples)


def _owned_by_symbol(item: SourceItem, graph_page: dict[str, Any]) -> bool:
    if not item.samples:
        return False
    cx = sum(point[0] for point in item.samples) / len(item.samples)
    cy = sum(point[1] for point in item.samples) / len(item.samples)
    for symbol in graph_page.get("symbols") or []:
        if not isinstance(symbol, dict):
            continue
        bbox = symbol.get("bbox_fractional")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = (float(value) for value in bbox)
        if x0 - MATCH_TOL <= cx <= x1 + MATCH_TOL and y0 - MATCH_TOL <= cy <= y1 + MATCH_TOL:
            return True
    return False


def assign_buckets(items: list[SourceItem], graph_page: dict[str, Any]) -> list[SourceItem]:
    prepared: list[tuple[dict[str, Any], list[Any], float, float, float, float]] = []
    for line in graph_page.get("lines") or []:
        pts = line.get("points") or []
        if len(pts) < 2:
            continue
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        prepared.append((line, pts, min(xs) - MATCH_TOL, min(ys) - MATCH_TOL, max(xs) + MATCH_TOL, max(ys) + MATCH_TOL))

    out: list[SourceItem] = []
    for item in items:
        if item.kind == "f" and item.reason == "fill_not_extracted" and _owned_by_symbol(item, graph_page):
            out.append(replace(item, disposition="mapped", bucket="unknown", reason="owned_by_symbols"))
            continue
        if item.kind != "l" or item.reason != "not_in_graph" or not item.samples:
            out.append(item)
            continue
        xs = [p[0] for p in item.samples]
        ys = [p[1] for p in item.samples]
        ax0, ay0, ax1, ay1 = min(xs) - MATCH_TOL, min(ys) - MATCH_TOL, max(xs) + MATCH_TOL, max(ys) + MATCH_TOL
        hit: dict[str, Any] | None = None
        for line, pts, bx0, by0, bx1, by1 in prepared:
            if ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1:
                continue
            if _near_polyline(item.samples, pts, MATCH_TOL):
                hit = line
                break
        if hit is None:
            out.append(item)
            continue
        typed = hit.get("line_typing_status") == "typed"
        out.append(
            replace(
                item,
                disposition="mapped",
                bucket="typed" if typed else "unknown",
                reason="sheet_line" if typed else "saved_untyped",
            )
        )
    return out


def summarize(items: list[SourceItem]) -> dict[str, Any]:
    counts = Counter(item.disposition for item in items)
    mapped = int(counts["mapped"])
    ignored = int(counts["ignored"])
    unaccounted = int(counts["unaccounted"])
    total = len(items)
    if mapped + ignored + unaccounted != total:
        raise RuntimeError(f"audit buckets do not balance: {mapped}+{ignored}+{unaccounted} != {total}")
    examples = []
    for item in items:
        if item.disposition != "unaccounted" or len(examples) >= 50:
            continue
        mid = item.samples[len(item.samples) // 2] if item.samples else None
        examples.append(
            {
                "path_index": item.path_index,
                "item_index": item.item_index,
                "kind": item.kind,
                "reason": item.reason,
                "midpoint": list(mid) if mid else None,
            }
        )
    return {
        "total": total,
        "mapped": mapped,
        "ignored": ignored,
        "unaccounted": unaccounted,
        "balanced": True,
        "reasons": dict(Counter(item.reason for item in items)),
        "unaccounted_examples": examples,
    }


def _box(raw: Any) -> tuple[float, float, float, float] | None:
    if isinstance(raw, dict) and {"x0", "y0", "x1", "y1"} <= set(raw):
        return (float(raw["x0"]), float(raw["y0"]), float(raw["x1"]), float(raw["y1"]))
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return None


def _norm(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum())


def _iom(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    aa = max(1e-12, (a[2] - a[0]) * (a[3] - a[1]))
    bb = max(1e-12, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / min(aa, bb)


def audit_words(page: fitz.Page, saved_boxes: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    from ai.pipelines.native_pdf_display_frame import native_words_display_fractional

    words = native_words_display_fractional(page)
    if not words and page.get_drawings():
        text_case = "outlined_or_absent"
    elif not words:
        text_case = "raster_only"
    else:
        text_case = "native_text"

    prepared: list[tuple[str, tuple[float, float, float, float]]] = []
    for row in saved_boxes:
        box = _box(row.get("bbox"))
        if box is None:
            continue
        prepared.append((_norm(str(row.get("text") or "")), box))

    results: list[dict[str, Any]] = []
    for word in words:
        box = (word.x0, word.y0, word.x1, word.y1)
        cx, cy = (word.x0 + word.x1) / 2.0, (word.y0 + word.y1) / 2.0
        record = {"text": word.text, "bbox": [word.x0, word.y0, word.x1, word.y1]}
        if _in_title_block(cx, cy):
            record.update(disposition="ignored", reason="title_block")
            results.append(record)
            continue
        label = _norm(word.text)
        hit = False
        for text, saved in prepared:
            if not label or not text:
                continue
            if label != text and label not in text and text not in label:
                continue
            if _iom(box, saved) >= 0.5:
                hit = True
                break
        if hit:
            record.update(disposition="mapped", reason="text_element")
        else:
            record.update(disposition="unaccounted", reason="word_not_saved")
        results.append(record)
    return text_case, results


def summarize_words(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["disposition"]) for row in rows)
    mapped = int(counts["mapped"])
    ignored = int(counts["ignored"])
    unaccounted = int(counts["unaccounted"])
    total = len(rows)
    if mapped + ignored + unaccounted != total:
        raise RuntimeError("word buckets do not balance")
    unsaved = [row for row in rows if row["disposition"] == "unaccounted"][:200]
    return {
        "total": total,
        "mapped": mapped,
        "ignored": ignored,
        "unaccounted": unaccounted,
        "balanced": True,
        "unsaved": unsaved,
    }


def points_outside_frame(graph_page: dict[str, Any]) -> dict[str, int]:
    total = 0
    outside = 0
    for line in graph_page.get("lines") or []:
        for pt in line.get("points") or []:
            total += 1
            x, y = float(pt[0]), float(pt[1])
            if x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
                outside += 1
    return {"points": total, "outside": outside}


def _pixmap_rgb(pix: fitz.Pixmap) -> np.ndarray:
    if pix.n not in (3, 4):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return np.array(arr[:, :, :3], copy=True)


def _dilate(mask: np.ndarray, radius: int = 2) -> np.ndarray:
    h, w = mask.shape
    padded = np.pad(mask, radius)
    out = np.zeros_like(mask)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            out |= padded[radius + dy : radius + dy + h, radius + dx : radius + dx + w]
    return out


def _stroke_ignored(items: list[SourceItem], width: int, height: int) -> np.ndarray:
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle(
        [TITLE_BLOCK_X_MIN * width, TITLE_BLOCK_Y_MIN * height, width, height],
        fill=255,
    )
    for item in items:
        if item.disposition != "ignored" or len(item.samples) < 2:
            continue
        xy = [(x * width, y * height) for x, y in item.samples]
        draw.line(xy, fill=255, width=3)
    return np.array(mask) > 0


def render_images(
    page: fitz.Page,
    graph_page: dict[str, Any],
    items: list[SourceItem],
    words: list[dict[str, Any]],
    *,
    scale: float,
) -> dict[str, np.ndarray]:
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB)
    original = _pixmap_rgb(pix)
    height, width = original.shape[:2]
    recon_img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(recon_img)
    sx = width / float(page.rect.width)
    for line in graph_page.get("lines") or []:
        pts = line.get("points") or []
        if len(pts) < 2:
            continue
        xy = [(float(p[0]) * width, float(p[1]) * height) for p in pts]
        sig = line.get("style_signature") or {}
        width_pt = 1.0
        if isinstance(sig, dict) and sig.get("stroke_width_bucket"):
            width_pt = float(sig["stroke_width_bucket"])
        draw.line(xy, fill=(0, 0, 0), width=max(1, int(round(width_pt * sx))))
    recon = np.array(recon_img)
    ignored = _stroke_ignored(items, width, height)
    compare_src = original.copy()
    compare_recon = recon.copy()
    compare_src[ignored] = 255
    compare_recon[ignored] = 255
    fill_mask = Image.new("L", (width, height), 0)
    fill_draw = ImageDraw.Draw(fill_mask)
    for symbol in graph_page.get("symbols") or []:
        if not isinstance(symbol, dict) or symbol.get("detector") != "pdf_fill":
            continue
        bbox = symbol.get("bbox_fractional")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        fill_draw.rectangle(
            [float(bbox[0]) * width, float(bbox[1]) * height, float(bbox[2]) * width, float(bbox[3]) * height],
            fill=255,
        )
    owned_fills = np.array(fill_mask) > 0
    compare_src[owned_fills] = 255
    compare_recon[owned_fills] = 255

    words_img = Image.fromarray(original.copy())
    wdraw = ImageDraw.Draw(words_img)
    colors = {"mapped": (0, 160, 0), "unaccounted": (220, 30, 30), "ignored": (140, 140, 140)}
    word_mask = Image.new("L", (width, height), 0)
    wmask = ImageDraw.Draw(word_mask)
    for word in words:
        x0, y0, x1, y1 = word["bbox"]
        rect = [x0 * width, y0 * height, x1 * width, y1 * height]
        wdraw.rectangle(rect, outline=colors[str(word["disposition"])], width=2)
        if word["disposition"] == "mapped":
            wmask.rectangle([rect[0] - 3, rect[1] - 3, rect[2] + 3, rect[3] + 3], fill=255)
    saved_words = np.array(word_mask) > 0
    compare_src[saved_words] = 255
    compare_recon[saved_words] = 255

    orig_ink = np.any(compare_src < INK_THRESHOLD, axis=2)
    recon_ink = np.any(compare_recon < INK_THRESHOLD, axis=2)
    red = orig_ink & ~_dilate(recon_ink)
    blue = recon_ink & ~_dilate(orig_ink)
    diff = np.full_like(original, 255)
    diff[red] = (220, 30, 30)
    diff[blue] = (30, 60, 220)

    return {
        "original": original,
        "reconstruction": recon,
        "diff": diff,
        "words": np.asarray(words_img),
        "red": red,
        "blue": blue,
        "orig_ink": orig_ink,
    }


def tile_report(
    orig_ink: np.ndarray,
    red: np.ndarray,
    blue: np.ndarray,
    *,
    rows: int,
    cols: int,
) -> list[dict[str, Any]]:
    height, width = orig_ink.shape
    tiles: list[dict[str, Any]] = []
    for row in range(rows):
        y0, y1 = row * height // rows, (row + 1) * height // rows
        for col in range(cols):
            x0, x1 = col * width // cols, (col + 1) * width // cols
            src = int(orig_ink[y0:y1, x0:x1].sum())
            red_n = int(red[y0:y1, x0:x1].sum())
            blue_n = int(blue[y0:y1, x0:x1].sum())
            coverage = 1.0 if src == 0 else 1.0 - (red_n / src)
            tiles.append(
                {
                    "row": row,
                    "col": col,
                    "bbox_px": [x0, y0, x1, y1],
                    "source_ink": src,
                    "red_pixels": red_n,
                    "blue_pixels": blue_n,
                    "coverage": coverage,
                }
            )
    tiles.sort(key=lambda tile: tile["coverage"])
    return tiles


def _frac_window(mask: np.ndarray, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    height, width = mask.shape
    x0 = max(0, min(width, int(box[0] * width)))
    y0 = max(0, min(height, int(box[1] * height)))
    x1 = max(0, min(width, int(box[2] * width)))
    y1 = max(0, min(height, int(box[3] * height)))
    return x0, y0, x1, y1


def red_in_frac_box(red: np.ndarray, box: tuple[float, float, float, float]) -> int:
    x0, y0, x1, y1 = _frac_window(red, box)
    if x1 <= x0 or y1 <= y0:
        return 0
    return int(red[y0:y1, x0:x1].sum())


def probe_box(images: dict[str, np.ndarray], box: tuple[float, float, float, float]) -> dict[str, Any]:
    x0, y0, x1, y1 = _frac_window(images["orig_ink"], box)
    src = int(images["orig_ink"][y0:y1, x0:x1].sum()) if x1 > x0 and y1 > y0 else 0
    red_n = int(images["red"][y0:y1, x0:x1].sum()) if x1 > x0 and y1 > y0 else 0
    blue_n = int(images["blue"][y0:y1, x0:x1].sum()) if x1 > x0 and y1 > y0 else 0
    return {
        "bbox": list(box),
        "source_ink": src,
        "red_pixels": red_n,
        "blue_pixels": blue_n,
        "coverage": 1.0 if src == 0 else 1.0 - red_n / src,
    }


def drop_line_near(graph_page: dict[str, Any], x: float, y: float, tol: float = 0.2) -> tuple[dict[str, Any], dict[str, Any]]:
    lines = [dict(line) for line in (graph_page.get("lines") or [])]
    best_i: int | None = None
    best_d = 1e9
    best_mid = (0.0, 0.0)
    for i, line in enumerate(lines):
        pts = line.get("points") or []
        inside = [p for p in pts if 0.0 <= float(p[0]) <= 1.0 and 0.0 <= float(p[1]) <= 1.0]
        if len(inside) < 1:
            continue
        mx = sum(float(p[0]) for p in inside) / len(inside)
        my = sum(float(p[1]) for p in inside) / len(inside)
        dist = math.hypot(mx - x, my - y)
        if dist < best_d:
            best_d = dist
            best_i = i
            best_mid = (mx, my)
    if best_i is None or best_d > tol:
        raise SystemExit(f"no saved line within {tol} of ({x}, {y}); closest distance {best_d:.4f}")
    dropped = lines.pop(best_i)
    updated = dict(graph_page)
    updated["lines"] = lines
    xs = [float(p[0]) for p in dropped.get("points") or []]
    ys = [float(p[1]) for p in dropped.get("points") or []]
    meta = {
        "line_index": best_i,
        "distance": best_d,
        "midpoint": list(best_mid),
        "bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
        "line_typing_status": dropped.get("line_typing_status"),
    }
    return updated, meta


def _parse_pair(text: str) -> tuple[float, float]:
    parts = [float(p) for p in text.split(",")]
    if len(parts) != 2:
        raise SystemExit(f"expected x,y; got {text}")
    return parts[0], parts[1]


def _parse_box(text: str) -> tuple[float, float, float, float]:
    parts = [float(p) for p in text.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"expected x0,y0,x1,y1; got {text}")
    return parts[0], parts[1], parts[2], parts[3]


def _save_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path)


def _saved_text_boxes(graph_page: dict[str, Any], text_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boxes = list(text_rows)
    for label in graph_page.get("labels") or []:
        boxes.append({"text": label.get("text") or "", "bbox": label.get("bbox_fractional"), "source": "sheet_label"})
    return boxes


def build_report(
    page: fitz.Page,
    graph_page: dict[str, Any],
    text_rows: list[dict[str, Any]],
    *,
    scale: float,
    tile_rows: int,
    tile_cols: int,
    coverage_threshold: float,
    drop_near: tuple[float, float] | None,
    probe: tuple[float, float, float, float] | None,
    meta: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    graph = graph_page
    drop_meta: dict[str, Any] | None = None
    if drop_near is not None:
        graph, drop_meta = drop_line_near(graph, drop_near[0], drop_near[1])
    items = assign_buckets(inventory_page(page), graph)
    path_summary = summarize(items)
    text_case, word_rows = audit_words(page, _saved_text_boxes(graph_page, text_rows))
    word_summary = summarize_words(word_rows)
    images = render_images(page, graph, items, word_rows, scale=scale)
    tiles = tile_report(images["orig_ink"], images["red"], images["blue"], rows=tile_rows, cols=tile_cols)
    min_cov = min((tile["coverage"] for tile in tiles), default=0.0)
    outside = points_outside_frame(graph_page)
    graph_meta = graph_page.get("meta") if isinstance(graph_page.get("meta"), dict) else {}
    capture = graph_meta.get("capture_check") if isinstance(graph_meta.get("capture_check"), dict) else {}
    grounding = graph_meta.get("grounding_check") if isinstance(graph_meta.get("grounding_check"), dict) else {}
    passes = (
        path_summary["unaccounted"] == 0
        and word_summary["unaccounted"] == 0
        and min_cov >= coverage_threshold
        and text_case == "native_text"
        and capture.get("outcome") != "FAILED"
    )
    reasons: list[str] = []
    if path_summary["unaccounted"]:
        reasons.append(f"paths_unaccounted={path_summary['unaccounted']}")
    if word_summary["unaccounted"]:
        reasons.append(f"words_unaccounted={word_summary['unaccounted']}")
    if min_cov < coverage_threshold:
        reasons.append(f"min_tile_coverage={min_cov:.4f}")
    if text_case != "native_text":
        reasons.append(f"text_case={text_case}")
    if capture.get("outcome") == "FAILED":
        reasons.append(f"capture={capture.get('reason')}")
    if grounding.get("outcome") == "WARN":
        reasons.append("grounding=EMPTY_OUTPUT")
    test_the_test = None
    if drop_meta is not None and drop_meta.get("bbox"):
        bbox = tuple(drop_meta["bbox"])
        # Pad a hair so antialiased pixels on the stroke still count.
        pad = 0.01
        padded = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
        red_n = red_in_frac_box(images["red"], padded)
        test_the_test = {**drop_meta, "red_pixels": red_n, "passed": red_n > 0}
    symbols = graph_page.get("symbols") or []
    passes_gate = passes and (test_the_test is None or test_the_test["passed"])
    suggested_status = "ready" if passes_gate else "needs_review"
    report: dict[str, Any] = {
        "meta": meta,
        "passes_gate": passes_gate,
        "suggested_status": suggested_status,
        "gate_reason": "; ".join(reasons) if reasons else "ok",
        "gate": {
            "unaccounted_paths": path_summary["unaccounted"],
            "unaccounted_words": word_summary["unaccounted"],
            "min_tile_coverage": min_cov,
            "coverage_threshold": coverage_threshold,
            "text_case": text_case,
            "symbol_count": len(symbols),
            "capture_check": capture,
            "grounding_check": grounding,
            "points_outside_display_frame": outside["outside"],
            "passes_gate": passes_gate,
            "suggested_status": suggested_status,
        },
        "paths": path_summary,
        "words": word_summary,
        "text_case": text_case,
        "points_outside_display_frame": outside,
        "tiles": tiles,
        "probe": probe_box(images, probe) if probe else None,
        "test_the_test": test_the_test,
    }
    return report, images


def write_outputs(out_dir: Path, report: dict[str, Any], images: dict[str, np.ndarray]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "original": out_dir / "original.png",
        "reconstruction": out_dir / "reconstruction.png",
        "diff": out_dir / "diff.png",
        "words": out_dir / "words.png",
    }
    for key, path in files.items():
        _save_png(path, images[key])
    tile_dir = out_dir / "tiles"
    for rank, tile in enumerate(report["tiles"], start=1):
        x0, y0, x1, y1 = tile["bbox_px"]
        name = f"{rank:02d}_cov-{tile['coverage']:.4f}_r{tile['row']}_c{tile['col']}.png"
        _save_png(tile_dir / name, images["diff"][y0:y1, x0:x1])
        tile["file"] = f"tiles/{name}"
    report_path = out_dir / "report.json"
    report["files"] = {key: str(path) for key, path in files.items()}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["files"]["report"] = str(report_path)
    return {key: str(path) for key, path in files.items()}


def load_saved_index(drawing_id: int, page: int) -> dict[str, Any]:
    root = _backend_root()
    if root is not None:
        os.chdir(root)
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    from database import SessionLocal
    from models.drawing_text_element import DrawingTextElement
    from models.drawing_viewport import DrawingViewport
    from models.models import Drawing
    from services.sheet_digitization import SHEET_ENTITY_GRAPH_KEY, load_page_lines
    from services.storage import storage_key_to_abs_path

    db = SessionLocal()
    try:
        drawing = db.get(Drawing, drawing_id)
        if drawing is None:
            raise SystemExit(f"drawing {drawing_id} not found")
        stats = drawing.index_stats_json if isinstance(drawing.index_stats_json, dict) else {}
        graphs = stats.get(SHEET_ENTITY_GRAPH_KEY) if isinstance(stats, dict) else None
        graph_page: dict[str, Any] = {}
        if isinstance(graphs, dict):
            raw = graphs.get(str(page))
            if isinstance(raw, dict):
                graph_page = json.loads(json.dumps(raw))
                graph_page["lines"] = load_page_lines(graph_page)
        text_rows = (
            db.query(DrawingTextElement)
            .filter(DrawingTextElement.master_drawing_id == drawing_id, DrawingTextElement.page == page)
            .all()
        )
        texts = [
            {"text": row.text, "bbox": row.bbox_json, "source": row.source}
            for row in text_rows
        ]
        viewports = (
            db.query(DrawingViewport)
            .filter(DrawingViewport.drawing_id == drawing_id, DrawingViewport.page == page)
            .all()
        )
        viewport_rows = [
            {"viewport_id": row.viewport_id, "kind": row.kind, "bbox_json": row.bbox_json, "source": row.source}
            for row in viewports
        ]
        storage_key = drawing.storage_key
        meta = {
            "drawing_id": drawing_id,
            "project_id": drawing.project_id,
            "page": page,
            "name": drawing.name,
            "index_status": drawing.index_status,
            "indexed_at": drawing.indexed_at.isoformat() if drawing.indexed_at else None,
            "storage_key": storage_key,
            "viewports": viewport_rows,
            "symbol_rows": len(graph_page.get("symbols") or []),
            "line_rows": len(graph_page.get("lines") or []),
            "text_rows": len(texts),
        }
    finally:
        db.close()
    if not storage_key or str(storage_key).startswith("http"):
        raise SystemExit(f"drawing {drawing_id} has no local PDF storage_key ({storage_key})")
    pdf_path = storage_key_to_abs_path(str(storage_key))
    if not pdf_path.exists():
        raise SystemExit(f"PDF missing at {pdf_path}")
    meta["pdf_path"] = str(pdf_path)
    return {"pdf_path": pdf_path, "graph_page": graph_page, "text_rows": texts, "meta": meta}


def run_drawing_audit(
    drawing_id: int,
    page: int = 1,
    out_dir: Path | None = None,
    *,
    scale: float = 1.0,
    tile_rows: int = 4,
    tile_cols: int = 6,
    coverage_threshold: float = COVERAGE_THRESHOLD,
    drop_line_near_xy: tuple[float, float] | None = None,
    probe: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """Reload the drawing in a new session, audit page, write images under out_dir."""
    loaded = load_saved_index(drawing_id, page)
    doc = fitz.open(str(loaded["pdf_path"]))
    try:
        if page < 1 or page > doc.page_count:
            raise SystemExit(f"page {page} out of range 1..{doc.page_count}")
        pdf_page = doc.load_page(page - 1)
        report, images = build_report(
            pdf_page,
            loaded["graph_page"],
            loaded["text_rows"],
            scale=scale,
            tile_rows=tile_rows,
            tile_cols=tile_cols,
            coverage_threshold=coverage_threshold,
            drop_near=drop_line_near_xy,
            probe=probe,
            meta=loaded["meta"],
        )
    finally:
        doc.close()
    target = out_dir or Path("uploads") / "audit-preview" / f"drawing-{drawing_id}"
    write_outputs(target, report, images)
    return report


def safe_run_drawing_audit(
    drawing_id: int,
    page: int = 1,
    out_dir: Path | None = None,
    *,
    scale: float = 1.0,
    tile_rows: int = 4,
    tile_cols: int = 6,
    coverage_threshold: float = COVERAGE_THRESHOLD,
    drop_line_near_xy: tuple[float, float] | None = None,
    probe: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """Audit one page without raising.

    A finished audit suggests ``ready`` or ``needs_review``. An exception
    suggests ``failed``. The index job writes ``suggested_status`` and does
    not treat a coverage gap as a crashed index.
    """
    try:
        report = run_drawing_audit(
            drawing_id,
            page=page,
            out_dir=out_dir,
            scale=scale,
            tile_rows=tile_rows,
            tile_cols=tile_cols,
            coverage_threshold=coverage_threshold,
            drop_line_near_xy=drop_line_near_xy,
            probe=probe,
        )
    except (Exception, SystemExit) as exc:
        message = str(exc) or exc.__class__.__name__
        return {
            "passes_gate": False,
            "suggested_status": "failed",
            "gate_reason": f"audit_error={message}",
            "error": message,
            "gate": {"passes_gate": False, "suggested_status": "failed"},
            "files": {},
        }
    status = "ready" if report.get("passes_gate") else "needs_review"
    report["suggested_status"] = status
    gate = report.get("gate")
    if isinstance(gate, dict):
        gate["suggested_status"] = status
    return report


def self_test() -> int:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    shape = page.new_shape()
    shape.draw_line(fitz.Point(72, 72), fitz.Point(400, 72))
    shape.finish(color=(0, 0, 0), width=1.5)
    shape.commit()
    page.insert_text(fitz.Point(72, 110), "GAUGE", fontsize=12)
    items = inventory_page(page)
    line = next(item for item in items if item.kind == "l" and item.reason == "not_in_graph")
    graph = {
        "lines": [
            {
                "points": [list(pt) for pt in line.samples],
                "line_typing_status": "typed",
                "style_signature": {"stroke_width_bucket": 1.5},
            }
        ],
        "labels": [],
        "symbols": [],
    }
    from ai.pipelines.native_pdf_display_frame import native_words_display_fractional

    words = native_words_display_fractional(page)
    texts = [{"text": word.text, "bbox": [word.x0, word.y0, word.x1, word.y1], "source": "native_pdf"} for word in words]
    report, images = build_report(
        page,
        graph,
        texts,
        scale=2.0,
        tile_rows=2,
        tile_cols=2,
        coverage_threshold=COVERAGE_THRESHOLD,
        drop_near=None,
        probe=None,
        meta={"self_test": True},
    )
    if report["paths"]["unaccounted"] != 0 or report["words"]["unaccounted"] != 0:
        print("self-test count failed", report["paths"], report["words"])
        return 2
    if report["gate"]["min_tile_coverage"] < COVERAGE_THRESHOLD:
        print("self-test coverage failed", report["gate"]["min_tile_coverage"])
        return 2
    drop_x = (line.samples[0][0] + line.samples[-1][0]) / 2.0
    drop_y = (line.samples[0][1] + line.samples[-1][1]) / 2.0
    broken, _images = build_report(
        page,
        graph,
        texts,
        scale=2.0,
        tile_rows=2,
        tile_cols=2,
        coverage_threshold=COVERAGE_THRESHOLD,
        drop_near=(drop_x, drop_y),
        probe=None,
        meta={"self_test": "drop"},
    )
    doc.close()
    if not broken.get("test_the_test", {}).get("passed"):
        print("self-test delete did not light the diff", broken.get("test_the_test"))
        return 2
    print("self-test passed", "red_pixels", broken["test_the_test"]["red_pixels"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a saved sheet graph against its PDF")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--drawing-id", type=int)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--tile-rows", type=int, default=4)
    parser.add_argument("--tile-cols", type=int, default=6)
    parser.add_argument("--coverage-threshold", type=float, default=COVERAGE_THRESHOLD)
    parser.add_argument("--drop-line-near", default=None, help="x,y display fraction. Run 734 profile midpoint: 0.305,0.80")
    parser.add_argument(
        "--probe",
        default=None,
        help="x0,y0,x1,y1 display fraction. Run 734 profile: 0.26,0.79,0.35,0.81",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.drawing_id is None or args.out is None:
        parser.error("--drawing-id and --out are required")
    report = run_drawing_audit(
        args.drawing_id,
        page=args.page,
        out_dir=args.out,
        scale=args.scale,
        tile_rows=args.tile_rows,
        tile_cols=args.tile_cols,
        coverage_threshold=args.coverage_threshold,
        drop_line_near_xy=_parse_pair(args.drop_line_near) if args.drop_line_near else None,
        probe=_parse_box(args.probe) if args.probe else None,
    )
    gate = report["gate"]
    print(
        f"paths mapped={report['paths']['mapped']} ignored={report['paths']['ignored']} "
        f"unaccounted={report['paths']['unaccounted']} total={report['paths']['total']}"
    )
    print(
        f"words mapped={report['words']['mapped']} ignored={report['words']['ignored']} "
        f"unaccounted={report['words']['unaccounted']} text_case={report['text_case']}"
    )
    print(
        f"min_tile_coverage={gate['min_tile_coverage']:.4f} "
        f"points_outside_display_frame={gate['points_outside_display_frame']} "
        f"passes_gate={report['passes_gate']} suggested_status={report['suggested_status']}"
    )
    print(f"wrote {args.out}")
    if report.get("test_the_test") and not report["test_the_test"]["passed"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
