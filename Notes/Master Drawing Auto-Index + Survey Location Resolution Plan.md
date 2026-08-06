# Master Drawing Auto-Index + Survey-Grade Location Resolution Plan

**Document version:** 2.0 (hybrid)  
**Supersedes:** `Notes/Master Drawing Auto-Index Implementation Plan.md` (Phases 0–8 only)  
**Golden regression case:** Project `2`, master drawing `661`, inspection run `435`, evidence `357`, linked install sheet `C4.20`, Utility MR (NPC-5) sanitary sewer corridor near Future Hospital Building.

---

## 1. Problem statement

### 1.1 What works today (Phases 0–8 — largely implemented)

| Component | File(s) | Status |
|-----------|---------|--------|
| OCR index job | `backend/services/drawing_index_jobs.py`, `backend/ai/pipelines/master_drawing_indexer.py` | Implemented |
| `drawing_text_elements` table | `backend/models/drawing_text_element.py` | Implemented |
| Scale parser | `backend/ai/pipelines/drawing_scale_parser.py` | Implemented |
| Legend tagger | `backend/services/master_drawing_legend_tagger.py` | Implemented |
| Auto regions | `backend/ai/pipelines/master_drawing_region_builder.py` | Implemented |
| Clue tile matcher | `backend/ai/pipelines/candidate_tile_selector.py` | Implemented |
| Inspection match job | `backend/services/inspection_matching_jobs.py` | Implemented |
| Index API/UI | `backend/services/drawing_index_api.py`, `client/src/lib/api/drawing_index.ts` | Implemented |
| Location resolver (Case A/B) | `backend/ai/pipelines/drawing_location_resolver.py` | Implemented but **not wired into `inspection_match` job** |

### 1.2 Why run #435 failed (`no_match`)

1. **`inspection_match` job searches master drawing 661 only** — rich station/N/E data lives on linked sheet C4.20 OCR text, not in master's indexed tiles.
2. **Clue matcher is substring-only** — `"SS"` / `"sanitary sewer"` on a campus site plan is ambiguous; no coordinate anchor.
3. **`RegistrationTransform.apply()` ignores `rotation_degrees`** — upside-down sheets break geometric compare.
4. **Sheet refs extracted but not used for matching** — `evidence_linking.py` links C4.20; resolver explicitly drops `SHEET_IDENTIFIER` terms.
5. **Two parallel pipelines not unified** — `inspection_mapping.py` uses `drawing_location_resolver`; `inspection_matching_jobs.py` uses `candidate_tile_selector` only.

### 1.3 Goal

On evidence upload, automatically place inspection location on the master drawing using the same signals a human uses. **All applicable methods run; the highest `internal_score` wins** (§13d). Signal reliability order below is **tie-break only** when scores are within `0.01`:

1. **N/E survey coordinates** (strongest — rotation-invariant)
2. **Inspection type + location term** (existing Case B)
3. **Geometric alignment after true-north normalization** (fixed Case A)
4. **Landmark contour fingerprint** (fallback when coords fail)
5. **Sheet cross-refs** — not a resolver method; **narrows candidate drawings/pages before steps 1–4**

---

## 2. Target architecture

```mermaid
flowchart TD
    subgraph ingest [Master ingest — on drawing upload]
        A[POST /drawings] --> B[drawing_render]
        B --> C[drawing_index job]
        C --> D[drawing_text_elements OCR]
        C --> E[scale_json + page_meta_json]
        C --> F[legend enrichment]
        C --> G[auto drawing_regions]
        C --> H[NEW: survey_point extraction]
        C --> I[NEW: keyplan rotation detection]
        C --> J[NEW: landmark contour index]
    end

    subgraph evidence [Evidence upload]
        K[POST evidence] --> L[LLM extraction + clues]
        K --> M[evidence_linking sheet refs]
        K --> N[linked PDF OCR merge]
        L --> O[NEW: survey_point extraction on evidence]
        M --> P[NEW: candidate drawing/page filter]
    end

    subgraph match [Inspection match job — unified]
        P --> Q[Ranker]
        O --> Q
        H --> Q
        D --> Q
        G --> Q
        Q --> R[drawing_location_resolver extended]
        R --> S[DrawingOverlay + match_status]
    end
```

**Coordinate system everywhere:** normalized fractional bbox `{x0, y0, x1, y1}` in range `[0.0, 1.0]`, origin top-left, x right, y down — same as `document_text_extraction.BoundingBox.to_fractional()`.

---

## Part I — Master Drawing Auto-Index (Phases 0–8)

> **Implementation status:** Complete in codebase. Retained here as reference for Phase 9+ dependencies. Do not re-implement unless a test fails.

### Phase 0 — Data model & config

#### 0a. `drawing_text_elements` (exists)

```python
# backend/models/drawing_text_element.py — DO NOT CHANGE SCHEMA for Phase 9
master_drawing_id: int  # FK drawings.id
page: int               # 1-based
text: str
text_normalized: str    # lower/strip
bbox_json: {"x0","y0","x1","y1"}  # normalized 0–1
ocr_confidence: float   # default 1.0
legend_expansion: str | None
legend_codes_json: list[str] | None
source: "native_pdf" | "tesseract" | "openai_vision"
```

Indexes: `(master_drawing_id)`, `(master_drawing_id, page)`, `(text_normalized)`.

#### 0b. `drawings.scale_json` and `drawings.page_meta_json` (exists)

```python
scale_json = {
    "raw_text": "1\" = 10'",
    "paper_inches_per_real_foot": 0.1,      # 1 inch paper / 10 feet real
    "real_feet_per_paper_inch": 10.0,
    "horizontal": {"numerator": 1, "denominator": 10, "units": "in=ft"},
    "confidence": float,                     # 0.0–1.0
    "source_bbox": [x0, y0, x1, y1],
    "page": 1,
}

page_meta_json = [{
    "page": 1,
    "width_pt": float,    # PDF MediaBox width in points (72 pt = 1 inch)
    "height_pt": float,
    "width_px": int,      # from DrawingRendition
    "height_px": int,
    "rotation": int,      # PyMuPDF page.rotation — PDF box rotation ONLY (0|90|180|270)
    # Phase 9 adds:
    # "true_north_rotation_deg": float,   # keyplan-detected, see Phase 11
    # "true_north_source": str,           # "keyplan_cv" | "orientation_text" | "pdf_rotation" | "manual"
    # "keyplan_bbox": [x0, y0, x1, y1],
}]
```

Physical size conversion (existing, use in contour step):

```python
real_width_ft = normalized_width * (width_pt / 72.0) * scale_json["real_feet_per_paper_inch"]
```

#### 0c. Index status on `drawings` (exists)

```python
index_status: "pending" | "processing" | "ready" | "failed"
index_error: str | None
indexed_at: datetime | None
index_stats_json: {
    "pages": int,
    "text_elements": int,
    "regions": int,
    "scale_found": bool,
    # Phase 9 adds:
    "survey_points": int,
    "landmarks": int,
    "keyplan_detected_pages": int,
}
```

#### 0d. Config (`backend/config.py` — exists)

| Env var | Default | Meaning |
|---------|---------|---------|
| `DRAWING_INDEX_ENABLED` | `true` | Skip index jobs when false |
| `DRAWING_INDEX_TILE_SIZE_NORMALIZED` | `0.08` | Grid tile size (8% of page) |
| `DRAWING_INDEX_MIN_CLUSTER_WORDS` | `2` | Min words per OCR cluster |
| `DRAWING_INDEX_OCR_MAX_PAGES` | `0` | `0` = all pages |
| `DRAWING_INDEX_AUTO_REGION_MODE` | `cluster` | `cluster` \| `grid` \| `hybrid` |

Region builder constants (do not change without updating tests):

| Constant | Value | File |
|----------|-------|------|
| `_MIN_OCR_CONFIDENCE` | `0.5` | `master_drawing_region_builder.py` |
| `_CLUSTER_BUCKET_SIZE` | `0.04` | same |
| `_FIXED_GRID_DIVISIONS` | `12` | same |
| `TITLE_BLOCK_X_MIN` | `0.75` | `drawing_scale_parser.py` |
| `TITLE_BLOCK_Y_MIN` | `0.75` | same |
| `_BBOX_OVERLAP_THRESHOLD` | `0.5` | `candidate_tile_selector.py` |
| `MATCH_SCORE_THRESHOLD` | `0.75` | `inspection_match_persistence.py` |
| `LINKED_CONTENT_WORD_BUDGET` | `6000` words | `linked_attachment_merge.py` |

---

### Phase 1 — `drawing_index` job (exists)

- **Enqueue:** chained after `drawing_render` completes (`drawing_index_jobs.py`).
- **Idempotency:** delete all `drawing_text_elements` for drawing; delete only regions where `geometry.meta.source == "auto_index"`; preserve human-drawn regions.
- **Phase 9 extension:** also delete/replace `drawing_survey_points` and `drawing_landmarks` where `source == "auto_index"`.

---

### Phase 2 — OCR ingest (exists)

Module: `backend/ai/pipelines/master_drawing_indexer.py`

Pipeline: `open_storage_path` → `extract_document()` → bulk insert `DrawingTextElement` → legend enrich → auto regions → persist scale/page_meta.

---

### Phase 3 — Scale extraction (exists)

Module: `backend/ai/pipelines/drawing_scale_parser.py`

Title-block scan region: `x >= 0.75 AND y >= 0.75` on page 1 first; fallback full page.

---

### Phase 4 — Legend enrichment (exists)

Module: `backend/services/master_drawing_legend_tagger.py`

Uses `scripts/seed_legend_reference.py` + `backend/data/legend_seed_data.py`.

---

### Phase 5 — Auto regions (exists)

Module: `backend/ai/pipelines/master_drawing_region_builder.py`

Modes: `cluster` (bucket `0.04`), `grid` (`12×12`), `hybrid`.

---

### Phase 6 — Clue matching (exists, extend in Phase 13)

Module: `backend/ai/pipelines/candidate_tile_selector.py`

Priority: text elements → regions → dedupe by overlap ≥ `0.5`.

Score formula (existing):

```python
internal_score = tile.confidence + max(matched_clue.confidence)
# tile.confidence: 0.75 if tagged region, 0.50 untagged, 1.0 for direct text element match
# matched → status "matched" if internal_score >= 0.75
```

