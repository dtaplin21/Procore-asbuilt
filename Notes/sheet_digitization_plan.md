# Sheet Digitization Plan — Raster Geometry + Per-Viewport Scale

**Goal:** Digitize construction PDFs (no CAD required) into a structured sheet graph — symbols, lines, labels, associations, and **per-viewport calibration** — then feed that graph into the existing location-match / scope / registration pipelines.

**Why:** Clients give raster or mixed PDFs, not DWG. Multi-scale sheets (e.g. plan `1"=20'` + section `1"=4'` on the same page) break any single global scale. Geometry extraction must be **deterministic (OpenCV / OCR)**; vision LLMs only classify and associate.

**Golden case (dev):** project `2`, master `661` (U2.C4.00 campus plan), aux C4.20 install sheet (e.g. `1501` / prior `1084`), evidence/run from sewer scope work (`Notes/sewer_scope_precision_plan.md`).

**How to use:** Work **top → bottom**. Copy one **PROMPT** block into Cursor Agent. Check `[x]` when done. Each step lists a **Manual** path (no agent) and a **TEST** command.

**Depends on (already built — extend, do not rewrite):**
- `document_text_extraction` / `ocr_engine` — native PDF + Tesseract/vision OCR
- `drawing_scale_parser` — title-block / HORIZ+VERT text scales (today: **one scale per drawing**)
- `landmark_extractor` / `landmark_matcher` — OpenCV contours + Hu moments
- `sheet_orientation_detector` — CV orientation
- `legend_lookup` / `clue_expander` — abbreviation ↔ expansion
- `registration_from_survey` / `scope_line_tracer` / inspection location agent
- `seed_master_registration_controls.py` — manual control centroids (stopgap)

**Related docs:**
- `Notes/sewer_scope_precision_plan.md` — aux polyline → master projection
- `Notes/inspection_location_agent_plan.md` — agent / dossier
- `Notes/universal_location_match_eval.md` — eval labels

---

## Problem in one picture

```
TODAY
─────
  One drawing.scale_json for whole sheet
  Contours = generic landmarks (not symbol classes)
  No line skeleton / Hough pipe runs
  Manual _UCSF_MASTER_CONTROLS for registration
  Vision LLM sometimes asked to "find the line" ✗


TARGET
──────
  Page → viewports[{kind, bbox, scale_json}]
  CV lines + YOLO symbols in fractional coords
  LLM only labels/associates crops with known boxes
  Registration uses digitized controls (or manual picks)
  Scope / match consume SheetEntityGraph ✓
```

---

## Hard rules (every phase)

| Rule | Detail |
|------|--------|
| **No CAD required** | Every sheet is a rasterized page (PyMuPDF pixmap) + OCR tokens. |
| **Per-viewport scale** | Never apply one sheet-wide `scale_json` to all geometry. Plan vs section vs detail each get their own viewport + scale. |
| **Deterministic geometry** | Pixel/line/symbol localization = OpenCV / detector / OCR bboxes. Vision LLM does **not** invent coordinates. |
| **LLM = semantics only** | Feed crops + known fractional boxes; LLM returns class, note text, associations. |
| **Fractional page space first** | Store `x0,y0,x1,y1` / polyline points in 0–1 page coords. Real-feet conversion uses **that viewport’s** scale only. |
| **Sheet numbers ≠ placement** | Sheet IDs only link aux drawings inside a project. |
| **Manual always possible** | Every automated step has a manual seed/pick path (admin UI or script). |
| **Tests gate each step** | Do not start the next prompt until that step’s TEST passes. |

---

## Target schema (SheetEntityGraph)

Persist JSON (and later tables) so match/scope don’t care how entities were produced:

