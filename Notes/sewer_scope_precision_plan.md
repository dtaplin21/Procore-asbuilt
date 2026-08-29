# Sewer Scope Precision Plan — Green-Highlight Polyline on Master

**Goal:** Inspection overlays on master drawing **661** must trace the full sanitary sewer run (like the green markup on C4.20: **STA 10+00 → 10+71 → 10+90.95**), placed on the **campus plan** — not a tiny corner segment or title-block pin.

**Why:** Run **642** / evidence **632** / overlay **445** currently shows a 2-point micro-polyline at the bottom-left of master 661 (~x=0.20, y=0.84). Coordinate lookup finds the right point on aux drawing **1084** (C4.20), but scope geometry is wrong in **shape** (single anchor) and **placement** (no master projection).

**Golden case (dev):** project `2`, master `661`, aux `1084` (`7.20-7.24 U1.C4.20 6.00 Sanitary Sewer Install.pdf`), evidence **632**, run **642**

**Reference (good pin, wrong scope):** Run **511** landed coordinate_lookup at **(0.518, 0.472)** on master — campus center, not bottom-left.

**How to use:** Work **top → bottom**. Copy one **PROMPT** block into Cursor Agent. Check `[ ]` when done. Each step has a **Plain English** line and a **TEST** command to run after the step.

**Prerequisite:** Post-H hotfixes I-1/I-2/I-3 from `Notes/location_match_investigation_plan.md` are done. Match-time investigation (PR-A–H) is live.

**Related docs:**
- `Notes/location_match_investigation_plan.md` — upload slim + dossier investigation
- `Notes/universal_location_match_eval.md` — eval label schema
- `backend/tests/fixtures/location_match_labels/README.md` — polyline annotation guide
- `Notes/sheet_digitization_plan.md` — raster digitization; **per-viewport scale** (plan vs section on one sheet); multi-scale handled by sheet digitization Phase V

---

## Problem in one picture

```
TODAY (Run #642)
────────────────
  Match finds coords on C4.20 (1084) ✓
  → single-point anchor (11+14.23)
  → vision trace on master PNG at wrong anchor
  → 2-point micro-polyline at bottom-left ✗


TARGET (green highlight)
────────────────────────
  Extract station run 10+00 → 10+90.95 from C4.20 OCR
  → chain aux survey points into multi-segment polyline
  → project polyline onto master 661 via registration transform
  → overlay follows full sewer trench on campus plan ✓
```

---

## Hard rules (every step)

| Rule | Plain English |
|------|----------------|
| **Ground truth is on master** | Eval labels and UI overlays are always geometry on master 661 — never sheet-number placement. |
| **No silent wrong pin** | Without registration, keep `needs_review` + `aux_coords_unprojected`; don't paste aux bboxes onto master. |
| **Plan-view stations only** | Ignore profile-sheet stations at y≈0.95 on C4.20 when extracting `10+00` / `10+90.95`. |
| **Polyline beats point** | Utility sewer runs use `utility_line` scope with ≥3 vertices, not a 2-point vision stub. |
| **Aux trace, master display** | Trace station/utility geometry on the **source aux sheet**, then project to master. |
| **Tests gate each step** | Do not start the next step until that step's pytest command passes. |

---

## File map (touch these)

| Action | Path |
|--------|------|
| MODIFY | `backend/tests/fixtures/location_match_labels/ucsf.json` — truth polyline label |
| ADD/MODIFY | `backend/ai/pipelines/station_range_extractor.py` (or extend `survey_point_extractor.py`) |
| MODIFY | `backend/services/evidence_investigation_persistence.py` — persist station clues + meta |
| MODIFY | `backend/ai/pipelines/scope_line_tracer.py` — aux tokens + scoped polyline |
| MODIFY | `backend/ai/pipelines/scope_geometry.py` — scope kind from station range |
| ADD/MODIFY | `backend/ai/pipelines/registration_from_survey.py` — compute transform from shared N/E |
| MODIFY | `backend/ai/pipelines/location_match_orchestrator.py` — project polyline vertices |
| MODIFY | `backend/ai/agents/inspection_location_agent.py` — pass source drawing + transform to tracer |
| ADD | `backend/tests/test_station_range_extractor.py` |
| ADD | `backend/tests/test_aux_scope_polyline.py` |
| ADD | `backend/tests/test_registration_from_survey.py` |
| MODIFY | `backend/tests/test_scope_line_tracer.py` |
| MODIFY | `backend/tests/test_location_match_orchestrator.py` |
| MODIFY | `backend/scripts/verify_v1_golden.py` — optional run 642 variant |

