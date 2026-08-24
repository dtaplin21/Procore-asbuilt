# Location Match Investigation Plan — Move Link & Clue Work Off Upload

**Goal:** Upload is **only** “save the file and attach it to the inspection run.” All PDF hyperlink following, linked-plan fetching, clue extraction, survey coordinate mining, and auxiliary drawing registration happens **once**, at location-match time, through the **existing agent dossier path** — not a duplicate upload pipeline and not a second investigation module.

**Why:** Run **524** / evidence **478** showed link text was captured at upload but **positioned coordinates never landed on Master.pdf**. Worse: the codebase **already re-fetches links** inside `build_evidence_dossier()` (`run_pdf_investigation`) but **does not persist** registration/clues/survey points — so upload and match both do link work, neither owns the full story.

**Golden case (dev):** project `2`, master `661`, evidence with linked **U1.C4.20** install PDF, N/E **2131764.84 / 6051541.82**, station **11+14.23**

**How to use:** Work top → bottom. Copy one **PROMPT** block into Cursor Agent. Check `[ ]` when done. Each step has a **Plain English** line.

**Related doc:** `Notes/inspection_location_agent_plan.md` (agent architecture — this plan changes *when* investigation runs, not the end UX)

---

## Design principle — one front door, no duplicate detective

```
INEFFICIENT (what the old plan draft avoided, and what we avoid now)
────────────────────────────────────────────────────────────────────
  upload → follow links + persist everything
  match  → follow links AGAIN (summaries only) + read stale DB
  NEW match_time_evidence_investigation.py → third copy of same steps


EFFICIENT (this plan)
─────────────────────
  upload → save file only → enqueue match job

  match job → InspectionLocationAgent.run()
                → build_evidence_dossier(investigate=True)     ← SINGLE FRONT DOOR
                     1. run_pdf_investigation()               ← already exists
                     2. persist_evidence_investigation()       ← thin NEW wrapper (DB only)
                     3. ensure auxiliary drawings indexed
                     4. load clues + scoped points from DB
                     5. assemble dossier
                → generate_all_location_candidates()
                → vision (master PNG only)
                → persist overlay
```

**Plain English:** Upgrade the detective the agent already calls (`build_evidence_dossier`). Don't hire a second detective at upload or a third in a new service file.

---

## What already exists (reuse, don't rebuild)

| Module | Today | After this plan |
|--------|-------|-----------------|
| `ai/agents/tools/pdf_investigation.py` → `run_pdf_investigation()` | Called from dossier; summaries only | **Canonical investigator** — extend return value |
| `ai/agents/evidence_dossier.py` → `build_evidence_dossier()` | Re-fetches links; reads clues from upload DB | **Owns investigation + dossier** when `investigate=True` |
| `ai/agents/inspection_location_agent.py` | Calls `build_evidence_dossier` then matchers | **Unchanged** call shape |
| `services/evidence_document_extraction.py` | Does everything at upload | **Slim upload only** |
| `services/linked_drawing_registration.py` | Called at upload | Called from **`persist_evidence_investigation`** |
| `ai/pipelines/pdf_link_follower.py` | Used by upload + pdf_investigation | Used **only** at match (via pdf_investigation) |

**Do NOT create** `match_time_evidence_investigation.py` — that duplicates logic already split across upload and dossier.

---

## Before vs after (user-visible)

```
TODAY
─────
Upload PDF (slow — 7+ min possible)
  → follow hyperlinks, register drawings, extract clues/coords
  → map_document_to_overlays (provisional pin)
  → run status = complete
  → enqueue match
Match
  → dossier re-follows links (summaries only)
  → reads upload-time DB; often no positioned coords on master


TARGET
──────
Upload PDF (fast — seconds)
  → save file + evidence record
  → run status = queued/processing
  → enqueue match only
Match worker
  → build_evidence_dossier(investigate=True)
  → follow links, persist, index aux drawings, extract positioned coords
  → agent places overlay on master
  → run status = complete
```

---

## Hard rules (every PR)

| Rule | Plain English |
|------|----------------|
| **Upload = storage only** | Upload is dropping a folder on someone's desk — don't open it yet. |
| **One investigation path** | Only `build_evidence_dossier(investigate=True)` follows links for matching. |
| **Persist after investigate** | Link follow must register drawings + clues + survey meta in DB before matchers run. |
| **No double fetch** | Remove upload link follow; dossier must not call `follow_pdf_links` twice per match. |
| **Positioned coords beat plain text** | N/E in a text dump isn't enough — need bbox on indexed sheet OCR. |
| **Master placement only** | Final overlay on master drawing; aux coords must be projected (PR-E). |
| **Idempotent** | Re-match uses cache in `evidence.meta.matchInvestigation` when fresh (< 24h). |