```json
{
  "drawing_id": 1501,
  "page": 1,
  "viewports": [
    {
      "viewport_id": "plan",
      "kind": "plan",
      "bbox_fractional": [0.05, 0.05, 0.72, 0.78],
      "scale_json": {
        "raw_text": "1\"=20'",
        "real_feet_per_paper_inch": 20.0,
        "confidence": 0.9,
        "page": 1
      },
      "source": "manual|ocr|detected"
    },
    {
      "viewport_id": "section_a",
      "kind": "section",
      "bbox_fractional": [0.02, 0.02, 0.28, 0.32],
      "scale_json": {
        "raw_text": "1\"=4'",
        "real_feet_per_paper_inch": 4.0,
        "confidence": 0.85,
        "page": 1
      },
      "source": "manual|ocr|detected"
    }
  ],
  "labels": [],
  "symbols": [],
  "lines": [],
  "associations": [],
  "calibration_notes": "Do not use sheet-global scale for feet conversion"
}
```

**Assignment rule:** every symbol/line/label must reference a `viewport_id` (or `viewport_id=null` only for titleblock/legend chrome outside calibrated viewports).

---

## File map (full build)

| Action | Path |
|--------|------|
| ADD | `Notes/sheet_digitization_plan.md` (this file) |
| ADD | `backend/ai/pipelines/sheet_entity_graph.py` — dataclasses + JSON schema helpers |
| ADD | `backend/ai/pipelines/viewport_detector.py` — detect/assign viewports |
| ADD | `backend/ai/pipelines/viewport_scale.py` — scale per viewport (wrap `drawing_scale_parser`) |
| ADD | `backend/ai/pipelines/line_extractor.py` — OpenCV Hough/LSD/skeleton → polylines |
| ADD | `backend/ai/pipelines/symbol_detector.py` — YOLO/DINO inference wrapper |
| ADD | `backend/services/sheet_digitization.py` — orchestrate page → graph |
| ADD | `backend/models/drawing_viewport.py` — DB viewports + scale_json |
| ADD | `backend/models/drawing_symbol.py` — detected symbols |
| ADD | `backend/models/drawing_line_entity.py` — detected lines (optional v1: JSON blob on drawing) |
| ADD | `backend/alembic/versions/..._add_sheet_digitization_tables.py` |
| ADD | `backend/scripts/seed_drawing_viewports.py` — **manual** viewport + scale seed |
| ADD | `backend/scripts/pick_fractional_point.py` — CLI helper: pixel → fractional |
| ADD | `backend/scripts/export_symbol_crops.py` — crop exporter for YOLO labeling |
| ADD | `backend/tests/test_viewport_scale.py` |
| ADD | `backend/tests/test_line_extractor.py` |
| ADD | `backend/tests/test_sheet_entity_graph.py` |
| MODIFY | `backend/ai/pipelines/drawing_scale_parser.py` — keep parsers; stop treating result as sheet-global for feet |
| MODIFY | `backend/ai/pipelines/landmark_extractor.py` — optional: feed candidates into symbol pipeline |
| MODIFY | `backend/ai/pipelines/registration_from_survey.py` — prefer viewport-aware controls |
| MODIFY | `backend/ai/pipelines/scope_line_tracer.py` — attach `viewport_id` to traced geometry |
| MODIFY | `backend/scripts/seed_master_registration_controls.py` — document manual pick → seed flow |

---

## PRE — Baseline + golden page fixtures

<!-- PRE-1 baseline snapshot (2026-08-28):
  - drawings.scale_json is sheet-global (one scale per drawing; no per-viewport table)
  - landmark_extractor: OpenCV contours + Hu moments; heuristic types only (no YOLO/symbol classes)
  - no drawing_viewports table / DrawingViewport model yet
  - pytest: test_drawing_scale_parser.py + test_landmark_extractor.py green
-->

- [x] **PRE-1** Snapshot current scale + landmark behavior

**PROMPT — copy below:**

```
PRE-1: Record digitization baseline.

1. Document current behavior in a short comment at top of Notes/sheet_digitization_plan.md PRE section:
   - drawing.scale_json is sheet-global
   - landmark_extractor uses OpenCV contours (no symbol classes)
   - no viewport table

2. Run:
cd backend && ./venv/bin/python -m pytest \
  tests/test_drawing_scale_parser.py \
  tests/test_landmark_extractor.py \
  -q --tb=short

Fix failures before Phase V. Do not start digitization on a red baseline.
```