---

## S-0 — Annotate truth polyline on master 661

- [x] **S-0.1** Open master 661 + C4.20 (1084) side-by-side in Objects viewer
- [x] **S-0.2** Mark normalized polyline vertices along the sewer run **as it should appear on master** (≥4 points: start 10+00 area → bend → end 10+90 area)
- [x] **S-0.3** Add eval label `ucsf-642-ss-run` to `ucsf.json` with `master_scope_geometry_json`
- [x] **S-0.4** Set tight `master_bbox_json` rect envelope around the polyline

**Plain English:** Draw the answer key first — where the green highlight should land on master 661 — so every code change can be measured.

**Manual annotation steps:**

1. In UI: `localhost:5173/objects?projectId=2&drawingId=661`
2. Use C4.20 green reference (stations 10+00 → 10+90.95) and Run #511 pin (~0.518, 0.472) as guides.
3. Record normalized `[x, y]` pairs (0–1) for each vertex on **master page 1**.
4. Expected polyline shape: horizontal segment through campus, then diagonal toward manhole — **not** bottom-left corner.

**PROMPT — copy below:**

```
S-0: Add UCSF Run #642 sewer-run truth polyline to eval labels.

1. backend/tests/fixtures/location_match_labels/ucsf.json
   Add a new label (do not remove existing entries):

   {
     "label_id": "ucsf-642-ss-run",
     "suite": "ucsf",
     "project_id": 2,
     "evidence_id": 632,
     "inspection_run_id": 642,
     "master_drawing_id": 661,
     "evidence_fixture_path": null,
     "master_bbox_json": {
       "type": "rect",
       "page": 1,
       "x": <tight envelope min x>,
       "y": <tight envelope min y>,
       "width": <span>,
       "height": <span>
     },
     "master_scope_geometry_json": {
       "type": "polyline",
       "page": 1,
       "scope_kind": "utility_line",
       "points": [
         [<x0>, <y0>],
         [<x1>, <y1>],
         [<x2>, <y2>],
         [<x3>, <y3>]
       ]
     },
     "expected_method": "coordinate_lookup",
     "expected_match_status": "matched",
     "rotation_deg": null,
     "has_coordinate_signal": true,
     "has_station_signal": true,
     "has_reference_signal": true,
     "evidence_kind": "form",
     "notes": "Run 642 / evidence 632. Truth polyline = full sanitary sewer run 10+00→10+90.95 projected onto master 661 campus plan. Annotated from C4.20 green highlight + Run 511 campus anchor."
   }

   Replace <x>/<y> placeholders with manually measured normalized coordinates.

2. backend/tests/test_location_match_labels_seed.py
   - Ensure validate_entry accepts the new polyline label (no schema changes expected).

3. Notes/sewer_scope_precision_plan.md — check S-0 boxes when coordinates are filled in.

TEST:
cd backend && pytest tests/test_location_match_labels_seed.py -q --tb=short
```

**Verify label loads:**

```bash
cd backend && python scripts/eval_location_match.py --suite ucsf --labels tests/fixtures/location_match_labels/ucsf.json 2>&1 | head -30
```

---

## S-1 — Extract station range from linked C4.20 OCR

