---
name: Inspection→Drawing→Procore Pipeline (Phased)
owner: QC/QA AI Platform
status: draft
last_updated: 2026-02-27
---

# Inspection→Drawing→Procore Pipeline (Phased)

## Goal

Support this end-to-end workflow without clashing with `Notes/IMPLEMENTATION_PHASES.md`:

- Upload a master drawing (floor plan)
- Upload subsection drawings, spec subsections, and inspection documents
- AI detects inspection type, extracts outcomes, maps inspected areas onto the master drawing (overlay geometry)
- System detects when subsection drawings do **not** match the master (diff + findings)
- UI renders overlays + inspection history + mismatch alerts
- Generate Procore update payload and sync

## Crosswalk to `Notes/IMPLEMENTATION_PHASES.md`

This doc is an implementation pipeline view. The roadmap in `Notes/IMPLEMENTATION_PHASES.md` is the source-of-truth for sequencing.\n
\n
**Legend**:\n
- **Maps to roadmap**: directly corresponds to an existing phase/step in `IMPLEMENTATION_PHASES.md`\n
- **New (additive)**: not explicitly listed in the roadmap; added to support drawing subsection alignment + mismatch detection\n
\n
| Pipeline phase (this doc) | Roadmap alignment | Notes |\n
|---|---|---|\n
| Phase 0 — Dashboard anchor (Project Summary) | **Maps to Phase 2 / Step 4** | Required to make the project-scoped drawing workspace and health state real |\n
| Phase 1 — Evidence persistence (drawings + evidence_records) | **Maps to Phase 4 / Step 8** (EvidenceRecord) + supports Phase 2 | Evidence tables + minimal CRUD |\n
| Phase 2 — Sub-drawing registration + alignment | **New (additive)** | Needed for subsection→master mapping |\n
| Phase 3 — Diff/mismatch detection | **New (additive)** | Needed to alert “sub drawing does not match master” |\n
| Phase 4 — Inspection extraction → overlay generation | Partially maps to **Phase 2 / Step 6** (Findings section) and future phases | Produces overlays + findings; UI wiring follows dashboard scoping |\n
| Phase 5 — Procore writeback | Not explicitly in roadmap (integration track) | Uses completed overlays/results to push to Procore |\n

## What we already have (verified in repo)

### Frontend

- Dashboard has project selector + project-scoped insights query wiring.
- Settings supports Procore connect/disconnect and an internal-id company selector.
- `client/src/pages/objects.tsx` contains a **Drawing Viewer mock** (no real upload/viewer).
- `client/src/pages/inspections.tsx` exists as UI but relies on `/api/inspections` which is currently stubbed.

### Backend

- FastAPI app with centralized error handling + request logging.
- DB-backed Procore token persistence with active company context.
- `/api/projects` reads from DB.
- `/api/insights` is DB-backed via `findings`.
- `/api/objects`, `/api/inspections`, `/api/submittals`, `/api/rfis` routes exist but storage methods are mostly stubs.
- `/api/procore/sync` fetches Procore projects but does **not** store locally yet.

### Data model

- `projects`, `findings`, `job_queue`, `companies`, `procore_connections` exist.
- No DB tables for drawings, uploads, evidence records, inspection runs, overlays, alignments.

### AI pipeline

- No implemented AI pipeline; `backend/ai/` is empty.

## Phased implementation (step-by-step)

### Phase 0 — Dashboard anchor (Project Summary)

- Add `GET /api/projects/{project_id}/dashboard/summary` and wire the dashboard top section.
- This becomes the anchor for “current drawing + sync health + current active company context”.

### Phase 1 — Core drawing + evidence persistence (Phase 4-compatible)

Add Postgres tables (Alembic) and ORM models:

- **`drawings`**
  - `id` (int PK)
  - `project_id` (FK → projects.id)
  - `source` ("upload"|"procore")
  - `name`
  - `file_url` (or `storage_key`)
  - `content_type` ("application/pdf", "image/png")
  - `page_count` (nullable)
  - `created_at`, `updated_at`
- **`evidence_records`** (Phase 4)
  - `id`, `project_id`
  - `type` ("spec"|"inspection_doc")
  - `trade` (nullable), `spec_section` (nullable)
  - `title`, `source_file_url`
  - `text_content` (nullable), `meta` (JSON)
  - timestamps

Backend endpoints (project-scoped):

- `POST /api/projects/{project_id}/drawings` (multipart upload)
- `GET /api/projects/{project_id}/drawings`
- `GET /api/projects/{project_id}/drawings/{drawing_id}`
- `POST /api/projects/{project_id}/evidence` (multipart upload; type=spec|inspection_doc)
- `GET /api/projects/{project_id}/evidence?type=...`

### Phase 2 — Sub-drawing registration + alignment (NEW)

To support “subsection drawing ↔ master drawing mapping” you need explicit linkage and a computed transform.

Add tables:

- **`drawing_regions`** (user-defined regions on the master)
  - `id` (int PK)
  - `master_drawing_id` (FK → drawings.id)
  - `label` (string)
  - `page` (int, default 1)
  - `geometry` (JSON)  # polygon/rect in master coordinate system
  - timestamps