**Manual:** Same pytest command from `backend/`.

**TEST:**
```bash
cd backend && ./venv/bin/python -m pytest tests/test_drawing_scale_parser.py tests/test_landmark_extractor.py -q --tb=short
```

---

- [x] **PRE-2** Save golden page renditions for master + aux

**PROMPT — copy below:**

```
PRE-2: Export golden PNG fixtures for digitization.

ADD backend/tests/fixtures/digitization/README.md explaining:
  - master_661_page1.png = campus plan (single primary plan scale)
  - aux_c420_page1.png = install sheet with PLAN + SECTION (multi-scale)

ADD script backend/scripts/export_drawing_page_png.py:
  usage: ./venv/bin/python scripts/export_drawing_page_png.py --drawing-id 661 --page 1 --out tests/fixtures/digitization/master_661_page1.png
  use PyMuPDF pixmap at dpi=150 (match ocr_engine conventions)

Export master 661 and the current C4.20 aux id from seed_master_registration_controls (AUX_ID).
Do not commit huge binaries if gitignored — document path under uploads/ as alternative.
```

**Manual:**
```bash
cd backend
./venv/bin/python scripts/export_drawing_page_png.py --drawing-id 661 --page 1 \
  --out tests/fixtures/digitization/master_661_page1.png
./venv/bin/python scripts/export_drawing_page_png.py --drawing-id 1501 --page 1 \
  --out tests/fixtures/digitization/aux_c420_page1.png
```

**TEST:** both PNG files exist and are non-empty.

---

# Phase V — Viewports + per-viewport scale (CRITICAL)

> **This phase is the multi-scale fix.** Do not skip. Without it, Phase L/S feet math and registration will be wrong on half the sheet.

- [x] **V-1** SheetEntityGraph + Viewport dataclasses

**PROMPT — copy below:**

```
PR-V step V-1: Create sheet entity graph dataclasses.

ADD backend/ai/pipelines/sheet_entity_graph.py

"""Structured digitization output for one drawing page (no CAD required)."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal

ViewportKind = Literal["plan", "section", "detail", "elevation", "profile", "other"]

@dataclass(frozen=True)
class ViewportScale:
    raw_text: str
    real_feet_per_paper_inch: float
    confidence: float
    horizontal: dict[str, Any] | None = None
    vertical: dict[str, Any] | None = None

@dataclass(frozen=True)
class DrawingViewport:
    viewport_id: str
    kind: ViewportKind
    page: int
    bbox_fractional: tuple[float, float, float, float]  # x0,y0,x1,y1
    scale: ViewportScale | None
    source: str  # manual | ocr | detected
    notes: str = ""

@dataclass(frozen=True)
class SheetLabel:
    text: str
    bbox_fractional: tuple[float, float, float, float]
    viewport_id: str | None
    confidence: float

@dataclass(frozen=True)
class SheetSymbol:
    symbol_class: str
    bbox_fractional: tuple[float, float, float, float]
    viewport_id: str | None
    confidence: float
    detector: str  # yolo | manual | contour

@dataclass(frozen=True)
class SheetLine:
    points: tuple[tuple[float, float], ...]
    viewport_id: str | None
    confidence: float
    line_type: str | None = None

@dataclass(frozen=True)
class SheetEntityGraph:
    drawing_id: int
    page: int
    viewports: tuple[DrawingViewport, ...]
    labels: tuple[SheetLabel, ...] = ()
    symbols: tuple[SheetSymbol, ...] = ()
    lines: tuple[SheetLine, ...] = ()
    associations: tuple[dict[str, Any], ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

def assign_viewport_id(
    point_or_bbox: tuple[float, ...],
    viewports: tuple[DrawingViewport, ...],
) -> str | None:
    """Return viewport_id whose bbox contains the point/center; prefer smallest area on ties.
    NEVER fall back to a fake global viewport for scale conversion — return None if outside all.
    """
    ...

ADD backend/tests/test_sheet_entity_graph.py covering assign_viewport_id with two overlapping bboxes.
```

