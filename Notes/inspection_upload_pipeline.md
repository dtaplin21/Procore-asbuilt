# Location Match — Manual Entry Checklist

**Golden case:** project `2`, master `661`, run `435`, evidence `357`, sheet `C4.20`

**How to use:** Work top to bottom. Copy one **PROMPT** block into Cursor Agent. Check `[x]` when done. Do not skip PR order (A → G).

**Already built (skip unless tests fail):** drawing_index, text_elements, scale, regions, clue matcher, evidence extraction, sheet linking.

---

## PRE — Verify existing (optional)

- [ ] **PRE-1** Run baseline tests

**PROMPT — copy below:**

```
Run and fix if failing:
cd backend && pytest tests/test_drawing_scale_parser.py tests/test_master_drawing_indexer.py tests/test_candidate_tile_selector.py tests/test_drawing_index_status.py -q
```

---

# PR-A — Survey points

- [ ] **A-1** Model `drawing_survey_point.py` + register on Drawing

**PROMPT — copy below:**

```
PR-A step A-1: Create survey point model and register it.

1. Create backend/models/drawing_survey_point.py:

"""Survey coordinate points indexed on drawings for coordinate matching."""
from __future__ import annotations
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class DrawingSurveyPoint(Base):
    __tablename__ = "drawing_survey_points"
    id = Column(Integer, primary_key=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer, nullable=False, default=1)
    northing = Column(Float, nullable=False)
    easting = Column(Float, nullable=False)
    station = Column(String, nullable=True)
    structure_label = Column(String, nullable=True)
    label_bbox_json = Column(JSON, nullable=False)
    northing_bbox_json = Column(JSON, nullable=True)
    easting_bbox_json = Column(JSON, nullable=True)
    ocr_confidence = Column(Float, nullable=False, server_default="1.0")
    source = Column(String, nullable=False)  # auto_index | evidence_extract | manual
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    drawing = relationship("Drawing", back_populates="survey_points")

2. Export DrawingSurveyPoint from backend/models/__init__.py

3. Add to Drawing in backend/models/models.py:
survey_points = relationship("DrawingSurveyPoint", back_populates="drawing", cascade="all, delete-orphan")
```

---

- [ ] **A-2** Alembic migration `drawing_survey_points`

**PROMPT — copy below:**

```
PR-A step A-2: Add Alembic migration for drawing_survey_points.

Follow pattern in backend/alembic/versions/m1d2x3t4e5l6_add_drawing_text_elements.py (idempotent upgrade, downgrade).

Table columns: id, drawing_id FK drawings.id CASCADE, page default 1, northing, easting, station, structure_label, label_bbox_json, northing_bbox_json, easting_bbox_json, ocr_confidence default 1.0, source, meta_json, created_at.

Index: ix_drawing_survey_points_drawing_page on (drawing_id, page)

Run: cd backend && alembic upgrade head
```

---

- [ ] **A-3** Create `survey_point_extractor.py`

**PROMPT — copy below:**

```
PR-A step A-3: Create backend/ai/pipelines/survey_point_extractor.py

Extract paired N/E from OCR tokens. Use physical-feet pairing gates (not normalized as primary):
- NE_PAIR_MAX_DISTANCE_FT = 15.0
- NE_PAIR_HORIZONTAL_MAX_FT = 12.0
- NE_PAIR_VERTICAL_MAX_FT = 8.0
- SCALE_FALLBACK_REAL_FEET_PER_PAPER_INCH = 10.0
- MIN_OCR_CONFIDENCE = 0.40

Regex:
- Northing: r"\bN\s*(?:=|:)?\s*(\d{6,8}(?:\.\d{1,2})?)\b"
- Easting: r"\bE\s*(?:=|:)?\s*(\d{6,8}(?:\.\d{1,2})?)\b"
- Station: r"\b(?:STA\.?\s*)?(\d{1,2}\+\d{2}(?:\.\d{1,2})?)\b"
- Structure: r"\b(SSMH|SSMH-\d+|MH-?\d+|CO-?\d+|SMH|DMH|CB|DI)\b"

Export:
- SurveyPointRecord dataclass
- PairingScaleContext dataclass
- resolve_pairing_scale(scale_json, page_meta, scale_source)
- pairing_passes_gates(ax, ay, bx, by, ctx=...)
- extract_survey_points_from_elements(elements, scale_json, page_meta_json, scale_source="master_index")

resolve_pairing_scale order: scale_json confidence >= 0.5 → physical; else page dims → campus default 10 ft/in; else normalized_fallback.
```