- [x] **S-1.1** Parse `10+00` and `10+90.95` (or `10+93`) from aux drawing text tokens at plan-view y positions
- [x] **S-1.2** Filter out profile-view tokens (y > 0.85 on aux page 1)
- [x] **S-1.3** Persist `station_from` / `station_to` as document clues and evidence meta during investigation
- [x] **S-1.4** `infer_scope_kind` returns `utility_line` when sewer language + station range present

**Plain English:** Read "SAN. STA. 10+00" through "10+90.95" off the linked install sheet and save them as the start/end of the trench run.

**PROMPT — copy below:**

```
S-1: Extract station range from linked auxiliary drawing OCR at match time.

CONTEXT:
- scope_geometry._station_range() reads evidence.meta.station_from/station_to and clue_type station_from/station_to
- C4.20 (1084) OCR has plan-view stations ~y 0.20–0.30 and profile stations ~y 0.95
- Evidence text includes "Trench and Install Sanitary Sewer Lines"

1. ADD backend/ai/pipelines/station_range_extractor.py (or extend survey_point_extractor.py):
   - extract_station_range_from_tokens(tokens, *, max_profile_y=0.85) -> tuple[str|None, str|None]
   - Use extract_stations_from_text() on DrawingTextElement rows for aux drawing
   - Pick min station as station_from, max as station_to (by chainage numeric value)
   - Ignore tokens with centroid y > max_profile_y (profile sheet strip)

2. MODIFY backend/services/evidence_investigation_persistence.py:
   - After aux drawing is indexed, load DrawingTextElement for linked drawing ids
   - Call station range extractor; persist:
     - evidence.meta["station_from"], evidence.meta["station_to"]
     - DocumentClue rows clue_type station_from / station_to with label bbox when available

3. MODIFY backend/ai/agents/evidence_dossier.py:
   - Include station_from/station_to in dossier evidence meta (already read by _station_range)

4. ADD backend/tests/test_station_range_extractor.py:
   - Fixture tokens mimicking C4.20: 10+00 @(0.10,0.20), 10+90.95 @(0.29,0.27), 10+00 @(0.10,0.95) profile
   - Assert station_from=10+00, station_to=10+90.95 (profile duplicate ignored)

5. MODIFY backend/tests/test_scope_geometry.py:
   - Dossier with station range + "sanitary sewer" text → infer_scope_kind == UTILITY_LINE

TEST:
cd backend && pytest tests/test_station_range_extractor.py tests/test_scope_geometry.py -q --tb=short
```

---

## S-2 — Chain aux scoped survey points into ordered polyline

- [x] **S-2.1** Order `DrawingSurveyPoint` rows on aux drawing by station chainage
- [x] **S-2.2** Build polyline from label bboxes (centroids), ≥3 points when range spans multiple stations
- [x] **S-2.3** Replace `_survey_endpoint_positions` 2-point limit with full aux polyline when scoped points have bboxes
- [x] **S-2.4** Return geometry in **aux fractional space** with meta `source_drawing_id`

**Plain English:** Connect the survey points on C4.20 in station order so the line follows the sewer — not just the first two points.

**PROMPT — copy below:**

```
S-2: Build multi-point polyline from auxiliary scoped survey points.

CONTEXT:
- dossier.master_context.scoped_survey_points includes SurveyPointRecord from aux drawings (via _load_scoped_survey_points)
- _survey_endpoint_positions() in scope_line_tracer.py only uses first 2 evidence meta points with placeholder bboxes
- Run #642 has 6 scoped points on drawing 1084

1. ADD backend/ai/pipelines/aux_scope_polyline.py:
   - build_aux_survey_polyline(scoped_points, *, station_from, station_to) -> list[tuple[float,float]] | None
   - Filter to source drawing_id == aux drawing with most points in station range
   - Sort by chainage (parse station label to float)
   - Map each point label_bbox_json centroid; require >= 3 points for utility_line

2. MODIFY backend/ai/pipelines/scope_line_tracer.py:
   - In UTILITY_LINE branch, before _trace_utility_line:
     call build_aux_survey_polyline when dossier has station range + scoped points
     Return ScopeGeometry(type=polyline, points=..., meta={source: aux_survey_chain, source_drawing_id: ...})

3. ADD backend/tests/test_aux_scope_polyline.py:
   - Mock 4 SurveyPointRecords on drawing 1084 with stations 10+00, 10+71, 10+90.95, 11+14.23
   - Assert ordered polyline has >= 3 vertices in ascending chainage order

4. MODIFY backend/tests/test_scope_line_tracer.py:
   - Dossier with station range + scoped aux points → polyline meta source=aux_survey_chain

TEST:
cd backend && pytest tests/test_aux_scope_polyline.py tests/test_scope_line_tracer.py -q --tb=short
```