**Manual:** Create the file by pasting the stub; implement `assign_viewport_id` with containment + smallest-area tie-break.

**TEST:**
```bash
cd backend && ./venv/bin/python -m pytest tests/test_sheet_entity_graph.py -q --tb=short
```

---

- [x] **V-2** DB model + migration for viewports

**PROMPT — copy below:**

```
PR-V step V-2: Persist drawing viewports.

ADD backend/models/drawing_viewport.py
  - id PK
  - drawing_id FK drawings.id CASCADE
  - page int
  - viewport_id str (unique per drawing+page, e.g. "plan", "section_a")
  - kind str
  - bbox_json JSON  # {x0,y0,x1,y1}
  - scale_json JSON | null  # same shape as drawing_scale_parser output
  - source str
  - notes str | null
  - unique (drawing_id, page, viewport_id)

ADD alembic migration. Register model in models/__init__.py if needed.

Do NOT delete or repurpose drawings.scale_json yet — keep as legacy titleblock hint only.
Document in model docstring: "Feet conversion MUST use DrawingViewport.scale_json for geometry inside bbox."
```

**Manual:**
```bash
cd backend && ./venv/bin/alembic revision -m "add_drawing_viewports" --autogenerate
# review migration, then:
./venv/bin/alembic upgrade head
```

**TEST:** migration applies; table exists in `\d drawing_viewports` (psql).

---

- [x] **V-3** Manual viewport seed script (multi-scale C4.20)

**PROMPT — copy below:**

```
PR-V step V-3: Manual viewport seeding for multi-scale sheets.

ADD backend/scripts/seed_drawing_viewports.py

Usage:
  ./venv/bin/python scripts/seed_drawing_viewports.py --dry-run
  ./venv/bin/python scripts/seed_drawing_viewports.py --drawing-id 1501

Hard-code (editable) _UCSF_C420_VIEWPORTS for aux C4.20:
  1) kind=plan, bbox covering plan view (exclude profile strip y>~0.85 and section inset),
     scale raw_text='1"=20'' (or whatever the sheet titleblock says for PLAN),
     real_feet_per_paper_inch=20
  2) kind=section, bbox covering SECTION A-A (or similar),
     scale raw_text='1"=4'', real_feet_per_paper_inch=4

Upsert into drawing_viewports by (drawing_id, page, viewport_id).

Print each viewport bbox + scale. Refuse to seed if plan and section bboxes are identical.

Also ADD helper backend/scripts/pick_fractional_point.py:
  ./venv/bin/python scripts/pick_fractional_point.py --image path.png --x 120 --y 400
  prints fractional (x/w, y/h) for manual bbox corner picking from a screenshot.
```

**Manual workflow (how you pick coords without Agent):**
1. Export page PNG (`export_drawing_page_png.py`).
2. Open in Preview / Photoshop; note image width/height.
3. For each viewport corner: `frac_x = pixel_x / width`, `frac_y = pixel_y / height`.
4. Or: `./venv/bin/python scripts/pick_fractional_point.py --image … --x … --y …`
5. Edit `_UCSF_C420_VIEWPORTS` centroids/bboxes in the seed script.
6. Run seed (dry-run first).

**TEST:**
```bash
cd backend && ./venv/bin/python scripts/seed_drawing_viewports.py --drawing-id 1501 --dry-run
cd backend && ./venv/bin/python scripts/seed_drawing_viewports.py --drawing-id 1501
```

---

- [x] **V-4** `viewport_scale` helpers + tests

**PROMPT — copy below:**