---

- [ ] **A-4** Create `survey_point_matcher.py`

**PROMPT — copy below:**

```
PR-A step A-4: Create backend/ai/pipelines/survey_point_matcher.py

Constants:
- COORD_MATCH_HIGH_CONF_FT = 1.0 → confidence 0.98
- COORD_MATCH_TOLERANCE_FT = 3.0 → confidence 0.96
- COORD_MATCH_REJECT_FT = 5.0 → confidence 0.80
- beyond 5 ft → no match

Export:
- SurveyPointMatch dataclass
- euclidean_survey_distance_ft(a, b)
- confidence_for_distance(distance_ft)
- match_survey_points(evidence_points, master_points) — greedy v1, best single pair
```

---

- [ ] **A-5** Create `survey_point_storage.py`

**PROMPT — copy below:**

```
PR-A step A-5: Create backend/services/survey_point_storage.py

Export persist_survey_points(session, drawing_id, points: list[SurveyPointRecord], source: str) -> int

Delete existing rows for (drawing_id, source) then bulk insert DrawingSurveyPoint rows.
```

---

- [ ] **A-6** Wire master index + clear on reindex

**PROMPT — copy below:**

```
PR-A step A-6: Wire survey points into master drawing index.

1. backend/ai/pipelines/master_drawing_indexer.py — after text elements persisted:
   - extract_survey_points_from_elements(text_elements, scale_json, page_meta_json)
   - persist_survey_points(session, drawing_id, points, source="auto_index")
   - add survey_points count to index_stats_json

2. backend/services/drawing_index_jobs.py — clear_drawing_index_artifacts():
   - delete DrawingSurveyPoint where drawing_id and source="auto_index"
   - preserve source="manual"
```

---

- [ ] **A-7** Wire evidence upload

**PROMPT — copy below:**

```
PR-A step A-7: Extract survey points on evidence upload.

1. Create backend/services/evidence_text.py with build_full_evidence_text(evidence) -> str

2. backend/services/evidence_document_extraction.py — after document extraction:
   - resolve_scale_for_evidence(evidence, linked_drawings): evidence meta scale → linked drawing scale → None
   - extract_survey_points_from_evidence on FULL document (all pages, no text truncation)
   - store in DocumentExtraction.meta_json["survey_points"]
```

---

- [ ] **A-8** Tests

**PROMPT — copy below:**

```
PR-A step A-8: Add tests.

Create backend/tests/test_survey_point_extractor.py:
- pairs N 2131764.84 + E 6051541.82 within 15 ft at 1"=10'
- rejects E token > 15 ft away
- campus default when no scale but page dims exist
- normalized_fallback when plain text only

Create backend/tests/test_survey_point_matcher.py:
- 2.5 ft delta → 0.96
- 6 ft delta → no match

Run: cd backend && pytest tests/test_survey_point_extractor.py tests/test_survey_point_matcher.py -q
```

---

- [ ] **A-9** Verify on drawing 661

**PROMPT — copy below:**

```
PR-A step A-9: Reindex master drawing 661 and verify survey points.

Reindex drawing 661 via API or job worker.
Query: SELECT northing, easting, station, structure_label FROM drawing_survey_points WHERE drawing_id = 661 LIMIT 10;
Expect at least one row with N/E near 2131764 / 6051541 if OCR captured them on master or linked C4.20.
```