---

## S-3 — Trace stations on aux tokens when match is aux-sourced

- [x] **S-3.1** `_load_master_text_tokens` gains `_load_drawing_text_tokens(drawing_id)` variant
- [x] **S-3.2** `_trace_station_range` uses aux tokens when winner `source_drawing_id != master`
- [x] **S-3.3** Station centroid search is not limited to `expanded_anchor` when tracing full run on aux
- [x] **S-3.4** Pass `source_drawing_id` from fused candidate into `trace_scope_geometry`

**Plain English:** When the match landed on C4.20, look for "10+00" and "10+90" labels on C4.20 — not on master (which has no station OCR).

**PROMPT — copy below:**

```
S-3: Scope tracer uses auxiliary drawing text when coordinate match is aux-sourced.

1. MODIFY backend/ai/pipelines/scope_line_tracer.py:
   - Add _load_drawing_text_tokens(session, drawing_id, page) -> list[_MasterTextToken]
   - trace_scope_geometry(..., source_drawing_id: int | None = None)
   - When source_drawing_id and source_drawing_id != dossier.master_drawing_id:
     tokens = _load_drawing_text_tokens(session, source_drawing_id, page)
   - _trace_station_range: when tracing aux, find station centroids globally on page
     (do not require intersection with expanded_anchor for endpoint stations)

2. MODIFY backend/ai/agents/inspection_location_agent.py:
   - Read source_drawing_id from winner.candidate (or winner metadata)
   - Pass to trace_scope_geometry(..., source_drawing_id=...)

3. MODIFY backend/ai/pipelines/location_match_orchestrator.py:
   - Ensure coordinate_lookup candidates carry source_drawing_id in candidate metadata

4. ADD tests in backend/tests/test_scope_line_tracer.py:
   - Master tokens empty, aux tokens have 10+00 + 10+90.95 → station_range polyline with 2+ points
   - source_drawing_id=1084, master_drawing_id=661

TEST:
cd backend && pytest tests/test_scope_line_tracer.py tests/test_inspection_location_agent.py -q --tb=short
```

---

## S-4 — Compute master ↔ aux registration from shared N/E control points

- [x] **S-4.1** Find N/E pairs indexed on **both** master 661 and aux 1084 (same northing/easting values)
- [x] **S-4.2** Compute `RegistrationTransform` (scale + translate; rotation if ≥3 points)
- [x] **S-4.3** Persist `evidence.meta.registration_transform` during investigation
- [x] **S-4.4** Fall back to `needs_review` when <2 shared control points

**Plain English:** Align the two maps using survey coordinates that appear on both master and C4.20 — like registering overlays in CAD.

**PROMPT — copy below:**