```
PR-V step V-4: Per-viewport scale conversion API.

ADD backend/ai/pipelines/viewport_scale.py

def load_viewports(session, drawing_id, page=1) -> list[DrawingViewport]: ...

def scale_for_geometry(
    viewports: Sequence[DrawingViewport],
    *,
    point: tuple[float, float] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> ViewportScale | None:
    """Pick viewport containing geometry; return its scale. None if unresolved.
    MUST NOT return sheet-global drawings.scale_json as a silent fallback.
    """

def fractional_delta_to_feet(
    delta_frac: float,
    *,
    axis: Literal["x", "y"],
    scale: ViewportScale,
    page_width_in: float,
    page_height_in: float,
) -> float:
    """Convert a fractional page delta to feet using THAT viewport's scale only."""

Reuse parse helpers from drawing_scale_parser where possible
(real_feet_per_paper_inch_from_scale, page_size_inches_from_meta).

ADD tests/test_viewport_scale.py:
  - plan viewport 1"=20' vs section 1"=4' on same page
  - same fractional length converts to different feet in each viewport
  - point outside all viewports → None (no global fallback)
```

**Manual:** If automating later, still verify with a calculator:  
`feet = frac_delta * page_axis_inches * real_feet_per_paper_inch`.

**TEST:**
```bash
cd backend && ./venv/bin/python -m pytest tests/test_viewport_scale.py -q --tb=short
```

---

- [x] **V-5** OCR-assisted viewport proposals (optional automation)

**PROMPT — copy below:**

```
PR-V step V-5: Propose viewports from OCR (does not replace manual seed).

ADD backend/ai/pipelines/viewport_detector.py

Heuristic v1 (no LLM coordinates):
  - Find text tokens matching SECTION / DETAIL / PLAN / PROFILE / ELEVATION near title-like sizes
  - Propose bbox as expanded region around cluster (clamp 0-1)
  - For each proposal, search nearby OCR for scale patterns via parse_scale_from_text
  - Emit DrawingViewport proposals with source="ocr", confidence from scale parse

Never auto-commit overlapping plan+section with the same scale.
CLI flag on seed script: --from-ocr --drawing-id N (prints proposals; require --apply to write).

Vision LLM may ONLY be used to choose among proposed bboxes / confirm kind — not to invent pixel corners.
```

**Manual:** Prefer V-3 seed until OCR proposals are reviewed on C4.20.

**TEST:** dry-run `--from-ocr` prints ≥1 plan and ≥0 section proposals without writing DB unless `--apply`.

---

# Phase L — Line extraction (OpenCV)

- [x] **L-1** OpenCV line / centerline extractor

**PROMPT — copy below:**

```
PR-L step L-1: Deterministic line extraction.

ADD backend/ai/pipelines/line_extractor.py

def extract_line_polylines(
    rendition_png: Path,
    *,
    viewport: DrawingViewport | None = None,
    max_lines: int = 200,
) -> list[SheetLine]:
  - Load grayscale via cv2
  - If viewport provided, crop to bbox pixels before processing
  - Gaussian blur + adaptive/Otsu threshold
  - Morphological close; optional skeletonize (scikit-image or cv2 thinning)
  - LSD or HoughLinesP for segments; merge colinear segments into polylines
  - Convert pixels → fractional relative to FULL page (not crop-only)
  - Attach viewport_id from viewport arg
  - Skip titleblock zone (reuse landmark_extractor TITLE_BLOCK_* constants)

ADD tests/test_line_extractor.py with a synthetic PNG (white bg, one thick black diagonal)
  asserting ≥1 polyline with endpoints near expected fractional corners.
```

**Manual:** Not applicable for CV core; use synthetic fixture.

**TEST:**
```bash
cd backend && ./venv/bin/python -m pytest tests/test_line_extractor.py -q --tb=short
```

---

# Phase S — Symbol detection

- [x] **S-1** Symbol crop export + labeling README

**PROMPT — copy below:**

```
PR-S step S-1: Symbol training data export.

ADD backend/scripts/export_symbol_crops.py
  - Input: drawing_id, optional viewport_id
  - Rasterize page; sliding window OR contour proposals from landmark_extractor
  - Write crops to data/symbol_crops/{class_or_unknown}/
  - Write manifest.csv: path, drawing_id, page, x0,y0,x1,y1 (fractional)

ADD backend/data/symbol_crops/README.md with labeling instructions:
  Classes v1 (sanitary): ssmh, ssco, callout_bubble, north_arrow, scale_bar, other
  Tool: Roboflow / CVAT / label manually into folders
  Target: ≥200 crops per class before training
```