---

## What moves off upload

| Today at upload (`evidence_document_extraction.py`) | New owner |
|-----------------------------------------------------|-----------|
| `follow_pdf_links()` | `run_pdf_investigation` at dossier build |
| `register_linked_pdfs_as_auxiliary_drawings()` | `persist_evidence_investigation()` |
| `replace_evidence_drawing_links()` | `persist_evidence_investigation()` |
| `extract_survey_points_from_evidence()` + meta | `persist_evidence_investigation()` |
| `run_document_extraction()` (clues) | `persist_evidence_investigation()` |
| `classify_and_persist_evidence_kind()` | `persist_evidence_investigation()` |
| Merged linked text in `evidence.text_content` | Optional 2k preview; full text from investigation |

| Upload keeps | Why |
|--------------|-----|
| Save file + evidence record | Core upload job |
| `maybe_enqueue_drawing_index_job()` for **master** | Master should be indexed before match |
| Enqueue `inspection_match` job | Kick off detective |

| Upload removes / defers | Why |
|-----------------------|-----|
| `map_document_to_overlays()` | Match-owned overlay avoids wrong provisional pin |
| Run status `complete` at upload end | Run completes when match finishes |

---

## File map (lean)

| Action | Path |
|--------|------|
| ADD | `backend/services/evidence_investigation_persistence.py` — thin DB wrapper only |
| ADD | `backend/tests/test_evidence_investigation_persistence.py` |
| MODIFY | `backend/ai/agents/tools/pdf_investigation.py` — return full `LinkFollowResult` + investigation payload |
| MODIFY | `backend/ai/agents/evidence_dossier.py` — `investigate=True` gate; call persist before loading clues |
| MODIFY | `backend/services/evidence_document_extraction.py` — slim upload path |
| MODIFY | `backend/api/routes/evidence.py` — slim upload; run status; defer overlays |
| MODIFY | `backend/services/inspection_matching_jobs.py` — index_pending / re-queue; logging only (no second investigate call) |
| MODIFY | `backend/ai/pipelines/location_match_orchestrator.py` — aux → master projection (PR-E) |
| MODIFY | `backend/ai/pipelines/pdf_link_follower.py` — match budgets, retry, depth (PR-F) |
| MODIFY | `backend/config.py` — `PDF_LINK_FOLLOW_MAX_EXTERNAL_MATCH`, depth |
| MODIFY | `client/.../inspection_runs_panel.tsx` — "Investigating linked files…" |

**Not adding:** `match_time_evidence_investigation.py`

---

## PR-A — Slim upload (save file only)

- [x] **A-1** Add `ingest_evidence_upload_only()` — no link follow, no clues
- [x] **A-2** Upload route uses slim path; enqueue match job directly
- [x] **A-3** Skip `map_document_to_overlays` on upload (match owns overlay)
- [x] **A-4** Run stays `queued`/`processing` until match completes
- [x] **A-5** Tests: upload never calls `follow_pdf_links`

**Plain English:** Upload stores the PDF and schedules location match. Nothing is fetched from Procore yet.

**PROMPT — copy below:**

```
PR-A: Slim evidence upload — storage only.

1. backend/services/evidence_document_extraction.py
   - Add ingest_evidence_upload_only(session, *, evidence_id, file_path):
     - Optional: store base OCR/text from uploaded file ONLY (extract_document, no follow_pdf_links)
     - Do NOT call register_linked_pdfs, extract_survey_points, run_document_extraction, classify_evidence_kind
   - Mark ingest_evidence_document_extraction deprecated in docstring (keep for tests/migration)

2. backend/api/routes/evidence.py upload_inspection_run_evidence:
   - Replace ingest_evidence_document_extraction with ingest_evidence_upload_only
   - Remove or gate map_document_to_overlays + create_drawing_overlays on upload
   - Enqueue maybe_enqueue_inspection_match_job directly (master index gating unchanged)
   - Do NOT set run status "complete" — leave queued/processing until match job finishes

3. Tests: backend/tests/test_evidence_document_extraction.py, test_evidence_route.py
   - Assert follow_pdf_links NOT called on upload path

Run: cd backend && pytest tests/test_evidence_document_extraction.py tests/test_evidence_route.py -q --tb=short
```