```
S-4: Compute registration transform from shared survey control points.

CONTEXT:
- RegistrationTransform in drawing_location_resolver.py (scale_x/y, translate_x/y, rotation_degrees)
- location_match_orchestrator._load_registration_transform reads evidence.meta.registration_transform
- _project_aux_bbox_to_master already applies transform when present
- Master 661 may have sparse coord OCR; aux 1084 has 6+ survey points

1. ADD backend/ai/pipelines/registration_from_survey.py:
   - compute_registration_from_control_points(pairs: list[tuple[aux_xy, master_xy]]) -> RegistrationTransform
   - match_control_points(session, aux_drawing_id, master_drawing_id) -> list of paired fractional centroids
     Match DrawingSurveyPoint rows by normalized northing+easting (or station + coords)
   - Require >= 2 pairs; use least-squares similarity transform for scale+translate (+ rotation if >= 3)

2. MODIFY backend/services/evidence_investigation_persistence.py:
   - After aux index + survey extract, call match_control_points for each linked aux vs master
   - Persist evidence.meta["registration_transform"] = {scale_x, scale_y, translate_x, translate_y, rotation_degrees}
   - Store meta.registration_control_point_count

3. ADD backend/tests/test_registration_from_survey.py:
   - Synthetic control points: aux (0.2,0.2)->master (0.5,0.47), aux (0.3,0.25)->master (0.55,0.49)
   - Assert projected aux bbox lands near expected master coords
   - Assert None when zero shared points

4. MODIFY backend/tests/test_location_match_orchestrator.py:
   - test_coordinate_lookup_projects_aux_match_with_registration_transform — extend to multi-point polyline projection

TEST:
cd backend && pytest tests/test_registration_from_survey.py tests/test_location_match_orchestrator.py -q --tb=short
```

---

## S-5 — Project full polyline to master and persist overlay

- [ ] **S-5.1** `_project_aux_bbox_to_master` generalized to `_project_aux_polyline_to_master`
- [ ] **S-5.2** Agent applies projection to scope geometry before persist when `source_drawing_id != master`
- [ ] **S-5.3** Without transform: keep `needs_review`, do **not** emit aux-space coords on master overlay
- [ ] **S-5.4** Overlay has ≥3 points spanning campus area (not bottom-left corner)

**Plain English:** Move every vertex of the C4.20 sewer line onto master 661 using the registration — that's what the user sees as the green highlight.

**PROMPT — copy below:**

```
S-5: Project auxiliary scope polyline onto master drawing.

1. MODIFY backend/ai/pipelines/location_match_orchestrator.py:
   - Add project_polyline_to_master(points, registration_transform) -> tuple[tuple[float,float], ...]
   - Clamp each vertex with clamp_point_to_page / fractional_coords helpers

2. MODIFY backend/ai/agents/inspection_location_agent.py:
   - After trace_scope_geometry, if scope.type==polyline and meta.source_drawing_id != master:
     - If registration_transform present: project all vertices, update scope
     - Else: set status needs_review, add aux_coords_unprojected to rationale; do not persist wrong master polyline

3. MODIFY backend/services/inspection_match_persistence.py (if needed):
   - Persist scope_geometry_json with projected master points

4. ADD integration test backend/tests/test_inspection_location_agent.py:
   - Mock dossier with aux polyline + registration transform
   - Assert persisted scope points near master campus (~0.5, 0.47), path length >> 0.05 normalized

TEST:
cd backend && pytest tests/test_inspection_location_agent.py tests/test_location_match_orchestrator.py -q --tb=short
```

---

## S-6 — Re-match Run #642, eval gate, manual QA

- [ ] **S-6.1** Re-index aux drawing 1084 (forced OCR) if station/coord tokens stale
- [ ] **S-6.2** Clear `evidence.meta.matchInvestigation` cache OR wait 24h before re-match
- [ ] **S-6.3** Re-run inspection match job for run 642
- [ ] **S-6.4** Eval: `ucsf-642-ss-run` passes path_overlap ≥ 0.70
- [ ] **S-6.5** UI overlay matches green highlight precision at 126% zoom

**Plain English:** Run the full pipeline on the real case and confirm the overlay looks like your green markup.

**PROMPT — copy below:**

```
S-6: Re-match Run #642 and verify eval + UI.

1. OPTIONAL backend/scripts/verify_run_642_scope.py (or extend verify_v1_golden.py):
   - Constants: PROJECT_ID=2, EVIDENCE_ID=632, RUN_ID=642, MASTER_ID=661, AUX_ID=1084
   - --rerun-match calls run_inspection_match_job with inspection_run_id=642
   - Assert overlay scope_geometry_json.type == polyline
   - Assert len(points) >= 3
   - Assert first point x in [0.35, 0.65] (campus band, not bottom-left corner)

2. Update ucsf-642-ss-run expected_match_status to matched once registration + projection land

No matcher changes in this step — verification only.

TEST (unit + eval):
cd backend && pytest tests/test_location_match_eval.py -q --tb=short
cd backend && python scripts/eval_location_match.py --suite ucsf --min-path-overlap 0.70
```