**Manual labeling:**
1. Run export for aux C4.20 + master 661.
2. Sort crops into class folders.
3. Keep a `holdout/` set never used in training.

**TEST:** manifest.csv has rows; README exists.

---

- [x] **S-2** Detector inference wrapper (weights optional)

**PROMPT — copy below:**

```
PR-S step S-2: Symbol detector module.

ADD backend/ai/pipelines/symbol_detector.py

def detect_symbols(
    rendition_png: Path,
    *,
    weights_path: Path | None,
    viewport: DrawingViewport | None = None,
    conf_threshold: float = 0.25,
) -> list[SheetSymbol]:
  - If weights_path missing, return [] and log symbol_detector_weights_missing
  - Else run ultralytics YOLO (or onnxruntime) on full page or viewport crop
  - Map boxes to fractional page coords
  - Set viewport_id via assign_viewport_id

ADD config hook SYMBOL_DETECTOR_WEIGHTS_PATH in config/settings if pattern exists.

Do not block indexing if weights absent — digitization graph can have symbols=[].
```

**Manual symbols (no YOLO yet):**
```bash
# After pick_fractional_point for a manhole center, insert via small script or SQL:
# symbol_class=ssmh, bbox around point, viewport_id=plan, detector=manual, confidence=1.0
```

**TEST:** unit test with weights_path=None returns [].

---

- [x] **S-3** Persist symbols table

**PROMPT — copy below:**

```
PR-S step S-3: drawing_symbols table.

ADD model DrawingSymbol (drawing_id, page, symbol_class, bbox_json, viewport_id nullable,
  confidence, detector, meta_json).
Migration + upsert helper in services/sheet_digitization.py.
```

**TEST:** alembic upgrade; insert/read roundtrip test.

---

# Phase A — Association (LLM semantics only)

- [x] **A-1** Associate labels ↔ symbols with known boxes

**PROMPT — copy below:**

```
PR-A step A-1: Vision/LLM association over proposals.

ADD backend/ai/pipelines/sheet_association.py

def associate_labels_to_symbols(
    labels: Sequence[SheetLabel],
    symbols: Sequence[SheetSymbol],
    *,
    legend_session=None,
    project_id=None,
) -> list[dict]:
  Heuristic first: nearest label above/beside symbol within fractional threshold.
  Optional: call existing openai_vision on a crop montage ONLY to pick best label index
  for a symbol — never to output new coordinates.

Reuse legend_lookup.expand_abbreviation / find_codes_for_term for class normalization.
```

**Manual:** Skip LLM; nearest-neighbor heuristic is enough for v1 tests.

**TEST:** synthetic label+symbol pair associates correctly.

---

# Phase D — Digitization orchestrator + wire-in

- [x] **D-1** `digitize_drawing_page` service

**PROMPT — copy below:**

```
PR-D step D-1: Orchestrate page digitization.

ADD backend/services/sheet_digitization.py

def digitize_drawing_page(session, drawing_id, page=1, *, rendition_png: Path) -> SheetEntityGraph:
  1. load_viewports (required for multi-scale; empty → graph.meta["viewport_warning"]=True)
  2. labels from drawing_text_elements (existing OCR index) + assign_viewport_id
  3. lines = extract_line_polylines per viewport (and/or full page then assign)
  4. symbols = detect_symbols (may be empty)
  5. associations = associate_labels_to_symbols
  6. return SheetEntityGraph

Persist graph JSON on drawing.meta["sheetEntityGraph"] for v1 (or normalized tables).

Hard rule: if converting any length to feet, call scale_for_geometry — never drawings.scale_json alone.
```

**TEST:**
```bash
cd backend && ./venv/bin/python -m pytest tests/test_sheet_digitization.py -q --tb=short
```

---

- [x] **D-2** Hook into drawing index job (non-blocking)

**PROMPT — copy below:**

```
PR-D step D-2: After successful OCR index, optionally digitize.

MODIFY backend/services/drawing_index_jobs.py (or master_drawing_indexer completion path):
  - If settings.sheet_digitization_enabled (default False), call digitize_drawing_page
  - Catch/log failures; never fail the index job solely because YOLO weights missing
  - Log counts: viewports, labels, symbols, lines
```