---

### Phase 7 — API & UI (exists)

| Endpoint | Purpose |
|----------|---------|
| `GET /projects/{pid}/drawings/{id}/index-status` | Status + stats |
| `POST /projects/{pid}/drawings/{id}/reindex` | Manual reindex |
| `GET /projects/{pid}/drawings/{id}/text-elements?page=&limit=` | Debug OCR |
| Phase 9 adds: `GET .../survey-points`, `GET .../landmarks` | Debug survey index |

UI: index spinner, stats line, distinguish `index_pending` vs `no_match`.

**UI fix (Phase 14 — required for run #435):**

- Poll `GET /inspections/{evidence_id}/match-status` every `2000 ms` until status ∉ `{index_pending}` or `30` attempts (60 s max).
- Pass **evidence id** (357), not run id (435), to match-status endpoint.
- Refetch overlays when job completes.

---

### Phase 8 — Tests (exists)

| Test file | Covers |
|-----------|--------|
| `test_drawing_scale_parser.py` | Scale regex |
| `test_master_drawing_indexer.py` | OCR persist |
| `test_master_drawing_legend_tagger.py` | SS expansion |
| `test_master_drawing_region_builder.py` | Auto regions |
| `test_candidate_tile_selector.py` | Text element match |
| `test_upload_drawing_enqueues_index_job.py` | Upload chain |
| `test_master_drawing_index_e2e.py` | Integration |

---

## Part II — Survey-Grade Location Resolution (Phases 9–14)

### Phase 9 — Survey point extraction & coordinate matching

**Priority:** Highest. Rotation-invariant. Implements user step **#1 (N/E coordinate OCR as first-class match key)**.

**Default text scope — full document, no assumed region:** Most evidence is a full inspection form, photo-with-caption, or dense install sheet (e.g. C4.20) — not a pre-cropped highlight. N/E, station, and structure-label regexes must run across the **entire evidence document every time**. Do not assume upstream pipeline has already scoped text to "the relevant part." Optional scoping (click point, highlight bbox) may **boost** matches only; when absent, degrade gracefully to full-document scan (§9f).

#### 9a. New table: `drawing_survey_points`

```python
# backend/models/drawing_survey_point.py
class DrawingSurveyPoint(Base):
    __tablename__ = "drawing_survey_points"

    id: int PK
    drawing_id: int FK drawings.id ON DELETE CASCADE
    page: int                          # 1-based
    northing: float                    # state-plane feet, 6–8 digits + decimals
    easting: float
    station: str | None                # e.g. "10+05.00"
    structure_label: str | None        # e.g. "SSMH", "MH-1", "CO"
    label_bbox_json: dict              # bbox of combined label cluster {x0,y0,x1,y1}
    northing_bbox_json: dict | None
    easting_bbox_json: dict | None
    ocr_confidence: float              # min(confidence of N token, E token)
    source: str                        # "auto_index" | "evidence_extract" | "manual"
    meta_json: dict | None             # raw OCR tokens, pairing_distance_ft, scale_fallback flag
    created_at: datetime
```

Indexes: `(drawing_id, page)`, `(northing, easting)` — use application-level tolerance query, not exact index equality.

#### 9b. Extraction module

**New file:** `backend/ai/pipelines/survey_point_extractor.py`

**Input (master index path):** `list[PositionedWord]` or `list[DrawingTextElement]` for one page, plus **`scale_json`** and **`page_meta_json`** for that page (required for pairing gates).

**Input (evidence path — §9d/§9f):** full evidence file via `extract_document()` → **all pages**, all positioned words; or merged `evidence.text_content` + linked supplemental text when positioned bboxes unavailable. Never require a pre-scoped text slice or highlight region.

**Why physical feet, not normalized fractions:** A fixed normalized gap (e.g. `0.15` page width) represents ~600 ft on a `1"=40'` site plan but ~15 ft on a `1"=1'-0"` detail. With §9f full-document evidence (any scale, uncropped page), normalized gates misfire **more often** than on tight crops. Pairing gates must use **`real_feet_per_paper_inch` from `scale_json` on both master and evidence sides** when scale is extractable; normalized-fraction gates are **last resort only** (see scale resolution below).

**Regex patterns (compile once):**

```python
# Northing — California State Plane feet (UCSF observed: 2131764.84)
_NORTHING_RE = re.compile(
    r"\bN\s*(?:=|:)?\s*(\d{6,8}(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)

# Easting — observed: 6051541.82
_EASTING_RE = re.compile(
    r"\bE\s*(?:=|:)?\s*(\d{6,8}(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)

# Station — e.g. 10+05, 10+05.00, STA 10+05
_STATION_RE = re.compile(
    r"\b(?:STA\.?\s*)?(\d{1,2}\+\d{2}(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)

# Structure labels near coords
_STRUCTURE_RE = re.compile(
    r"\b(SSMH|SSMH-\d+|MH-?\d+|CO-?\d+|SMH|DMH|CB|DI)\b",
    re.IGNORECASE,
)
```

**Physical distance helpers (use on every pairing decision):**

```python
POINTS_PER_INCH = 72.0

# Pairing gates — real-world feet on the sheet (preferred mode)
NE_PAIR_MAX_DISTANCE_FT = 15.0        # hard reject N↔E pairing beyond this
NE_PAIR_HORIZONTAL_MAX_FT = 12.0      # N and E usually on same line (side-by-side)
NE_PAIR_VERTICAL_MAX_FT = 8.0         # or stacked on adjacent lines
STATION_ATTACH_MAX_FT = 25.0          # station callout may sit slightly farther
STRUCTURE_ATTACH_MAX_FT = 25.0        # SSMH/MH label near coordinate block

# Last-resort normalized gates — ONLY when no scale extractable (see resolve_pairing_scale)
NE_PAIR_MAX_DISTANCE_NORM = 0.12        # deprecated primary path; fallback only
NE_PAIR_HORIZONTAL_MAX_NORM = 0.15
NE_PAIR_VERTICAL_MAX_NORM = 0.05
STATION_ATTACH_MAX_NORM = 0.08
STRUCTURE_ATTACH_MAX_NORM = 0.08

SCALE_FALLBACK_REAL_FEET_PER_PAPER_INCH = 10.0  # UCSF campus default when evidence scale unparseable but page dims known

@dataclass(frozen=True)
class PairingScaleContext:
    mode: Literal["physical", "normalized_fallback"]
    scale_json: dict | None
    page_meta: dict
    real_feet_per_paper_inch: float | None
    scale_source: str  # "evidence_title_block" | "linked_drawing" | "master_index" | "campus_default" | "none"

def resolve_pairing_scale(
    *,
    scale_json: dict | None,
    page_meta: dict,
    scale_source: str,
) -> PairingScaleContext:
    """
    Evidence-side scale resolution (call before pairing on every page):
      1. scale_json parsed from evidence PDF title block (parse_scale_from_words at upload)
      2. Else scale_json from linked auxiliary drawing (C4.20 via EvidenceDrawingLink)
      3. Else campus default (10.0 ft/in) IF page_meta has width_pt/height_pt
      4. Else mode = normalized_fallback (no real_feet_per_paper_inch available)
    """
    if scale_json and float(scale_json.get("confidence", 0)) >= 0.50:
        return PairingScaleContext(
            mode="physical",
            scale_json=scale_json,
            page_meta=page_meta,
            real_feet_per_paper_inch=float(scale_json["real_feet_per_paper_inch"]),
            scale_source=scale_source,
        )
    if page_meta.get("width_pt") and page_meta.get("height_pt"):
        return PairingScaleContext(
            mode="physical",
            scale_json=None,
            page_meta=page_meta,
            real_feet_per_paper_inch=SCALE_FALLBACK_REAL_FEET_PER_PAPER_INCH,
            scale_source="campus_default",
        )
    return PairingScaleContext(
        mode="normalized_fallback",
        scale_json=None,
        page_meta=page_meta,
        real_feet_per_paper_inch=None,
        scale_source="none",
    )

def normalized_delta_to_feet(
    dx_norm: float,
    dy_norm: float,
    *,
    page_width_pt: float,
    page_height_pt: float,
    real_feet_per_paper_inch: float,
) -> tuple[float, float]:
    """Convert centroid delta in normalized page coords to feet on the ground."""
    page_width_in = page_width_pt / POINTS_PER_INCH
    page_height_in = page_height_pt / POINTS_PER_INCH
    dx_ft = abs(dx_norm) * page_width_in * real_feet_per_paper_inch
    dy_ft = abs(dy_norm) * page_height_in * real_feet_per_paper_inch
    return dx_ft, dy_ft

def pairing_passes_gates(
    ax: float, ay: float, bx: float, by: float,
    *,
    ctx: PairingScaleContext,
    horizontal_max_ft: float = NE_PAIR_HORIZONTAL_MAX_FT,
    vertical_max_ft: float = NE_PAIR_VERTICAL_MAX_FT,
    max_distance_ft: float = NE_PAIR_MAX_DISTANCE_FT,
) -> tuple[bool, float]:
    """Returns (passes, distance_metric). distance_metric is feet or normalized depending on mode."""
    dx_norm = abs(bx - ax)
    dy_norm = abs(by - ay)
    dist_norm = math.hypot(dx_norm, dy_norm)

    if ctx.mode == "physical":
        assert ctx.real_feet_per_paper_inch is not None
        dx_ft, dy_ft = normalized_delta_to_feet(
            dx_norm, dy_norm,
            page_width_pt=float(ctx.page_meta["width_pt"]),
            page_height_pt=float(ctx.page_meta["height_pt"]),
            real_feet_per_paper_inch=ctx.real_feet_per_paper_inch,
        )
        dist_ft = math.hypot(dx_ft, dy_ft)
        ok = (
            dx_ft <= horizontal_max_ft
            and dy_ft <= vertical_max_ft
            and dist_ft <= max_distance_ft
        )
        return ok, dist_ft

    # Last resort: normalized fractions (plain-text extraction w/ no page dims)
    ok = (
        dx_norm <= NE_PAIR_HORIZONTAL_MAX_NORM
        and dy_norm <= NE_PAIR_VERTICAL_MAX_NORM
        and dist_norm <= NE_PAIR_MAX_DISTANCE_NORM
    )
    return ok, dist_norm
```

**Evidence-side scale (`resolve_scale_for_evidence` in §9d):** parse scale from each evidence page's title block during upload (reuse `drawing_scale_parser.parse_scale_from_words`). For inspection forms whose coordinates live on a **linked install sheet** (C4.20), inherit `scale_json` from the linked `Drawing` row when evidence file has no parseable scale. Store per-page context on `DocumentExtraction.meta_json["pairing_scale_by_page"]`.

**Pairing algorithm (deterministic):**

For each page, collect token matches with bboxes. Resolve `PairingScaleContext` once per page via `resolve_pairing_scale()`. Use token **centroids** in normalized space; evaluate gates via `pairing_passes_gates()`.

1. For each `N` token at centroid `(n_x, n_y)` with value `n_val`:
2. Find `E` token candidates where `pairing_passes_gates(n, e, ctx=ctx)` returns `True`.
3. If multiple E candidates pass, pick minimum distance metric (feet in `physical` mode, normalized in fallback mode).
4. Reject pair if no E candidate passes gates.
5. Attach nearest `_STATION_RE` token using same gate function with `STATION_ATTACH_MAX_FT` (physical) or `STATION_ATTACH_MAX_NORM` (fallback).
6. Attach nearest `_STRUCTURE_RE` token similarly.
7. `ocr_confidence = min(n_conf, e_conf)`.
8. Reject point if `ocr_confidence < 0.40`.

Store on each survey point `meta_json`:
- `pairing_distance_ft` when `mode == "physical"`
- `pairing_distance_norm` when `mode == "normalized_fallback"`
- `pairing_scale_source`, `pairing_scale_mode`

**Scale resolution priority (master + evidence):**

| Priority | Source | Mode |
|----------|--------|------|
| 1 | `scale_json` from same document title block (`confidence >= 0.50`) | `physical` |
| 2 | `scale_json` from linked auxiliary drawing (C4.20) | `physical` |
| 3 | Page dims known, scale unparseable → campus default `10.0` ft/in | `physical` |
| 4 | No scale and no page dims (plain-text-only extraction) | `normalized_fallback` |

Set `meta_json.scale_fallback = true` when priority ≥ 3. Log warning when `mode == "normalized_fallback"`.

**Output:** `list[SurveyPointRecord]`.

#### 9c. Coordinate match algorithm

**New file:** `backend/ai/pipelines/survey_point_matcher.py`

```python
COORD_MATCH_TOLERANCE_FT = 3.0       # default match
COORD_MATCH_HIGH_CONF_FT = 1.0       # high confidence
COORD_MATCH_REJECT_FT = 5.0          # no match above this

def euclidean_survey_distance_ft(a: SurveyPoint, b: SurveyPoint) -> float:
    return math.hypot(a.northing - b.northing, a.easting - b.easting)

def match_survey_points(
    evidence_points: list[SurveyPoint],
    master_points: list[SurveyPoint],
) -> list[SurveyPointMatch]:
    """
    Greedy 1:1 assignment (v1): for each evidence point (sorted by ocr_confidence desc),
    assign best unmatched master point with distance <= COORD_MATCH_TOLERANCE_FT.
    Returns the single best-scoring match for overlay placement; additional pairs
    are optional audit rows only.
    """
```

**Known simplification (v1 — acceptable for now):**

Greedy nearest-first assignment is **not globally optimal**. With 5+ survey points clustered tightly (e.g. a manhole run with several SSMHs within a few feet), processing evidence points in confidence order can lock an early evidence point to a master point that a later, higher-confidence point needed — producing a suboptimal or **swapped** pairing that optimal assignment (Hungarian / linear sum assignment on the cost matrix) would avoid.

| Situation | Action |
|-----------|--------|
| ≤ 4 evidence points per run (typical) | Keep greedy v1 |
| 5+ clustered points, or swapped assignments in fixtures | Upgrade to Hungarian on `distance_ft` cost matrix (scipy `linear_sum_assignment` or `munkres`) |
| Trigger to revisit | `test_ucsf_run435_coordinate_match` or e2e fixtures show wrong master point chosen when two candidates are within `COORD_MATCH_TOLERANCE_FT` |

**v2 upgrade sketch (when needed):**

```python
# Build cost[i,j] = distance_ft(evidence_i, master_j); inf if > COORD_MATCH_REJECT_FT
# row_ind, col_ind = linear_sum_assignment(cost)
# Emit matches where cost[row,col] <= COORD_MATCH_TOLERANCE_FT
```

Do **not** block PR-A on this — document and test; swap algorithm only if fixtures prove greedy fails.

**Confidence assignment:**

| Condition | `confidence_score` | `ResolutionMethod` |
|-----------|-------------------|-------------------|
| `distance <= 1.0 ft` | `0.98` | `COORDINATE_LOOKUP` |
| `1.0 < distance <= 3.0 ft` | `0.96` | `COORDINATE_LOOKUP` |
| `3.0 < distance <= 5.0 ft` | `0.80` | `COORDINATE_LOOKUP` (needs_review) |
| `distance > 5.0 ft` | no match | — |

**Bbox on master for overlay:** use `label_bbox_json` of matched master point, expanded by `0.01` normalized on each side (minimum visible box).

**Station-only fallback (no N/E on one side):**

If evidence has station `S` and master has station `S'` where normalized station strings match exactly (after stripping `STA.` prefix), and structure labels match (case-insensitive), assign confidence `0.88` — method `STATION_LOOKUP` (new enum value).

#### 9d. Index integration

**Master index** — in `master_drawing_indexer.py`, after text element persist:

```python
survey_points = extract_survey_points_from_elements(
    text_elements,
    scale_json=drawing.scale_json,
    page_meta_json=drawing.page_meta_json,
)
persist_survey_points(db, drawing_id, survey_points, source="auto_index")
```

**Evidence upload (default: full document)** — in `evidence_document_extraction.py` / match orchestrator, **always** run survey extraction over the complete evidence corpus:

```python
def extract_survey_points_from_evidence(
    session,
    evidence: EvidenceRecord,
    *,
    optional_hint_bbox: tuple[float, float, float, float] | None = None,
) -> list[SurveyPointRecord]:
    """
    Default: scan ENTIRE evidence — not a highlight crop, not title-block-only,
    not first-2000-chars. Merge all text sources before regex pass.
    """
    document = extract_document(evidence.storage_path)  # every page
    words = document.all_positioned_words()
    merged_text = build_full_evidence_text(evidence)
    linked_drawings = load_linked_drawings(session, evidence.id)
    auxiliary_points = load_linked_drawing_survey_points(session, evidence.id)

    scale_json = resolve_scale_for_evidence(evidence, linked_drawings)
    page_meta_json = resolve_page_meta_for_evidence(document)

    points_from_words = extract_survey_points_from_elements(
        words,
        scale_json=scale_json,
        page_meta_json=page_meta_json,
        optional_hint_bbox=optional_hint_bbox,
    )
    points_from_text = extract_survey_points_from_plain_text(
        merged_text,
        pairing_ctx=PairingScaleContext(mode="normalized_fallback", ...),  # no bboxes
    )
    return dedupe_survey_points(points_from_words + points_from_text + auxiliary_points)


def resolve_scale_for_evidence(
    evidence: EvidenceRecord,
    linked_drawings: list[Drawing],
) -> dict | None:
    """
    1. DocumentExtraction.meta_json["scale_json"] if parsed at upload from evidence PDF
    2. First linked drawing with index_status=ready and scale_json (e.g. C4.20 at 1"=10')
    3. None → resolve_pairing_scale falls through to campus default or normalized_fallback
    """
    ...
```

Persist on `DocumentExtraction.meta_json["survey_points"]` and `meta_json["pairing_scale_by_page"]` at upload time. Match job reads this — do not re-scan a truncated subset at match time.

**Linked drawings:** when `EvidenceDrawingLink` points to project drawing (e.g. C4.20), include that drawing's indexed `drawing_survey_points` in the evidence candidate set (already full-sheet indexed).

#### 9f. Full-document text scan — pipeline rule

| Rule | Detail |
|------|--------|
| **Default** | Scan entire `evidence.text_content` + linked supplemental text + all OCR pages |
| **Never assume** | That evidence text is pre-scoped to a highlight, click point, or "relevant paragraph" |
| **Optional scoping** | If `optional_hint_bbox` or user pin exists → rank/boost tokens inside hint; **still scan full document** |
| **Degrade gracefully** | When no hint exists (common case) → full-document behavior with no code-path change |

**Pipeline audit — remove implicit subset assumptions:**

| File | Current behavior | Required change |
|------|------------------|-----------------|
| `backend/services/evidence_document_extraction.py` | Runs full-file extraction + linked merge | Ensure `meta_json["survey_points"]` populated from **full** scan (§9d) |
| `backend/services/inspection_matching_jobs.py` | Reads `DocumentClue` from full extraction | OK — verify clues/survey points not filtered by page or bbox before match |
| `backend/services/evidence_linking.py` | `extract_sheet_refs(evidence.text_content)` on full text | **Pattern to follow** — sheet refs already full-document |
| `backend/ai/pipelines/inspection_mapping.py` | `map_document_to_overlays()` uses full `extract_document()` | OK for document path |
| `backend/ai/pipelines/inspection_mapping.py` | `EvidenceInput.bbox` for manual pin path only | OK — bbox is overlay anchor, **not** text scope; do not use to filter OCR/terms |
| `backend/ai/pipelines/inspection_mapping.py` | `_extract_outcomes_llm()` uses `text[:2000]` | OK for LLM outcome summary only — **must not** be the survey/sheet-ref text source |
| `backend/ai/pipelines/inspection_mapping.py` | `_extract_vocabulary_tags()` uses full `text_content` | OK — keep full text |
| `backend/services/match_candidate_scope.py` (new) | — | `build_match_scope()` runs sheet-ref regex on **full** merged evidence text, not first page |

**Anti-pattern to eliminate:** any helper that accepts `evidence_text: str` where callers pass `text_content[:N]`, `text_near_bbox(...)`, or page-1-only OCR without a explicit full-document fallback when hint/bbox is `None`.

#### 9e. Tests

| Test | Assert |
|------|--------|
| `test_survey_point_extractor_pairs_n_e` | `"N 2131764.84"` + `"E 6051541.82"` within 15 ft at `1"=10'` → one point |
| `test_survey_point_extractor_rejects_distant_e` | E token > 15 ft away at same scale → no pair |
| `test_survey_point_pairing_scale_invariant` | same normalized gap pairs at `1"=10'` but rejects at `1"=40'` when gap > 15 ft real |
| `test_survey_point_evidence_uses_linked_drawing_scale` | form has no scale; linked C4.20 has `1"=10'` → evidence pairing uses physical ft |
| `test_survey_point_extractor_campus_default` | evidence has page dims, no parseable scale → `10.0` ft/in, `scale_fallback=true` |
| `test_survey_point_extractor_normalized_last_resort` | plain-text only, no page dims → `pairing_scale_mode=normalized_fallback` |
| `test_survey_point_matcher_3ft` | delta 2.5 ft → confidence 0.96 |
| `test_survey_point_matcher_rejects_6ft` | delta 6.0 ft → no match |
| `test_ucsf_run435_coordinate_match` | evidence 357 coords match master 661 corridor point; if this fails with two candidates within 3 ft, investigate greedy swap → Hungarian (§9c) |
| `test_survey_points_from_full_evidence_text` | N/E in linked C4.20 supplemental text (not page 1 of form) → extracted |
| `test_survey_points_no_hint_scans_all_pages` | multi-page evidence PDF → points found on page 2+ when absent from page 1 |
| `test_survey_points_hint_boost_not_filter` | hint_bbox set → points outside hint still extracted, lower rank |

---

### Phase 10 — Sheet cross-reference candidate narrowing

**Implements user step #4 (cross-reference text extraction).** Cheap, high-confidence search-space reduction.

**Default text scope:** Same as §9f — scan **full merged evidence text** for sheet refs and cross-refs. `build_match_scope()` must not assume evidence text is pre-scoped to a highlight or form header only.

#### 10a. Existing code (reuse, do not rewrite)

`backend/services/evidence_linking.py` — already scans full `evidence.text_content` (correct pattern):

```python
refs = extract_sheet_refs(cast(Optional[str], evidence.text_content))
```

**Extend to full merged corpus** (not base `text_content` alone when linked PDFs present):

```python
def build_full_evidence_text(evidence: EvidenceRecord) -> str:
    """Base upload text + linked supplemental (install sheets). Same merge as extraction pipeline."""
    base = evidence.text_content or ""
    # Include linked attachment OCR already merged into text_content at upload;
    # if stored separately in meta, merge here. Never truncate for sheet-ref scan.
    return base.strip()

def extract_sheet_refs_from_evidence(evidence: EvidenceRecord) -> list[str]:
    return extract_sheet_refs(build_full_evidence_text(evidence))
```

Also extract from `drawing_text_elements` on master (full indexed text, all pages): `"SEE SHEET"`, `"REFER TO SHEET"`, `"ON SHEET"` followed by sheet ref:

```python
SHEET_REF_PATTERNS = (
    re.compile(r"\b([A-Z]{1,3}-?\d{2,4}[A-Z]?)\b", re.IGNORECASE),
    re.compile(r"\b((?:[A-Z]\d+\.)?[A-Z]\d+\.\d{2,4})\b", re.IGNORECASE),
)

_CROSS_REF_RE = re.compile(
    r"\b(?:SEE|REFER\s+TO|ON|DETAIL\s+ON)\s+SHEET\s+"
    r"((?:[A-Z]\d+\.)?[A-Z]\d+\.\d{2,4})\b",
    re.IGNORECASE,
)
```

#### 10b. Candidate drawing filter

**New file:** `backend/services/match_candidate_scope.py`

```python
@dataclass(frozen=True)
class MatchScope:
    master_drawing_id: int
    auxiliary_drawing_ids: tuple[int, ...]   # linked sheets (C4.20)
    preferred_pages: tuple[int, ...]         # default (1,)
    sheet_refs: tuple[str, ...]

def build_match_scope(session, *, evidence_id, master_drawing_id) -> MatchScope:
    """
    1. extract_sheet_refs_from_evidence() on FULL merged evidence text (§10a)
    2. evidence_linking refs → auxiliary_drawing_ids
    3. master OCR cross-refs (all pages) mentioning evidence sheet refs → boost
    4. If no refs: auxiliary_drawing_ids = ()
    """
```

#### 10c. Inspection match job integration

In `run_inspection_match_job()`:

1. Call `resolve_evidence_location()` (Phase 13 orchestrator) — **do not short-circuit** on the first method that returns a candidate.
2. The orchestrator calls `build_match_scope()` internally, then runs **all** applicable matchers and picks the winner by score (§13d–§13e).
3. Persist the winning `(method, bbox, confidence)`; record **all** scored candidates in `DrawingMatchCandidate` for audit (not just the winner).

**Important:** Sheet refs do **not** directly produce a master bbox. They only restrict which drawings/pages supply survey points and clues.

#### 10d. Tests

| Test | Assert |
|------|--------|
| `test_build_match_scope_c420` | evidence with C4.20 ref in **linked supplemental text** → auxiliary drawing id resolved |
| `test_cross_ref_extract_on_master` | master text "SEE SHEET C4.20" → ref extracted |
| `test_sheet_refs_full_document_not_truncated` | ref appears after char 2000 in merged text → still found |

---

### Phase 11 — True-north rotation normalization (keyplan)

**Implements user step #2 (sheet rotation normalization via keyplan/north-arrow).** Required before geometric alignment and contour matching.

**Highest-risk phase in this plan.** Keyplan icons on UCSF sheets are multi-part graphics (building outline + circle-and-cross north arrow), not a simple rigid rectangle. **Do not** derive rotation from `minAreaRect` longest-edge angles — multi-part contour geometry is noisy and does not reliably track the north arrow direction.

**Design constraint:** Construction sheets in this project are virtually always drawn at one of **four cardinal rotations** (`0°`, `90°`, `180°`, `270°`) relative to true north — not arbitrary skew angles. Orientation detection should therefore be **discrete 4-way template matching**, not continuous angle estimation.

#### 11a. Extend `page_meta_json` (per page entry)

```python
{
    "page": 1,
    "width_pt": float,
    "height_pt": float,
    "width_px": int,
    "height_px": int,
    "rotation": int,                          # PyMuPDF — unchanged
    "true_north_rotation_deg": float,         # clockwise degrees to rotate INTO true north; cardinal only (0|90|180|270) when source is keyplan_cv or orientation_text
    "true_north_source": str,                 # see detection order below
    "keyplan_bbox": [x0, y0, x1, y1] | None,  # normalized location of best template match
    "keyplan_match_score": float | None,      # NCC score when source is keyplan_cv
    "orientation_text": str | None,           # e.g. "NORTH POINTING DOWN"
}
```

#### 11b. Detection order (first success wins)

**New file:** `backend/ai/pipelines/sheet_orientation_detector.py`

| Step | Method | `true_north_source` | Confidence |
|------|--------|---------------------|------------|
| 1 | OCR orientation callout (loose regex + direction extract) | `orientation_text` | `0.85` |
| 2 | Keyplan CV in title block | `keyplan_cv` | `0.80` |
| 3 | PyMuPDF `page.rotation` mapped to degrees | `pdf_rotation` | `0.60` |
| 4 | Default | `assumed_up` | `0.50`, `true_north_rotation_deg = 0.0` |

**Text orientation (step 1) — primary fallback when keyplan CV fails §3b audit:**

Title blocks use many phrasings, not just `"NORTH POINTING DOWN"`. Observed on UCSF sheets (including U1.C4.20 callout box):

- `NORTH POINTING DOWN`
- `NORTH ARROW POINTS DOWN`
- `SHEET ORIENTED WITH NORTH DOWN`
- `VIEW ORIENTATION: NORTH POINTING SOUTH`

Use a **two-pass** text detector — cheap and high-value; prefer this over pdf_rotation when CV is unavailable.

```python
# Pass 1: loose match — NORTH near a direction/orientation keyword (within 20 chars)
_ORIENTATION_LOOSE_RE = re.compile(
    r"\bNORTH\b.{0,20}\b(POINT(?:S|ING)?|ORIENTED|ORIENTATION|ARROW|VIEW)\b",
    re.IGNORECASE,
)

# Also match "oriented with north <dir>" / "north <dir>" without POINTING
_ORIENTATION_WITH_DIR_RE = re.compile(
    r"\b(?:SHEET\s+)?ORIENTED\s+WITH\s+NORTH\s+(UP|DOWN|LEFT|RIGHT|SOUTH|NORTH|EAST|WEST)\b",
    re.IGNORECASE,
)

# Pass 2: extract cardinal direction word from the matched span (or full line)
_DIRECTION_WORD_RE = re.compile(
    r"\b(UP|DOWN|LEFT|RIGHT|SOUTH|NORTH|EAST|WEST)\b",
    re.IGNORECASE,
)

ORIENTATION_TEXT_TO_DEG = {
    "UP": 0.0,
    "NORTH": 0.0,       # "north pointing north" = sheet upright
    "DOWN": 180.0,
    "SOUTH": 180.0,     # "north pointing south" (U1.C4.20) = upside down
    "LEFT": 90.0,
    "WEST": 90.0,
    "RIGHT": 270.0,
    "EAST": 270.0,
}

def detect_orientation_from_text(page_text: str) -> OrientationResult | None:
    """
    1. Try _ORIENTATION_WITH_DIR_RE first (explicit direction capture).
    2. Else find _ORIENTATION_LOOSE_RE matches; for each, run _DIRECTION_WORD_RE
       on the matched substring and take the LAST direction word (closest to end of phrase).
    3. Map direction → true_north_rotation_deg via ORIENTATION_TEXT_TO_DEG.
    4. Store full matched string in orientation_text for audit.
    """
```

**Examples:**

| OCR snippet | Extracted direction | `true_north_rotation_deg` |
|-------------|--------------------|-----------------------------|
| `NORTH POINTING DOWN` | DOWN | `180.0` |
| `NORTH ARROW POINTS DOWN` | DOWN | `180.0` |
| `SHEET ORIENTED WITH NORTH DOWN` | DOWN | `180.0` |
| `VIEW ORIENTATION: NORTH POINTING SOUTH` | SOUTH | `180.0` |
| `NORTH POINTING UP` | UP | `0.0` |

Scan full page OCR text (not title-block crop only) — orientation callouts on install sheets (C4.20) may sit outside `{x >= 0.75, y >= 0.75}`.

**Keyplan CV (step 2) — discrete 4-way template matching (not minAreaRect):**

Search region (title block):

```python
KEYPLAN_SEARCH = {
    "x0": 0.65, "y0": 0.65, "x1": 1.0, "y1": 1.0,  # superset of TITLE_BLOCK 0.75
}

KEYPLAN_NCC_THRESHOLD = 0.70          # min normalized cross-correlation to accept
KEYPLAN_CARDINAL_ROTATIONS = (0, 90, 180, 270)  # only these — no continuous angles
KEYPLAN_TEMPLATE_PATH = "backend/tests/fixtures/keyplan_template.png"  # crop from C0.00; north arrow points UP at 0°
```

**Why not `minAreaRect`:** The UCSF keyplan is a building outline plus circle-and-cross north arrow. A multi-part contour's "longest edge" does not correlate with north direction. Discrete template matching at 90° increments matches the actual failure mode (sheets flipped in 90°/180° steps, not skewed at odd angles) and is simpler to test.

Algorithm on rendition PNG crop (`DrawingRendition`, page N):

1. Convert `KEYPLAN_SEARCH` to pixel bbox using `width_px`, `height_px`; crop to `search_gray`.
2. Load reference template `keyplan_template.png` (grayscale); template north arrow points **up** at `0°`.
3. For each `rotation_deg` in `KEYPLAN_CARDINAL_ROTATIONS`:
   ```python
   rotated_template = rotate_image(template_gray, rotation_deg)  # cv2.rotate or warpAffine
   if rotated_template larger than search_gray: scale down template to fit
   score_map = cv2.matchTemplate(search_gray, rotated_template, cv2.TM_CCOEFF_NORMED)
   peak_score = score_map.max()
   peak_loc = unravel_argmax(score_map)  # top-left of best match
   ```
4. Track global best `(peak_score, rotation_deg, peak_loc)` across all four rotations.
5. If `peak_score >= KEYPLAN_NCC_THRESHOLD`:
   - `true_north_rotation_deg = float(best_rotation_deg)`  # clockwise rotation needed to normalize sheet → true north
   - `true_north_source = "keyplan_cv"`
   - `keyplan_match_score = peak_score`
   - `keyplan_bbox` = template footprint at `peak_loc`, converted to normalized coords
   - orientation confidence = `0.80`
6. Else: skip to step 3 (pdf_rotation fallback).

**Interpretation:** If the keyplan on the sheet best matches the template when the template is rotated `180°`, the sheet's north arrow points down → `true_north_rotation_deg = 180`.

If no rotation scores ≥ `0.70`: skip to step 3.

#### 11c. Coordinate transform utilities

**New file:** `backend/ai/pipelines/coordinate_frame.py`

```python
def rotate_point(x: float, y: float, degrees: float, cx: float = 0.5, cy: float = 0.5) -> tuple[float, float]:
    """Rotate (x,y) around (cx,cy). degrees clockwise. All normalized 0–1."""
    rad = math.radians(degrees)
    dx, dy = x - cx, y - cy
    cos_r, sin_r = math.cos(rad), math.sin(rad)
    rx = dx * cos_r + dy * sin_r
    ry = -dx * sin_r + dy * cos_r
    return rx + cx, ry + cy

def rotate_bbox(bbox: tuple[float,float,float,float], degrees: float) -> tuple[float,float,float,float]:
    x0,y0,x1,y1 = bbox
    corners = [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
    rotated = [rotate_point(x,y,degrees) for x,y in corners]
    xs = [p[0] for p in rotated]
    ys = [p[1] for p in rotated]
    return min(xs), min(ys), max(xs), max(ys)

def normalize_to_true_north(bbox, page_meta: dict) -> tuple[float,float,float,float]:
    deg = float(page_meta.get("true_north_rotation_deg") or 0.0)
    return rotate_bbox(bbox, deg)
```

#### 11d. Fix `RegistrationTransform.apply()`

**File:** `backend/ai/pipelines/drawing_location_resolver.py`

Replace v1 apply (scale+translate only) with:

```python
def apply(self, x0, y0, x1, y1) -> tuple[float, float, float, float]:
    # 1. Rotate source bbox around source page center (0.5, 0.5) by rotation_degrees
    rx0, ry0, rx1, ry1 = rotate_bbox((x0,y0,x1,y1), self.rotation_degrees)
    # 2. Scale
    sx0, sy0 = rx0 * self.scale_x, ry0 * self.scale_y
    sx1, sy1 = rx1 * self.scale_x, ry1 * self.scale_y
    # 3. Translate
    return (
        sx0 + self.translate_x,
        sy0 + self.translate_y,
        sx1 + self.translate_x,
        sy1 + self.translate_y,
    )
```

Import `rotate_bbox` from `coordinate_frame.py`.

#### 11e. Index job integration

After OCR in `master_drawing_indexer.py`:

```python
for page_entry in page_meta_json:
    orientation = detect_sheet_orientation(rendition_png, text_elements_for_page, page_entry)
    page_entry.update(orientation)
```

#### 11f. Pre-build validation (human checklist)

Before implementing step 2 CV, verify on **5 sheets** from project 2:

- [ ] Keyplan icon present in `{x >= 0.65, y >= 0.65}` on ≥ 4/5 sheets
- [ ] Same icon family (building outline + circle-and-cross north arrow — not a simple bar/rectangle)
- [ ] Crop one clean template from C0.00 → `backend/tests/fixtures/keyplan_template.png`; confirm NCC ≥ `0.70` against itself at `0°`
- [ ] Spot-check all four rotations: template at `0°/90°/180°/270°` against a known upside-down sheet (e.g. C4.20) picks the correct cardinal angle

If audit fails: rely on step 1 (`NORTH POINTING DOWN` text) + manual `true_north_rotation_deg` override API. **Do not** ship minAreaRect or continuous-angle fallback.

#### 11g. Tests

| Test | Assert |
|------|--------|
| `test_orientation_text_down` | `"NORTH POINTING DOWN"` → `180.0` deg |
| `test_orientation_text_arrow_points_down` | `"NORTH ARROW POINTS DOWN"` → `180.0` deg |
| `test_orientation_text_oriented_with_north_down` | `"SHEET ORIENTED WITH NORTH DOWN"` → `180.0` deg |
| `test_orientation_text_north_pointing_south` | `"VIEW ORIENTATION: NORTH POINTING SOUTH"` (U1.C4.20) → `180.0` deg |
| `test_orientation_text_loose_no_direction` | loose match with no direction word → `None` (fall through to CV/pdf) |
| `test_rotate_bbox_180` | `(0.1,0.1,0.2,0.2)` → symmetric flip around center |
| `test_registration_transform_with_rotation` | 180° registration maps evidence bbox to master |
| `test_keyplan_ncc_picks_180` | synthetic crop with keyplan flipped 180° → `true_north_rotation_deg == 180`, score ≥ `0.70` |
| `test_keyplan_ncc_cardinal_only` | winning rotation is always one of `{0, 90, 180, 270}` |
| `test_keyplan_ncc_below_threshold_falls_back` | all four rotations score < `0.70` → `true_north_source != "keyplan_cv"` |

---

### Phase 12 — Landmark contour fingerprinting

**Implements user step #3 (landmark contour fingerprinting).** Fallback only — runs when Phase 9 returns zero matches.

**Least-trustworthy signal in this plan.** Utility pipe lines on UCSF sheets cross directly through tank and building outlines, corrupting Canny edge detection and Hu-moment fingerprints. Contour matching may suggest a bbox for human review but must **never** auto-promote to `matched` until real accuracy data exists.

**Evidence-type gate (required):** Contour/Hu-moment matching is only valid when the **evidence document itself** is line-art (a scanned or marked-up drawing sheet). It is **not** valid for field photographs — a photo of a trench has no clean vector outlines to match against plan landmarks. See §12f and §13a — do not invoke `landmark_matcher` unless `evidence_kind == "drawing_scan"`.

#### 12a. New table: `drawing_landmarks`

```python
class DrawingLandmark(Base):
    __tablename__ = "drawing_landmarks"

    id: int PK
    drawing_id: int FK
    page: int
    landmark_type: str          # "building" | "tank" | "structure" | "road"
    bbox_json: dict             # true-north-normalized bbox
    hu_moments_json: list[float]  # 7 Hu moments (log-transformed)
    contour_hash: str | None    # optional perceptual hash
    source: str                 # "auto_index"
    meta_json: dict | None
    created_at: datetime
```

#### 12b. Extraction

**New file:** `backend/ai/pipelines/landmark_extractor.py`

**Two call sites — same algorithm, different inputs:**

| Call site | When | Scope |
|-----------|------|--------|
| **Master index** (`master_drawing_indexer.py`) | On `drawing_index` job | Full page (minus exclusion zones) → persist to `drawing_landmarks` |
| **Evidence match** (`landmark_matcher.py`) | On contour fallback for `evidence_kind == "drawing_scan"` | **Full evidence page** (minus same exclusion zones) — **not** a pre-cropped highlight region |

**Input:** evidence or master rendition PNG + `page_meta_json` (true-north rotation applied in pixel space before contour extraction).

```python
def extract_landmarks_from_page(
    rendition_png,
    page_meta: dict,
    *,
    optional_hint_bbox: tuple[float, float, float, float] | None = None,
) -> list[LandmarkRecord]:
    """
    Always scan the full plan body. optional_hint_bbox is NEVER required.
    If provided (rare: evidence is pre-highlighted), boost contours overlapping
    hint by +0.05 internal rank — do not restrict extraction to hint alone.
    """
```

**Detection (deterministic v1 — no ML):**

1. Exclude title block `{x >= 0.75, y >= 0.75}` and legend block `{x <= 0.35, 0.20 <= y <= 0.85}` (same as region builder) — on **both** master and evidence pages.
2. Canny `(30, 100)` on remaining plan body.
3. Keep closed contours with area:
   - `>= 0.0002 * page_area_normalized` (large enough = building/tank)
   - `<= 0.05 * page_area_normalized` (exclude page border)
4. Classify by aspect ratio `width/height`:
   - `0.8 <= ratio <= 1.2` and area ≥ `0.001` → `tank`
   - `ratio > 1.5` or `ratio < 0.67` → `building`
   - else → `structure`
5. Compute Hu moments: `cv2.HuMoments(cv2.moments(contour)).flatten()` then `-sign(x)*log10(abs(x))` for each.
6. Store each landmark's **own** bbox in true-north-normalized coordinates via `normalize_to_true_north()`. The matched landmark bbox is the region of interest — it is an **output**, not an input assumption.

#### 12c. Matching

**New file:** `backend/ai/pipelines/landmark_matcher.py`

```python
HU_MATCH_THRESHOLD = 0.15   # cv2.matchShapes I2 metric — lower is better
MIN_LANDMARK_MATCHES = 2    # require at least 2 landmark pairs
MIN_SPATIAL_SEPARATION = 0.05  # normalized — matched pairs must be > 5% page apart

def run_landmark_matcher(
    *,
    master_landmarks: list[LandmarkRecord],       # from drawing_landmarks index
    evidence_rendition_png,
    evidence_page_meta: dict,
    optional_hint_bbox: tuple[float, float, float, float] | None = None,
) -> ContourMatchResult | None:
    """
    Evidence-side: extract landmarks from FULL evidence page via extract_landmarks_from_page().
    Do NOT accept a required pre-known highlight bbox — most evidence (e.g. full C4.20 sheet)
    has no upstream highlight region.
    """
    evidence_landmarks = extract_landmarks_from_page(
        evidence_rendition_png,
        evidence_page_meta,
        optional_hint_bbox=optional_hint_bbox,  # filter/boost only, never required
    )
    ...
```

Algorithm:

1. Extract evidence landmarks from **full page** (§12b); load master landmarks from index.
2. Normalize all evidence and master landmarks to true north.
3. Build cost matrix of Hu distances (evidence × master).
4. Greedy assign pairs where `hu_distance <= 0.15`.
5. Require ≥ `2` pairs with consistent relative displacement:
   - Compute vector from evidence landmark A to B: `Δ_ev`
   - Compute vector from master landmark A' to B': `Δ_master`
   - `vector_error = hypot(Δ_ev.x - Δ_master.x, Δ_ev.y - Δ_master.y)`
   - Accept set if `vector_error <= 0.03` normalized for all pairs.
6. **Output bbox (no input highlight assumed):** derive master overlay region from **matched master landmark bboxes** — union of matched master landmarks' `bbox_json`, expanded by `0.01` normalized per side. Do **not** translate a pre-existing evidence highlight bbox; the matched landmarks *are* the region of interest.
   - Optional: if `optional_hint_bbox` was provided and overlaps matched evidence landmarks, add `+0.02` to internal confidence (boost only).
7. Internal confidence (ranking only — **never** `matched` status):
   - `0.70` if 2 landmark pairs
   - `0.72` if 3+ landmark pairs (cap below `MATCH_SCORE_THRESHOLD`; no auto-promotion)
8. Frontend status: **`needs_review` always** for `CONTOUR_MATCH`, regardless of pair count or internal score.

#### 12d. Resolver extension

**File:** `backend/ai/pipelines/drawing_location_resolver.py`

Add enum values:

```python
class ResolutionMethod(str, Enum):
    COORDINATE_LOOKUP = "coordinate_lookup"
    STATION_LOOKUP = "station_lookup"
    CONTOUR_MATCH = "contour_match"
    ALIGNMENT = "alignment"
    REFERENCE_LOOKUP = "reference_lookup"
    UNRESOLVED = "unresolved"
```

Replace priority-ladder routing with **score-first selection**. `detect_resolution_case()` becomes a thin wrapper; the real logic lives in `select_best_location_match()` (§13e).

**Do not** return the first method that passes a threshold — that lets a lower-confidence method win because it appears earlier in an if-chain (e.g. ALIGNMENT at priority-3 beating a coordinate match at `0.80` at priority-0 when scores are mishandled).

```python
@dataclass(frozen=True)
class MethodCandidate:
    method: ResolutionMethod
    confidence: float
    bbox_fractional: tuple[float, float, float, float] | None
    matched_region: MasterRegion | None
    notes: str

def collect_method_candidates(...) -> list[MethodCandidate]:
    """Run every applicable method; skip methods with no signal (confidence 0.0)."""
    candidates: list[MethodCandidate] = []

    if survey_match is not None:
        candidates.append(MethodCandidate(COORDINATE_LOOKUP, survey_match.confidence, ...))

    if station_match is not None:
        candidates.append(MethodCandidate(STATION_LOOKUP, station_match.confidence, ...))

    if registration_transform is not None:
        alignment = _resolve_via_alignment(...)
        candidates.append(MethodCandidate(ALIGNMENT, alignment.confidence_score, ...))

    if doc_has_reference_terms:
        reference = _resolve_via_reference_lookup(...)
        if reference.confidence_score > 0:
            candidates.append(MethodCandidate(REFERENCE_LOOKUP, reference.confidence_score, ...))

    if contour_match is not None and contour_match.pair_count >= 2:
        candidates.append(MethodCandidate(CONTOUR_MATCH, contour_match.confidence, ...))

    return candidates

def detect_resolution_case(candidates: list[MethodCandidate]) -> ResolutionMethod:
    """Returns winning method only — use select_best_location_match() for full result."""
    winner = select_best_location_match(candidates)
    return winner.method if winner else UNRESOLVED
```

Final winner selection is defined in §13e (max confidence; priority ladder is **tie-break only**).

#### 12f. Evidence kind gate (contour eligibility)

Contour matching runs **only** when evidence is line-art. Add before any call to `landmark_matcher` in `resolve_evidence_location()` (§13a).

**New enum** (or module-level constants in `location_match_orchestrator.py`):

```python
EvidenceKind = Literal["drawing_scan", "photo", "form"]
```

**Classification** — `classify_evidence_kind(session, evidence_id) -> EvidenceKind`:

| `evidence_kind` | Meaning | Contour eligible? |
|-----------------|---------|-------------------|
| `drawing_scan` | Scanned/marked-up drawing sheet (vector or raster line-art) | **Yes** |
| `photo` | Field photograph (trench, manhole, etc.) | **No** |
| `form` | Inspection report / PDF form (text extraction, no drawable outlines on evidence file) | **No** |

**Reuse existing pipeline where possible:**

```python
# Primary: DocumentExtraction.document_type from upload/extraction pipeline
# backend/ai/schemas/document_extraction_schemas.py — DocumentType enum already exists:
#   inspection_report | field_photo | master_drawing | unknown

DOCUMENT_TYPE_TO_EVIDENCE_KIND: dict[str, EvidenceKind] = {
    "field_photo": "photo",
    "master_drawing": "drawing_scan",
    "inspection_report": "form",       # default; override with heuristic below
    "unknown": "form",                # conservative — no contour
}

# Heuristic override for inspection_report uploads that are actually drawing PDFs:
# If native PDF text density >= 50 positioned words on page 1 OR mime is application/pdf
# with linked install-sheet attachment (EvidenceDrawingLink), upgrade to "drawing_scan".
NATIVE_TEXT_DENSITY_THRESHOLD = 50    # words on page 1 from extract_document()
```

Store resolved kind on `DocumentExtraction.meta_json["evidence_kind"]` at extraction time (persist once, read in match job).

**Gate logic in orchestrator:**

```python
NON_CONTOUR_METHODS = (
    COORDINATE_LOOKUP, STATION_LOOKUP, REFERENCE_LOOKUP, ALIGNMENT,  # + clue tile as separate source
)

def resolve_evidence_location(...) -> LocationMatchResult:
    evidence_kind = classify_evidence_kind(session, evidence_id)

    # Steps 1–3: run all non-contour matchers (survey, clue, reference, alignment)
    candidates = collect_non_contour_candidates(...)

    winner = select_best_location_match(candidates)
    if winner is not None and winner.confidence > 0.0:
        return winner

    # Gate: no contour for photos/forms
    if evidence_kind != "drawing_scan":
        return LocationMatchResult(
            method=UNRESOLVED,
            confidence=0.0,
            bbox_fractional=None,
            notes=(
                f"No coordinate/station/reference match for evidence_kind={evidence_kind!r}. "
                "Contour matching skipped (not line-art). Surface evidence for manual placement."
            ),
        )

    # Step 4: drawing_scan only — landmark_matcher (contour fallback; full-page evidence extract)
    contour = run_landmark_matcher(
        master_landmarks=load_master_landmarks(...),
        evidence_rendition_png=...,
        evidence_page_meta=...,
        optional_hint_bbox=None,  # or evidence highlight if present — never required
    )
```

**Frontend behavior when gated:** `match_status = "no_match"`, no overlay bbox — evidence panel shows full uploaded file for manual pin placement. Do not emit a low-quality contour guess on photos.

#### 12g. Tests

| Test | Assert |
|------|--------|
| `test_landmark_extractor_finds_tank` | synthetic rectangle contour → type `tank` |
| `test_landmark_extractor_full_page_evidence` | extraction runs on full page, not gated on input bbox |
| `test_landmark_matcher_output_from_master_bboxes` | overlay bbox = union of matched **master** landmarks, not translated evidence highlight |
| `test_landmark_matcher_optional_hint_boost_only` | hint_bbox provided → rank boost; hint absent → still extracts full page |
| `test_landmark_matcher_hu_threshold` | identical shapes → distance 0.0 |
| `test_landmark_matcher_requires_two_pairs` | 1 pair only → no match |
| `test_contour_match_always_needs_review` | 3+ pairs at internal score `0.72` → `match_status == "needs_review"` |
| `test_contour_skipped_for_photo_evidence` | `evidence_kind == "photo"`, coords/reference all fail → `UNRESOLVED`, landmark_matcher not called |
| `test_contour_runs_for_drawing_scan` | `evidence_kind == "drawing_scan"`, no higher signal → contour candidate returned |
| `test_select_best_reference_beats_contour` | REFERENCE location-only `0.75` + CONTOUR `0.72` (3+ pairs) → reference wins |
| `test_select_best_alignment_beats_weak_coordinate` | ALIGNMENT `0.90` + coordinate tier `0.80` → alignment wins |
| `test_tiebreak_coordinate_over_contour` | both `0.96` within epsilon → COORDINATE_LOOKUP wins tie-break |

---

### Phase 13 — Unified match ranker & pipeline wiring

**Goal:** Single code path from evidence upload to overlay.

#### 13a. New orchestrator

**New file:** `backend/ai/pipelines/location_match_orchestrator.py`

```python
@dataclass
class LocationMatchResult:
    method: ResolutionMethod
    confidence: float
    bbox_fractional: tuple[float,float,float,float] | None
    master_drawing_id: int
    region_id: int | None
    page: int
    source: str           # "coordinate_match" | "clue_match" | "contour_match" | "reference_lookup"
    notes: str

def resolve_evidence_location(session, *, evidence_id, master_drawing_id, page=1) -> LocationMatchResult:
    """
    Step 0: build_match_scope()          # full merged evidence text for sheet refs
    Step 0b: evidence_kind = classify_evidence_kind(session, evidence_id)
    Step 1: Run ALL non-contour matchers (no early exit):
              - extract_survey_points_from_evidence() — **full document** (§9f)
              - survey_point_matcher (master + auxiliary + evidence meta)
              - find_candidate_tiles_from_clues → best clue tile score
              - resolve_document_location (REFERENCE_LOOKUP)
              - alignment path if registration_transform present
    Step 2: Score each result per §13d; select_best_location_match()
    Step 3: If winner.confidence > 0 → return winner
    Step 4: If evidence_kind != "drawing_scan" → UNRESOLVED (skip Phase 12; manual placement)
    Step 5: drawing_scan only → landmark_matcher (contour fallback)
    Step 6: return winner or UNRESOLVED
    """
```

#### 13b. Replace body of `run_inspection_match_job()`

**File:** `backend/services/inspection_matching_jobs.py`

Replace direct `find_candidate_tiles_from_clues` loop with:

```python
result = resolve_evidence_location(session, evidence_id=..., master_drawing_id=...)
status = match_status_from_result(result)  # see §13d — CONTOUR_MATCH always needs_review
persist_inspection_match_overlay(..., status=status, bbox=result.bbox_fractional, ...)
record_internal_match_candidate(..., source=result.source, score=result.confidence)
```

```python
def match_status_from_result(result: LocationMatchResult) -> MatchStatus:
    if result.confidence <= 0:
        return "no_match"
    if result.method == ResolutionMethod.CONTOUR_MATCH:
        return "needs_review"  # never auto-promote — pipe lines corrupt contour inputs
    return "matched" if result.confidence >= MATCH_SCORE_THRESHOLD else "needs_review"
```

Keep `DrawingMatchCandidate` rows for **all** scored method candidates (sorted by confidence desc), not only the winner.

#### 13c. Wire `inspection_mapping.py`

`map_document_to_overlays()` should call the same `resolve_evidence_location()` instead of duplicating resolver logic.

#### 13d. Score table — **source of truth**

Every applicable method produces an `internal_score`. The orchestrator picks **`argmax(internal_score)`** over all candidates. The priority ladder (§13e) is used **only** when two candidates tie within `SCORE_TIE_EPSILON`.

| Method | `internal_score` | Frontend `match_status` |
|--------|-----------------|------------------------|
| Coordinate, `d <= 1.0 ft` | `0.98` | `matched` |
| Coordinate, `d <= 3.0 ft` | `0.96` | `matched` |
| Coordinate, `d <= 5.0 ft` | `0.80` | `needs_review` |
| Station + structure exact | `0.88` | `matched` |
| Reference type + location | `0.92` | `matched` |
| Reference location only | `0.75` | `matched` |
| Reference type only (single region) | `0.55` | `needs_review` |
| Alignment, overlapping region found | `0.90` | `matched` |
| Alignment, no overlapping region | `0.75` | `matched` |
| Clue tile (existing formula) | `tile.conf + clue.conf` | `matched` if ≥ `0.75` |
| Contour ≥ 2 pairs | `0.70` (2 pairs) / `0.72` (3+ pairs) | **`needs_review` always** |
| No signal | `0.0` | `no_match` |

Threshold constant: `MATCH_SCORE_THRESHOLD = 0.75` (unchanged).

**CONTOUR_MATCH rule:** Internal scores are capped at `0.72` (below threshold) for ranking/audit only. `match_status_from_result()` returns `needs_review` for any `CONTOUR_MATCH` winner — no exception for 3+ pairs. Revisit only after labeled accuracy data from `LocationMatchLabel` proves contour precision is production-ready.

**Examples (score wins, not list order):**

- REFERENCE_LOOKUP location-only `0.75` beats CONTOUR_MATCH `0.72` (3+ pairs) → reference wins bbox **and** status.
- ALIGNMENT with region `0.90` beats coordinate tier `0.80` → alignment wins.
- COORDINATE_LOOKUP `0.96` beats everything else → coordinate wins.
- CONTOUR_MATCH wins argmax but no method ≥ `0.75` → overlay bbox from contour, status **`needs_review`** (not `matched`).

#### 13e. Tie-breaker (when scores are equal within epsilon)

```python
SCORE_TIE_EPSILON = 0.01

# Lower index = wins tie. Used ONLY when |score_a - score_b| <= SCORE_TIE_EPSILON.
METHOD_TIEBREAK_PRIORITY: tuple[ResolutionMethod, ...] = (
    COORDINATE_LOOKUP,    # 0 — strongest physical anchor
    STATION_LOOKUP,      # 1
    REFERENCE_LOOKUP,    # 2
    ALIGNMENT,           # 3
    CONTOUR_MATCH,       # 4
    # clue_match is not a ResolutionMethod enum value; treat as rank 5 when comparing
)

def select_best_location_match(candidates: list[MethodCandidate]) -> MethodCandidate | None:
    viable = [c for c in candidates if c.confidence > 0.0]
    if not viable:
        return None
    max_score = max(c.confidence for c in viable)
    tied = [c for c in viable if abs(c.confidence - max_score) <= SCORE_TIE_EPSILON]
    if len(tied) == 1:
        return tied[0]
    return min(tied, key=lambda c: METHOD_TIEBREAK_PRIORITY.index(c.method))
```

`resolve_document_location()` and `run_inspection_match_job()` must both call `select_best_location_match()` — never a fixed if-chain.

---

### Phase 14 — Labeled eval set, regression & operator tooling

> **Threshold freeze policy:** Constants below are **provisional** — tuned against a single golden case (run 435 / evidence 357 / master 661). **Do not finalize** until the labeled eval set (§14b–§14d) has ≥ `5` rows and the eval script passes. Adjust only after reviewing per-case failures.

| Constant | Provisional value | File |
|----------|-------------------|------|
| `COORD_MATCH_TOLERANCE_FT` | `3.0` | `survey_point_matcher.py` |
| `NE_PAIR_MAX_DISTANCE_FT` | `15.0` | `survey_point_extractor.py` |
| `NE_PAIR_MAX_DISTANCE_NORM` | `0.12` (fallback only) | `survey_point_extractor.py` |
| `KEYPLAN_NCC_THRESHOLD` | `0.70` | `sheet_orientation_detector.py` |
| `HU_MATCH_THRESHOLD` | `0.15` | `landmark_matcher.py` |
| `MATCH_SCORE_THRESHOLD` | `0.75` | `inspection_match_persistence.py` |

#### 14a. Golden regression test (eval case #1)

**New file:** `backend/tests/test_ucsf_survey_location_e2e.py`

This is **one row** in the labeled eval set — not sufficient alone to lock thresholds.

Fixture requirements:

- Master PDF excerpt with known N/E near Future Hospital Building corridor on drawing 661
- Evidence text snippet from C4.20 with matching N/E within `3.0 ft`
- Sheet rotation ~`180°` between evidence install sheet and master site plan
- Assert: `resolve_evidence_location()` returns `method=COORDINATE_LOOKUP`, `confidence >= 0.96`, bbox IoU with human-labeled master bbox ≥ `0.30`

#### 14b. Human-labeled pairs table

**New file:** `backend/models/location_match_label.py`

```python
class LocationMatchLabel(Base):
    __tablename__ = "location_match_labels"

    id: int PK
    label_id: str                    # stable slug, e.g. "ucsf-435-ss-corridor"
    project_id: int
    evidence_id: int | None          # nullable if fixture-only (synthetic PDF path)
    inspection_run_id: int | None
    master_drawing_id: int
    evidence_fixture_path: str | None  # backend/tests/fixtures/... when not in DB

    # Ground truth
    master_bbox_json: dict           # {x0,y0,x1,y1} normalized — required
    evidence_bbox_json: dict | None  # optional; evidence-side region if known
    expected_method: str             # COORDINATE_LOOKUP | STATION_LOOKUP | REFERENCE_LOOKUP | UNRESOLVED | ...
    expected_match_status: str       # matched | needs_review | no_match
    rotation_deg: float | None       # known true-north offset between evidence and master (e.g. 180.0)

    # Signal profile (for stratified eval)
    has_coordinate_signal: bool      # True if N/E present on evidence or linked sheet
    has_station_signal: bool
    has_reference_signal: bool       # inspection type + location term
    evidence_kind: str               # drawing_scan | photo | form

    notes: str
    created_by: int | None
    created_at: datetime
```

**Seed target: 5–10 labeled pairs minimum** before locking thresholds. Store seed rows in:

`backend/tests/fixtures/location_match_labels.json`

Load via `backend/scripts/seed_location_match_labels.py` (dev/CI) or insert through admin UI (PR-G).

#### 14c. Required eval set composition

| # | Label slug (example) | Must include | `has_coordinate_signal` | `rotation_deg` | Expected outcome |
|---|----------------------|--------------|-------------------------|----------------|------------------|
| 1 | `ucsf-435-ss-corridor` | Golden case — run 435, evidence 357, master 661, linked C4.20 | `true` | `180` | `COORDINATE_LOOKUP`, `matched` |
| 2 | `ucsf-rotated-detail` | Second **180°** pair (different sheet pair than #1) | `true` or `false` | `180` | method per human label |
| 3 | `ucsf-no-coords-clue-only` | **Zero coordinate signal** — clue/reference only | `false` | `0` or `null` | `REFERENCE_LOOKUP` or `needs_review` |
| 4 | `ucsf-no-coords-unresolved` | **Zero coordinate signal** — ambiguous/no match | `false` | any | `UNRESOLVED`, `no_match` |
| 5 | `ucsf-station-only` | Station + structure, no N/E on one side | `false` | any | `STATION_LOOKUP` if matchable |
| 6–10 | (expand) | Mix: photo (`form`/`photo` → no contour), drawing_scan contour candidate, multi-sheet ref | vary | vary | per human label |

**Hard requirements before threshold freeze:**

- [ ] ≥ `5` rows with `master_bbox_json` confirmed by a human
- [ ] ≥ `1` row with `rotation_deg == 180` (excluding duplicates of same sheet pair as #1)
- [ ] ≥ `1` row with `has_coordinate_signal == false` and expected `UNRESOLVED` or non-coordinate method
- [ ] Eval script (§14d) run on all rows; review failures before changing constants

#### 14d. Eval script

**New file:** `backend/scripts/eval_location_match.py`

```bash
# Run against DB labels + fixtures (CI-friendly)
python backend/scripts/eval_location_match.py \
  --labels backend/tests/fixtures/location_match_labels.json \
  --min-iou 0.30 \
  --output /tmp/location_match_eval.json
```

```python
@dataclass
class EvalCaseResult:
    label_id: str
    expected_method: str
    actual_method: str
    expected_status: str
    actual_status: str
    bbox_iou: float | None
    passed: bool
    failure_reasons: list[str]

def run_eval(labels: list[LocationMatchLabel], session) -> list[EvalCaseResult]:
    """
    For each label:
      1. resolve_evidence_location(...) or load fixture
      2. Compare method, match_status, bbox IoU vs master_bbox_json
      3. Record pass/fail + deltas for threshold tuning
    """

def print_eval_summary(results: list[EvalCaseResult]) -> None:
    """
    Report:
      - pass rate overall and by stratum (has_coordinate_signal, rotation_deg != 0)
      - false positives on zero-coordinate cases
      - IoU distribution (p50, min)
    Fail CI if pass_rate < 0.80 OR any zero-coordinate case produces matched coordinate/contour false positive
    """
```

**New test:** `backend/tests/test_location_match_eval.py` — loads fixture JSON, runs eval script, asserts ≥ `80%` pass rate once ≥ `5` labels exist (skip with `@pytest.mark.skip` until labels seeded).

**Workflow:** After adding/changing thresholds in §9b/§11/§12, re-run eval script and attach `/tmp/location_match_eval.json` summary to PR description.

#### 14e. Debug endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /drawings/{id}/survey-points` | All indexed survey points |
| `GET /drawings/{id}/landmarks` | Landmark bboxes + types |
| `GET /drawings/{id}/orientation` | `page_meta_json` orientation fields |
| `POST /drawings/{id}/orientation` | Manual override `{page, true_north_rotation_deg}` |

#### 14f. Reindex behavior

On reindex: replace `source="auto_index"` rows in `drawing_survey_points` and `drawing_landmarks`; preserve `source="manual"`.

---

## 3. Pre-build validation checklist (required before Phase 11 CV)

Run these queries/tests on project 2 before implementing keyplan detection:

### 3a. N/E OCR verification

```bash
curl "/api/projects/2/drawings/661/text-elements?limit=500" \
  | jq '.items[] | select(.text | test("2131764|6051541|SSMH|10\\+05"; "i"))'
```

**Pass criteria:**

- ≥ `1` N token matching `_NORTHING_RE` with confidence ≥ `0.40`
- ≥ `1` E token matching `_EASTING_RE` within **15 ft real-world** pairing distance of N token (per page `scale_json`)
- Same pass on linked C4.20 drawing OR evidence `text_content`

### 3b. Keyplan audit (manual)

Inspect pages 1 of sheets: `C0.00`, `C4.20`, master `661`, `C4.21`, `C6.00`.

Record per sheet:

| Sheet | Keyplan present (Y/N) | Bbox corner (x0,y0) | Orientation callout text (Y/N + snippet) | PyMuPDF rotation |
|-------|----------------------|---------------------|------------------------------|------------------|

**Proceed with CV if:** keyplan present on ≥ `80%` of audited sheets in `{x >= 0.65, y >= 0.65}` **and** discrete 4-way template match (not contour angle) scores ≥ `0.70` on ≥ 4/5 audited sheets at the correct cardinal rotation.

**Fallback if not:** use text-only orientation (Phase 11b step 1) + manual override API.

---

## 4. PR implementation order

| PR | Phases | Files (primary) | Unblocks |
|----|--------|-----------------|----------|
| **PR-A** | 9a–9e | `drawing_survey_point.py`, `survey_point_extractor.py`, `survey_point_matcher.py`, migration | Coordinate matching |
| **PR-B** | 10 | `match_candidate_scope.py`, `inspection_matching_jobs.py` | C4.20 search scope |
| **PR-C** | 11 | `sheet_orientation_detector.py` (discrete 4-way keyplan NCC), `coordinate_frame.py`, fix `RegistrationTransform.apply()` | Rotation-normalized geometry |
| **PR-D** | 12 | `drawing_landmark.py`, `landmark_extractor.py`, `landmark_matcher.py` | Contour fallback |
| **PR-E** | 13 | `location_match_orchestrator.py`, unify `inspection_mapping.py` | Single pipeline |
| **PR-F** | 14a + 14d test | e2e golden test, eval script, match-status polling | Run 435 regression |
| **PR-G** | 14b–14c | `location_match_label.py`, fixture JSON (5–10 rows), seed script, admin UI | **Threshold validation** — block threshold changes until eval passes |

**Do not start PR-C (keyplan CV) until checklist 3b passes.**

---

## 5. What not to do

- Do not use sheet identifiers as master region lookup keys (unchanged design rule).
- Do not run contour matching before true-north normalization (Phase 11 before Phase 12).
- Do not run contour matching when `evidence_kind` is `photo` or `form` — return `UNRESOLVED` for manual placement.
- Do not require a pre-cropped evidence highlight bbox for contour matching — extract landmarks from the full evidence page; output bbox comes from matched master landmarks.
- Do not scope survey-point, station, structure-label, or sheet-ref regex passes to a highlight crop, click vicinity, or `text_content[:N]` truncation — **full document is the default**; optional hints boost only.
- Do not expose `confidence_score`, Hu distances, or OCR confidence to frontend.
- Do not delete human-drawn regions or manual survey points on reindex.
- Do not OCR on upload request thread (keep async jobs).

---

## 6. File map (new + modified)

| Action | Path |
|--------|------|
| NEW | `backend/models/drawing_survey_point.py` |
| NEW | `backend/models/drawing_landmark.py` |
| NEW | `backend/models/location_match_label.py` |
| NEW | `backend/tests/fixtures/location_match_labels.json` |
| NEW | `backend/scripts/eval_location_match.py` |
| NEW | `backend/scripts/seed_location_match_labels.py` |
| NEW | `backend/tests/test_location_match_eval.py` |
| NEW | `backend/ai/pipelines/survey_point_extractor.py` |
| NEW | `backend/ai/pipelines/survey_point_matcher.py` |
| NEW | `backend/ai/pipelines/sheet_orientation_detector.py` |
| NEW | `backend/ai/pipelines/coordinate_frame.py` |
| NEW | `backend/ai/pipelines/landmark_extractor.py` |
| NEW | `backend/ai/pipelines/landmark_matcher.py` |
| NEW | `backend/ai/pipelines/evidence_kind_classifier.py` |
| NEW | `backend/ai/pipelines/location_match_orchestrator.py` |
| NEW | `backend/services/match_candidate_scope.py` |
| MOD | `backend/ai/pipelines/master_drawing_indexer.py` |
| MOD | `backend/ai/pipelines/drawing_location_resolver.py` |
| MOD | `backend/services/evidence_document_extraction.py` (full-document survey points at upload) |
| MOD | `backend/services/inspection_matching_jobs.py` (verify no text subset before match) |
| MOD | `backend/ai/pipelines/inspection_mapping.py` (audit: bbox ≠ text scope) |
| MOD | `backend/services/evidence_linking.py` (`build_full_evidence_text` helper) |
| MOD | `backend/services/drawing_index_api.py` |
| MOD | `client/src/hooks/useInspectionMatchStatus.ts` (poll) |
| MOD | `client/src/components/drawing-workspace/inspection_runs_panel.tsx` (evidence id) |

---

## 7. Success criteria (definition of done)

1. Upload evidence 357 against master 661 → match job returns `matched` with bbox overlapping sanitary sewer corridor near Future Hospital Building (human IoU ≥ `0.30`).
2. Coordinate match alone succeeds when N/E present within `3.0 ft` even if sheet is rotated `180°`.
3. Clue-only fallback still works for evidence without coordinates (existing tests pass).
4. `index_status=processing` shows `index_pending` in UI; auto-retries match when ready.
5. Full backend suite passes; `test_ucsf_survey_location_e2e.py` passes (golden case #1).
6. **Labeled eval set:** ≥ `5` rows in `location_match_labels.json` meeting §14c composition; `eval_location_match.py` pass rate ≥ `80%`; zero-coordinate cases do not false-positive to `matched`.
7. Threshold constants (§14 threshold table) updated only with eval summary attached to PR — not on single-fixture tuning alone.

---

## 8. Relationship to `drawing_location_resolver.py`

Current resolver (Case A/B only):

| Case | Method | Signal |
|------|--------|--------|
| A | `ALIGNMENT` | `RegistrationTransform` (rotation currently ignored) |
| B | `REFERENCE_LOOKUP` | `inspection_type` + `location_term` vs `MasterRegion` |
| — | `UNRESOLVED` | No signal |

Extended resolver after Phases 9–13:

**Selection rule:** run all methods → score per §13d → `argmax(confidence)` → tie-break per §13e. The table below is **tie-break priority only**, not execution order.

| Tie-break rank | Method | Signal | Rotation-invariant? |
|----------------|--------|--------|---------------------|
| — (upstream) | — | Sheet refs → `MatchScope` | Yes |
| 0 | `COORDINATE_LOOKUP` | N/E within 3.0 ft | **Yes** |
| 1 | `STATION_LOOKUP` | Station + structure label | Yes |
| 2 | `REFERENCE_LOOKUP` | Type + location term | Yes |
| 3 | `ALIGNMENT` | Registration after true-north normalize | No (fixed by Phase 11) |
| 4 | `CONTOUR_MATCH` | Hu moments, ≥ 2 landmark pairs | Yes (after Phase 11 normalize) |
| — | `UNRESOLVED` | all scores == 0.0 | — |

Sheet identifiers remain excluded from `_actionable_terms()` — they prune search scope only, never directly resolve a master bbox.