---

## PR-B — Extend existing investigator + thin persist wrapper

- [x] **B-1** `run_pdf_investigation()` returns `LinkFollowResult` (not just summaries)
- [x] **B-2** Add `EvidenceInvestigationPayload` dataclass (links + merged text + errors)
- [x] **B-3** Add `persist_evidence_investigation()` in services (DB side effects only)
- [x] **B-4** Remove duplicate link follow from upload (PR-A dependency)
- [x] **B-5** Tests for persist wrapper (mock link result)

**Plain English:** Teach the existing PDF investigator to hand off everything it found to a small "filing clerk" that saves linked drawings, clues, and coordinates to the database.

**PROMPT — copy below:**

```
PR-B: Extend run_pdf_investigation + add persist_evidence_investigation (thin).

1. backend/ai/agents/tools/pdf_investigation.py
   - Extend PdfInvestigationResult (or add EvidenceInvestigationPayload) to include:
     link_result: LinkFollowResult  (fetched_pdfs, supplemental_text, cross_refs, errors)
     merged_text: str               (linked content first, then base — same order as today upload)
     base_text: str
   - run_pdf_investigation already calls follow_and_capture_links — expose full link_result on return
   - Do NOT add DB imports here (keep ai/ layer pure)

2. CREATE backend/services/evidence_investigation_persistence.py

   def persist_evidence_investigation(
     session, *, evidence_id, file_path, project_id, payload: EvidenceInvestigationPayload
   ) -> EvidenceInvestigationPersistResult:
     - register_linked_pdfs_as_auxiliary_drawings(session, project_id, link_result=payload.link_result, ...)
     - replace_evidence_drawing_links(session, evidence, commit=False)
     - extract_survey_points_from_evidence(session, evidence, file_path) + persist_evidence_survey_meta
     - run_document_extraction(session, file_id=str(evidence_id), content=payload.merged_text, ...)
     - classify_and_persist_evidence_kind(...)
     - evidence.meta["matchInvestigation"] = {followed, skipped, errors, linked_drawing_ids, at}
     - evidence.text_content = optional short preview only (first 2000 chars of merged_text) OR leave base only
     - Return linked_drawing_ids, extraction id, survey point count

   Move logic FROM evidence_document_extraction.ingest_evidence_document_extraction — do not duplicate.

3. CREATE backend/tests/test_evidence_investigation_persistence.py
   - Mock register_linked_pdfs, assert called with link_result from payload
   - Assert matchInvestigation meta written

Run: cd backend && pytest tests/test_evidence_investigation_persistence.py tests/test_pdf_investigation_tools.py -q --tb=short
```

---

## PR-C — Single front door: `build_evidence_dossier(investigate=True)`

- [ ] **C-1** Add `investigate: bool = True` param to `build_evidence_dossier`
- [ ] **C-2** When `investigate=True`: run pdf investigation → persist → then load clues (replace `_pdf_investigation_for_evidence` duplicate fetch)
- [ ] **C-3** Cache: skip re-investigate if `evidence.meta.matchInvestigation.at` fresh (< 24h) unless `force=True`
- [ ] **C-4** `InspectionLocationAgent` passes `investigate=True` (default)
- [ ] **C-5** Tests: dossier calls persist once; no double follow_pdf_links

**Plain English:** When the agent starts, the dossier builder opens the PDF, follows every link, saves results to the DB, *then* reads them back to build the case file. One trip, not two.

**PROMPT — copy below:**

```
PR-C: build_evidence_dossier owns match-time investigation (single front door).

1. backend/ai/agents/evidence_dossier.py

   def build_evidence_dossier(..., investigate: bool = True, force_investigate: bool = False):

   When investigate and (force or cache stale):
     a. Resolve evidence file path from storage_key
     b. result = run_pdf_investigation(file_path, max_links=settings.pdf_link_follow_max_external_match)
     c. persist_evidence_investigation(session, evidence_id=..., payload=result)
     d. session.flush()

   REMOVE _pdf_investigation_for_evidence separate link fetch — merged into step b-c above.
   AFTER persist: _load_extraction_and_clues, load_linked_drawings, scoped survey points as today.

   Cache: if evidence.meta.matchInvestigation.investigated_at within 24h and not force_investigate, skip b-c.

2. backend/ai/agents/inspection_location_agent.py
   - build_evidence_dossier(..., investigate=True) — no other changes required

3. backend/services/inspection_matching_jobs.py
   - run_inspection_match_job: do NOT add separate investigate call — agent/dossier owns it
   - Log inspection_investigation_complete after agent returns (read meta.matchInvestigation)

4. Tests: backend/tests/test_evidence_dossier.py
   - Patch run_pdf_investigation + persist_evidence_investigation
   - Assert persist called once per dossier build
   - Assert follow_pdf_links not called twice

Run: cd backend && pytest tests/test_evidence_dossier.py tests/test_inspection_location_agent.py -q --tb=short
```