---

# PR-B — Sheet scope

- [ ] **B-1** Create `match_candidate_scope.py`

**PROMPT — copy below:**

```
PR-B step B-1: Create backend/services/match_candidate_scope.py

@dataclass MatchScope:
  master_drawing_id: int
  auxiliary_drawing_ids: tuple[int, ...]
  preferred_pages: tuple[int, ...]
  sheet_refs: tuple[str, ...]

build_match_scope(session, evidence_id, master_drawing_id):
1. extract_sheet_refs(build_full_evidence_text(evidence)) — FULL text, no truncation
2. find_project_drawings_for_refs → auxiliary_drawing_ids (e.g. C4.20)
3. If no refs: auxiliary_drawing_ids = ()

Sheet refs narrow search only — they do NOT produce a master bbox directly.
```

---

- [ ] **B-2** Tests

**PROMPT — copy below:**

```
PR-B step B-2: Create backend/tests/test_match_candidate_scope.py

Tests:
- evidence with C4.20 in linked supplemental text → auxiliary drawing id resolved
- sheet ref after char 2000 in merged text → still found

Run: cd backend && pytest tests/test_match_candidate_scope.py -q
```

---

# PR-C — Rotation (after keyplan audit)

- [ ] **C-0** Pre-build audit (manual — do before C-2 CV)

**PROMPT — copy below:**

```
PR-C step C-0: Manual audit before keyplan CV.

curl -s "http://localhost:8000/api/projects/2/drawings/661/text-elements?limit=500" | jq '.items[] | select(.text | test("2131764|6051541|SSMH|10\\+05"; "i"))'

Inspect keyplans on C0.00, C4.20, 661, C4.21, C6.00 — record corner bbox and orientation text.
Proceed with CV only if keyplan in title block on >= 80% of sheets.
```

---

- [ ] **C-1** Create `coordinate_frame.py`

**PROMPT — copy below:**

```
PR-C step C-1: Create backend/ai/pipelines/coordinate_frame.py

Export:
- rotate_point(x, y, degrees, cx=0.5, cy=0.5)
- rotate_bbox(bbox tuple, degrees) -> axis-aligned union bbox
- normalize_to_true_north(bbox, true_north_rotation_deg) wrapper
```

---

- [ ] **C-2** Create `sheet_orientation_detector.py`

**PROMPT — copy below:**

```
PR-C step C-2: Create backend/ai/pipelines/sheet_orientation_detector.py

Detection order (first win):
1. orientation_text — loose regex NORTH near POINT/ORIENTED/ARROW/VIEW + direction word → 0|90|180|270
2. keyplan_cv — discrete 4-way template NCC (0,90,180,270) in title block x>=0.65 y>=0.65, threshold 0.70
3. pdf_rotation from page_meta
4. assumed_up rotation 0

Extend page_meta_json per page with: true_north_rotation_deg, true_north_source, keyplan_bbox, keyplan_match_score, orientation_text

Do NOT use minAreaRect for rotation.
```

---

- [ ] **C-3** Wire orientation into index + fix RegistrationTransform

**PROMPT — copy below:**

```
PR-C step C-3:

1. master_drawing_indexer.py — run sheet orientation detector per page, persist extended page_meta_json

2. drawing_location_resolver.py — fix RegistrationTransform.apply() to apply rotation_degrees via rotate_bbox BEFORE scale/translate
```

---

- [ ] **C-4** Tests + keyplan fixture

**PROMPT — copy below:**

```
PR-C step C-4: Add backend/tests/fixtures/keyplan_template.png (crop from C0.00 title block).

Tests:
- orientation text "NORTH POINTING DOWN" → 180 deg
- rotate_bbox 180 deg swaps y
- RegistrationTransform.apply respects rotation

Run pytest for new rotation tests.
```

---

# PR-D — Contour fallback

- [ ] **D-1** Model `drawing_landmark.py` + migration

**PROMPT — copy below:**