**Manual enable:** set env `SHEET_DIGITIZATION_ENABLED=true` for project 2 only once viewports seeded.

**TEST:** index job still succeeds with digitization disabled.

---

- [x] **D-3** Feed registration / scope (replace hand seeds gradually)

**PROMPT — copy below:**

```
PR-D step D-3: Use digitized controls when available.

MODIFY registration_from_survey / seed_master_registration_controls flow:
  - Prefer DrawingSymbol / SheetLabel stations inside viewport kind=plan
  - Fall back to manual DrawingSurveyPoint seed (existing script)
  - When projecting aux→master, ensure both endpoints use plan viewports (ignore section geometry)

MODIFY scope_line_tracer:
  - Prefer SheetLine polylines inside plan viewport over vision trace when confidence high
  - Tag investigation meta with viewport_id used

Document in Notes/sewer_scope_precision_plan.md a one-liner: multi-scale handled by sheet_digitization_plan Phase V.
```

**Manual fallback (still supported):**
```bash
cd backend
./venv/bin/python scripts/pick_fractional_point.py --image … --x … --y …
# edit _UCSF_MASTER_CONTROLS / _UCSF_AUX_CONTROLS
./venv/bin/python scripts/seed_master_registration_controls.py --rerun-match
```

**TEST:** existing registration + scope tests still pass; add one test that section-viewport geometry is not used for plan registration.

---

# Phase E — Eval / regression

- [x] **E-1** Digitization fixtures + multi-scale unit gate

**PROMPT — copy below:**

```
PR-E step E-1: Regression for multi-scale.

ADD tests/test_viewport_scale_multiscale_gate.py:
  Fixture viewports plan=20 ft/in, section=4 ft/in
  Identical fractional segment length → feet_plan / feet_section == 20/4 == 5
  Fail if implementation uses a single global scale for both.

ADD optional scripts/eval_sheet_digitization.py --drawing-id 1501 printing entity counts.
```

**TEST:**
```bash
cd backend && ./venv/bin/python -m pytest tests/test_viewport_scale.py tests/test_viewport_scale_multiscale_gate.py -q --tb=short
```

---

## Manual cookbook (bookmark)

| Task | Command / action |
|------|------------------|
| Export page PNG | `python scripts/export_drawing_page_png.py --drawing-id ID --page 1 --out …` |
| Pixel → fractional | `python scripts/pick_fractional_point.py --image … --x … --y …` |
| Seed multi-scale viewports | Edit `_UCSF_C420_VIEWPORTS` → `python scripts/seed_drawing_viewports.py --drawing-id 1501` |
| Seed registration controls | Edit `_UCSF_*_CONTROLS` → `python scripts/seed_master_registration_controls.py --rerun-match` |
| Label symbols | `python scripts/export_symbol_crops.py` → sort into `data/symbol_crops/{class}/` |
| Enable auto digitize | `SHEET_DIGITIZATION_ENABLED=true` after V-3 seeded |

---

## Definition of done

- [ ] C4.20 has **≥2 viewports** (plan + section) with **different** `real_feet_per_paper_inch`
- [x] Feet conversion tests prove plan vs section diverge correctly
- [ ] Line extractor returns fractional polylines inside a viewport crop
- [ ] Symbol detector module exists (weights optional); manual symbol insert works
- [ ] Digitization does not break drawing index when disabled
- [ ] Registration/scope prefer **plan** viewport entities; section never silently scales plan geometry
- [ ] Manual pick/seed path still works end-to-end without YOLO

---

## Out of scope (explicit)

- Client CAD/DWG import
- Full GIS / state-plane georeferencing (sheet fractional + local feet first)
- Training YOLO in CI (train offline; commit weights path via env)
- Replacing legend DB with vision-only legend reading

---

*Created: 2026-08-27 — Sheet digitization + **per-viewport multi-scale calibration** as a first-class hard rule.*