---

## PR-D — Index linked drawings during dossier investigate

- [ ] **D-1** After `persist_evidence_investigation`, enqueue render + index for new auxiliary drawings
- [ ] **D-2** `build_evidence_dossier` waits or agent returns `index_pending` if aux not ready
- [ ] **D-3** Lazy survey extraction on auxiliary drawing IDs after index ready
- [ ] **D-4** Log `scoped_point_count` per drawing_id

**Plain English:** When match finds a linked sewer plan, it OCRs and indexes that plan before trying to place coordinates — like reading the referenced page before marking the map.

**PROMPT — copy below:**

```
PR-D: Index auxiliary drawings during dossier investigation.

1. backend/services/evidence_investigation_persistence.py (or dossier after persist):
   - For each new linked_drawing_id: maybe_enqueue drawing_render + drawing_index jobs
   - Return list of drawing_ids needing index

2. backend/ai/agents/evidence_dossier.py OR inspection_location_agent.py:
   - After persist, check auxiliary drawings index_status via get_master_drawing_index_readiness pattern
   - If any auxiliary not ready: agent returns index_pending (existing path) — job re-queues via flush_deferred_inspection_matches_for_drawing

3. After aux index ready: _load_scoped_survey_points includes auxiliary IDs (already in orchestrator)
   - Ensure lazy_extract runs on aux drawing 1084-class fixtures
   - Survey source tag: match_investigation (never pre2_baseline_seed)

4. Tests: scoped_point_count > 0 when aux drawing indexed with N/E OCR fixture

Run: cd backend && pytest tests/test_evidence_dossier.py tests/test_survey_point_validation.py -q --tb=short
```

---

## PR-E — Project auxiliary coordinates onto master drawing

- [ ] **E-1** When coordinate match hits auxiliary drawing, project bbox to master
- [ ] **E-2** Use registration transform when available
- [ ] **E-3** Else emit `needs_review` with `aux_coords_unprojected` — never silent wrong pin
- [ ] **E-4** Update `ucsf.json` eval label notes

**Plain English:** Coordinates found on C4.20 get translated to the equivalent spot on Master.pdf — like aligning two maps by shared survey numbers.

**PROMPT — copy below:**

```
PR-E: Project auxiliary survey matches onto master drawing.

1. backend/ai/pipelines/location_match_orchestrator.py
   - _prefer_master_scoped_point / _coordinate_lookup_candidates:
     When best scoped point drawing_id != master_drawing_id:
       Try _project_aux_bbox_to_master(session, aux_point, master_drawing_id)
       Use evidence registration transform if present
       Else needs_review candidate notes="aux_coords_unprojected"
   - Add tests for projection helper

2. Log source_drawing_id + projected=true/false in generate_all_location_candidates

3. backend/tests/fixtures/location_match_labels/ucsf.json — update expected notes

Run: cd backend && pytest tests/test_location_match_eval.py tests/test_inspection_location_agent.py -q --tb=short
```

---

## PR-F — Match-time hyperlink budget (on existing follower)

- [ ] **F-1** `PDF_LINK_FOLLOW_MAX_EXTERNAL_MATCH` config (default 10)
- [ ] **F-2** Optional depth limit for nested links in `pdf_link_follower`
- [ ] **F-3** One retry on Procore timeout
- [ ] **F-4** `run_pdf_investigation` passes match limits to follower

**Plain English:** Match can follow more links and retry once if Procore is slow — applied to the existing link follower, not a new module.

**PROMPT — copy below:**