```
PR-D step D-1: Create drawing_landmarks table.

Model backend/models/drawing_landmark.py:
- drawing_id FK, page, landmark_type (tank|manhole|building|other)
- bbox_json normalized, hu_moments_json, ocr_confidence, source (auto_index|manual), meta_json

Migration + register on Drawing. Clear source=auto_index on reindex; preserve manual.
```

---

- [ ] **D-2** Create `landmark_extractor.py` + `landmark_matcher.py`

**PROMPT — copy below:**

```
PR-D step D-2:

landmark_extractor.py — extract from FULL page PNG, exclude title block (x>=0.75,y>=0.75) and legend zones.

landmark_matcher.py:
- Hu distance threshold 0.15
- require >= 2 landmark pairs with vector_error <= 0.03 normalized
- output bbox = union of matched MASTER landmark bboxes (+0.01 padding)
- internal confidence 0.70 (2 pairs) or 0.72 (3+ pairs)
- NEVER return match_status matched for contour — always needs_review
```

---

- [ ] **D-3** Create `evidence_kind_classifier.py`

**PROMPT — copy below:**

```
PR-D step D-3: Create backend/ai/pipelines/evidence_kind_classifier.py

EvidenceKind = drawing_scan | photo | form

Map DocumentExtraction.document_type:
- field_photo → photo
- master_drawing → drawing_scan
- inspection_report → form (default)
- unknown → form

Override to drawing_scan if linked install sheet OR native text density >= 50 words on page 1.

Persist meta_json["evidence_kind"] at extraction time.

Contour matching ONLY when evidence_kind == drawing_scan.
```

---

- [ ] **D-4** Wire landmarks into index job

**PROMPT — copy below:**

```
PR-D step D-4: Wire landmark extraction into master_drawing_indexer.py and clear in drawing_index_jobs.py (source=auto_index only).
Add landmarks count to index_stats_json.
```

---

# PR-E — Unified orchestrator

- [ ] **E-1** Create `location_match_orchestrator.py`

**PROMPT — copy below:**

```
PR-E step E-1: Create backend/ai/pipelines/location_match_orchestrator.py

SCORE_TIE_EPSILON = 0.01
METHOD_TIEBREAK_PRIORITY: COORDINATE_LOOKUP, STATION_LOOKUP, REFERENCE_LOOKUP, ALIGNMENT, CONTOUR_MATCH

Export:
- LocationMatchResult, MethodCandidate dataclasses
- select_best_location_match(candidates) — max confidence; tie-break by priority list only within epsilon
- match_status_from_result — CONTOUR_MATCH always needs_review
- resolve_evidence_location(session, evidence_id, master_drawing_id, page=1):

Step 0: build_match_scope()
Step 0b: classify_evidence_kind()
Step 1: Run ALL non-contour matchers (no early exit):
  - survey points (master + auxiliary + evidence meta)
  - clue tiles on master + auxiliary
  - REFERENCE_LOOKUP
  - ALIGNMENT if registration_transform
Step 2: select_best_location_match()
Step 3: if winner → return
Step 4: if evidence_kind != drawing_scan → UNRESOLVED (skip contour)
Step 5: contour fallback for drawing_scan only
Step 6: UNRESOLVED

Extend drawing_location_resolver.ResolutionMethod with COORDINATE_LOOKUP, STATION_LOOKUP, CONTOUR_MATCH.
```

---

- [ ] **E-2** Replace `run_inspection_match_job()` body

**PROMPT — copy below:**

```
PR-E step E-2: Unify inspection match job.

backend/services/inspection_matching_jobs.py — replace clue-only loop with:
  result = resolve_evidence_location(session, evidence_id=..., master_drawing_id=...)
  status = match_status_from_result(result)
  persist overlay with result.bbox_fractional, result.page, result.region_id
  record DrawingMatchCandidate for audit

backend/ai/pipelines/inspection_mapping.py — map_document_to_overlays() should call same orchestrator.
```

---