- **`drawing_alignments`** (sub drawing → master registration)
  - `id` (int PK)
  - `master_drawing_id` (FK)
  - `sub_drawing_id` (FK)
  - `region_id` (nullable FK → drawing_regions.id)
  - `method` ("manual"|"feature_match"|"vision")
  - `transform` (JSON)  # homography/affine + confidence
  - `status` ("queued"|"processing"|"complete"|"failed")
  - `error_message` (nullable)
  - timestamps

Transform JSON contract (minimal):

- `{ "type": "homography", "matrix": [9 numbers], "confidence": 0.0-1.0, "page": 1 }`

Backend endpoints:

- `POST /api/projects/{project_id}/drawings/{master_drawing_id}/regions`
- `GET /api/projects/{project_id}/drawings/{master_drawing_id}/regions`
- `POST /api/projects/{project_id}/drawings/{master_drawing_id}/alignments`
  - body: `{ "sub_drawing_id": 12, "region_id": 3, "method": "manual" }`
- `GET /api/projects/{project_id}/drawings/{master_drawing_id}/alignments`

UI needs (MVP):

- On the drawing viewer, allow user to draw a region box/polygon and attach a sub-drawing to it.
- Kick off alignment job; show status.

### Phase 3 — Diff/mismatch detection (NEW)

To answer: “Does the subsection drawing match the master drawing?”

Add table:

- **`drawing_diffs`**
  - `id` (int PK)
  - `alignment_id` (FK → drawing_alignments.id)
  - `summary` (text)
  - `severity` ("low"|"medium"|"high"|"critical")
  - `diff_regions` (JSON)  # list of geometry regions in master coords
  - `created_at`

Diff region JSON contract (overlay-friendly):

- `[ { "page": 1, "type": "polygon", "points": [[x,y],...], "label": "Mismatch", "confidence": 0.0-1.0 } ]`

Back-end pipeline module:

- `backend/ai/pipelines/drawing_diff.py`
  - Inputs: master image/page, sub image/page, transform
  - Output: diff regions + summary + severity
  - Persist to `drawing_diffs`
  - Create a `findings` row when mismatch severity ≥ threshold

Endpoints:

- `POST /api/projects/{project_id}/drawings/{master_drawing_id}/diffs`
  - body: `{ "alignment_id": 55 }`
- `GET /api/projects/{project_id}/drawings/{master_drawing_id}/diffs?alignment_id=55`

UI:

- Render diff overlays on the master drawing
- Show a “Mismatch found” banner and link to the related finding

### Phase 4 — Inspection extraction → overlay generation

Add tables:

- **`inspection_runs`**
  - `id`, `project_id`, `master_drawing_id`
  - `evidence_id` (FK → evidence_records.id)
  - `inspection_type` (string)
  - `status`, `started_at`, `completed_at`, `error_message`
- **`inspection_results`**
  - `id`, `inspection_run_id`
  - `outcome` ("pass"|"fail"|"mixed"|"unknown")
  - `notes` (text)
  - `created_at`
- **`drawing_overlays`**
  - `id`, `master_drawing_id`, `inspection_run_id` (nullable), `diff_id` (nullable)
  - `geometry` (JSON)
  - `status` ("pass"|"fail"|"unknown")
  - `meta` (JSON)
  - `created_at`

Pipeline module:

- `backend/ai/pipelines/inspection_mapping.py`
  - classify inspection type (trade/spec hints + LLM fallback)
  - extract outcomes (pass/fail/notes)
  - map areas to master drawing coordinates (MVP: use `drawing_regions` linkage; later: vision)
  - write overlays + create findings when needed

Endpoints:

- `POST /api/projects/{project_id}/inspections/runs`
- `GET /api/projects/{project_id}/inspections/runs?...`
- `GET /api/projects/{project_id}/drawings/{drawing_id}/overlays`

### Phase 5 — Procore writeback

Add endpoint:

- `POST /api/projects/{project_id}/procore/writeback`
  - `{ "inspection_run_id": 123, "mode": "dry_run"|"commit" }`

Implementation:

- Build a “payload builder” service:
  - `backend/services/procore_writeback.py`
- Extend `backend/services/procore_client.py` with the specific Procore write endpoints you decide (comments, custom fields, inspection items, etc.).

## How this avoids clashing with existing phases

- Phase 2 Step 4 is addressed first (project-scoped summary).
- Evidence uploads are implemented as `evidence_records` (exactly the intent of Phase 4).
- Diff/alignment are additive modules that create `findings` (fits existing insights UI).

## Verification checklist (end-to-end)

- Upload master drawing → `drawings` row exists
- Upload sub drawing → `drawings` row exists with alignment created
- Create region + alignment → `drawing_alignments.transform` computed/stored
- Run diff → `drawing_diffs` row exists + overlays returned + finding created on mismatch
- Upload inspection doc → `evidence_records` row exists
- Run inspection mapping → overlays + inspection_results exist + finding created on failure
- Writeback dry_run returns payload; commit performs Procore update