```
PR-F: Match hyperlink budget on pdf_link_follower (no new service).

1. backend/config.py: pdf_link_follow_max_external_match (default 10), pdf_link_follow_max_depth (default 2)

2. backend/ai/pipelines/pdf_link_follower.py:
   - follow_pdf_links(..., max_external=..., max_depth=...)
   - Retry fetch once on timeout

3. backend/ai/agents/tools/pdf_investigation.py:
   - run_pdf_investigation uses settings.pdf_link_follow_max_external_match

4. Tests: test_pdf_link_follower.py

Run: cd backend && pytest tests/test_pdf_link_follower.py -q --tb=short
```

---

## PR-G — UI & run status honesty

- [ ] **G-1** Run `complete` only after match job finishes
- [ ] **G-2** Panel: "Investigating linked files…" while processing
- [ ] **G-3** Upload toast: no misleading overlay count

**Plain English:** UI says "reading linked plans" instead of showing a wrong pin and "upload complete."

**PROMPT — copy below:**

```
PR-G: UI reflects match-time investigation.

1. backend: run status complete only in inspection_matching_jobs after match job success/fail
2. client inspection_runs_panel.tsx: processing label "Investigating linked files…"
3. Upload response: overlays_created=0 or omit until match completes

Run: cd client && npm test -- inspection_runs_panel -q
```

---

## PR-H — Cleanup & docs

- [ ] **H-1** Remove dead upload extraction code paths
- [ ] **H-2** Update `.env.example` + cross-ref in `inspection_location_agent_plan.md`
- [ ] **H-3** Full test suite + UCSF eval

**Plain English:** Delete leftover upload detective code; document new flow; prove UCSF case.

**PROMPT — copy below:**

```
PR-H: Cleanup.

1. Remove extract_evidence_file_content_with_links from upload path; keep function if tests need it
2. Notes/inspection_location_agent_plan.md — link to this plan; note dossier is single front door
3. backend/.env.example — PDF_LINK_FOLLOW_MAX_EXTERNAL_MATCH, PDF_LINK_FOLLOW_MAX_DEPTH
4. cd backend && pytest -q --tb=short

Run eval: python backend/scripts/eval_location_match.py (ucsf label)
```

---

## Success criteria

| Check | Plain English |
|-------|----------------|
| Upload < few seconds | No Procore fetch at upload |
| Single `follow_pdf_links` per match | Logs show one link-follow pass, not two |
| `persist_evidence_investigation` in dossier path | Linked drawings registered at match |
| `scoped_point_count > 0` on aux C4.20 OR projected master pin | Coords from linked plan used |
| Run 524 scenario ≠ title-block "Utility MR" only | Better than reference_lookup corner pin |
| No `pre2_baseline_seed` | No fake eval seeds |

---

## Manual QA (after PR-C+)

```
1. Delete runs on master 661 (optional)
2. Upload inspection PDF — fast return, run status processing/queued
3. Worker logs:
   - pdf_link_follow_complete (once)
   - linked_drawing_registered
   - drawing_index on auxiliary
   - inspection_match_result
4. Objects ?run=<id> — overlay on sewer run OR honest needs_review
5. evidence.meta.matchInvestigation populated
```

---

## Open decisions (resolved for this plan)

| # | Decision |
|---|----------|
| 1 | `map_document_to_overlays` on upload? **No** — match owns overlay |
| 2 | New `match_time_evidence_investigation.py`? **No** — extend dossier + persist wrapper |
| 3 | Re-investigate on retry? **Cache 24h** in `evidence.meta.matchInvestigation` |
| 4 | Vision on linked PDF pages? **Phase 2** after PR-E |
| 5 | Move AI model imports? **No** — vision stays on master in agent; no import shuffle needed |

---

## Module roles after this plan

| Module | Plain English |
|--------|----------------|
| `evidence.py` | Saves file, enqueues match |
| `pdf_investigation.run_pdf_investigation` | Opens PDF, follows links, reads pages |
| `evidence_investigation_persistence.persist_*` | Files linked plans + clues + coords to DB |
| `evidence_dossier.build_evidence_dossier` | **Front door** — investigate, persist, assemble case file |
| `inspection_location_agent` | Decides where on master; calls dossier then matchers |
| `location_match_orchestrator` | Coordinate/clue/region candidates + aux projection |
| `pdf_link_follower` | Low-level hyperlink click + download |
| `inspection_matching_jobs` | Worker shell — runs agent, updates run status |

---

*Updated: 2026-08-24 — Lean plan: single front door via `build_evidence_dossier`, extend existing `run_pdf_investigation`, thin `persist_evidence_investigation` wrapper.*