- [ ] **E-3** Verify golden case

**PROMPT — copy below:**

```
PR-E step E-3: Test evidence 357 against master 661.

Upload or re-run inspection_match for run 435 / evidence 357.
Expect coordinate_lookup matched (or needs_review if 3-5 ft) instead of no_match.
Auxiliary drawing C4.20 survey points must be in search scope.
```

---

# PR-F — E2E + UI

- [ ] **F-1** E2E test

**PROMPT — copy below:**

```
PR-F step F-1: Create backend/tests/test_ucsf_survey_location_e2e.py

Golden case: project 2, evidence 357, master 661, linked C4.20.
Assert match method coordinate_lookup and match_status in (matched, needs_review).
```

---

- [ ] **F-2** Fix match-status polling (client)

**PROMPT — copy below:**

```
PR-F step F-2: Fix client match status polling.

In useInspectionMatchStatus.ts (or equivalent):
- Poll GET /inspections/{evidence_id}/match-status every 2000ms, max 30 attempts
- Pass evidence id (357), NOT run id (435)
- Refetch overlays when job completes
```

---

- [ ] **F-3** Debug API survey-points

**PROMPT — copy below:**

```
PR-F step F-3: Add GET /projects/{pid}/drawings/{id}/survey-points debug endpoint.
Return northing, easting, station, structure_label, label_bbox_json, page, source.
Wire optional UI or curl-only for dev.
```

---

# PR-G — Eval set

- [ ] **G-1** Model `location_match_label.py` + migration

**PROMPT — copy below:**

```
PR-G step G-1: Create location_match_labels table.

Fields: label_id, project_id, evidence_id, inspection_run_id, master_drawing_id, evidence_fixture_path,
master_bbox_json (required ground truth), expected_method, expected_match_status, rotation_deg,
has_coordinate_signal, has_station_signal, has_reference_signal, evidence_kind, notes.
```

---

- [ ] **G-2** Seed fixture JSON (5–10 rows)

**PROMPT — copy below:**

```
PR-G step G-2: Create backend/tests/fixtures/location_match_labels.json with minimum:

1. ucsf-435-ss-corridor — evidence 357, master 661, rotation_deg 180, expected coordinate_lookup matched
2. ucsf-rotated-detail — second 180 deg pair
3. ucsf-no-coords-clue-only — has_coordinate_signal false
4. ucsf-no-coords-unresolved — photo, expected no_match
5. ucsf-station-only — station lookup case

Fill master_bbox_json from human-labeled pins on drawing 661.

Create backend/scripts/seed_location_match_labels.py to load JSON into DB.
```

---

- [ ] **G-3** Eval script

**PROMPT — copy below:**

```
PR-G step G-3: Create backend/scripts/eval_location_match.py

For each label: run resolve_evidence_location, compare method, match_status, bbox IoU vs master_bbox_json (min 0.30).

Fail if pass_rate < 0.80 OR any zero-coordinate case gets matched via coordinate/contour false positive.

Create backend/tests/test_location_match_eval.py — skip until >= 5 labels seeded.

Run:
cd backend && python scripts/eval_location_match.py --labels tests/fixtures/location_match_labels.json --min-iou 0.30 --output /tmp/location_match_eval.json
```

---

- [ ] **G-4** Definition of done

**PROMPT — copy below:**

```
PR-G step G-4: Confirm all done criteria:

[ ] Evidence 357 → master 661 matched, IoU >= 0.30 vs human bbox
[ ] Coordinate match works at 180 deg rotation within 3 ft
[ ] Photo/form no coords → no_match, no contour false positive
[ ] Eval >= 5 labels, pass rate >= 80%
[ ] UI polls match status with evidence id
```

---

## Quick reference — do not

- Sheet refs (C4.20) narrow search — they do not place pins directly
- Contour only for `drawing_scan`; always `needs_review`
- Full document text for survey/sheet-ref scans — no truncation
- Do not lock thresholds until PR-G eval passes