**Re-match commands (dev DB):**

```bash
# 1. Re-index aux 1084 if needed (worker must be running)
cd backend && python -c "
from database import SessionLocal
from services.drawing_index_jobs import enqueue_drawing_index_job
db = SessionLocal()
enqueue_drawing_index_job(db, drawing_id=1084, project_id=2)
db.commit()
print('enqueued index for 1084')
"

# 2. Clear investigation cache (forces fresh link follow + station extract)
cd backend && python -c "
from database import SessionLocal
from models.models import EvidenceRecord
db = SessionLocal()
ev = db.get(EvidenceRecord, 632)
meta = dict(ev.meta or {})
meta.pop('matchInvestigation', None)
ev.meta = meta
db.commit()
print('cleared matchInvestigation cache')
"

# 3. Re-run match
cd backend && python -c "
from database import SessionLocal
from services.inspection_matching_jobs import run_inspection_match_job
db = SessionLocal()
status = run_inspection_match_job({
    'inspection_id': '632',
    'drawing_id': 661,
    'page': 1,
    'inspection_run_id': 642,
    'project_id': 2,
}, db)
db.commit()
print('match status:', status)
"

# 4. Eval gate
cd backend && python scripts/eval_location_match.py --suite ucsf --min-path-overlap 0.70
```

**Manual QA checklist:**

```
Prerequisites:
  [ ] Procore OAuth connected (project 2)
  [ ] Worker running
  [ ] S-0 truth polyline annotated in ucsf.json

UI (localhost:5173/objects?projectId=2&drawingId=661&run=642):
  [ ] Overlay is polyline (not tiny corner rect)
  [ ] Line follows sewer corridor through campus (compare to green C4.20 reference)
  [ ] ≥ 3 vertices visible at 126% zoom
  [ ] Status matched OR needs_review with honest aux_coords_unprojected (never wrong corner pin)

Logs:
  [ ] station_from=10+00 station_to=10+90.95 (or 10+93) in investigation meta
  [ ] scoped_point_count >= 6 on drawing 1084
  [ ] registration_control_point_count >= 2 OR explicit aux_coords_unprojected
  [ ] scope=aux_survey_chain or scope=station_labels in rationale

Eval:
  [ ] ucsf-642-ss-run path_overlap >= 0.70
  [ ] endpoint_error within MAX_ENDPOINT_ERROR
```

---

## Success criteria (definition of done)

| Check | Plain English |
|-------|----------------|
| Truth label exists | `ucsf-642-ss-run` in ucsf.json with polyline ≥4 points |
| Station range extracted | evidence 632 meta has 10+00 / 10+90.95 from aux OCR |
| Aux polyline built | Scope meta `aux_survey_chain`, ≥3 vertices on 1084 |
| Registration computed | `registration_transform` in evidence meta OR honest `needs_review` |
| Master placement correct | Polyline center near campus (~0.5, 0.47), not (0.20, 0.84) |
| Eval passes | `path_overlap ≥ 0.70` on ucsf-642-ss-run |
| UI matches green highlight | Visual QA at 126% — full trench run, not corner sliver |

---

## Step dependency graph

```
S-0 (truth label)
  ↓
S-1 (station range extract)
  ↓
S-2 (aux polyline chain) ──→ S-3 (aux token trace)
  ↓                              ↓
S-4 (registration) ←─────────────┘
  ↓
S-5 (project to master)
  ↓
S-6 (re-match + eval + QA)
```

---

*Created: 2026-08-26 — Sewer scope precision plan for Run #642 / master 661 / aux 1084 (C4.20 green-highlight parity).*
