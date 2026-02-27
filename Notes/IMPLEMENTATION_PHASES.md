## Implementation Phases (Current Roadmap)

This is the source-of-truth roadmap for building the QC/QA AI Automation Platform with Procore integration.

---

## Phase 1 — Project scoping foundation (Done)

### Step 1 — Decide your project identifier (use Procore project id)

Use `procore_project_id` as the external ID and create an internal `projects.id` primary key if you want, but the key is:
**every record must reference a project**.

**Add to DB models** (`backend/models/models.py`)

Add a `Project` table (if you don’t have one yet):
- `id` (internal int PK)
- `company_id` (FK)
- `procore_project_id` (string or int, unique per company)
- `name`
- `last_sync_at`
- `sync_status` (optional)
- timestamps

Then add `project_id` to:
- `JobQueue`
- your new `Finding` table (or “Insight” if you reuse it)

**Goal of Step 1**: you can store “which project this belongs to” everywhere.

---

### Step 2 — Create the bare minimum API for the Project selector

Implement:
- `GET /api/projects`

Return a list like:

```json
[
  {"id": 12, "name": "Project Alpha", "procore_project_id": 12345},
  {"id": 13, "name": "Project Beta", "procore_project_id": 67890}
]
```

Where do projects come from initially?
- Manual seed is fine for V1 dev
- Later you’ll sync from Procore

**Goal of Step 2**: frontend can select a project and store `projectId`.

---

### Step 3 — Update Dashboard UI to select a project (even before new backend endpoints)

In `client/src/pages/dashboard.tsx`:
- Add `selectedProjectId` state
- Load projects list with React Query
- Render `ProjectSelector`
- Save selection (URL query param recommended: `?projectId=12`)

Don’t build the full dashboard yet—just get:
- selector renders
- selection persists

**Goal of Step 3**: dashboard is “project-scoped” structurally.

---

## Phase 2 — Dashboard sections wired to project-scoped endpoints*******************************************************************************************************************************

Now that `projectId` exists, implement each section one-by-one.

### Step 4 — Project summary endpoint + Top section

Backend:
- `GET /api/projects/{project_id}/dashboard/summary`

Return:
- project info
- basic KPIs (can be placeholders at first)

Frontend:
- Replace current global stats call with this new project-scoped call
- Render “Top: Project summary”

**Goal**: top section works with real data shape.

---

### Step 5 — Job queue endpoint + Middle section

Backend:
- `GET /api/projects/{project_id}/jobs?status=active`

Return jobs for that project.

Frontend:
- Build `JobQueueList` component
- Render “Middle: Active jobs + status”

**Goal**: you can see queued/running/failed jobs per project.

---

### Step 6 — Findings endpoint + Bottom section

Backend:
- `GET /api/projects/{project_id}/findings?limit=…`

Return recent findings.

Frontend:
- Build `RecentFindingsList` component
- Render “Bottom: Recent findings”
- Link to drawing workspace route stub

**Goal**: dashboard becomes usable.

---

## Phase 3 — Drawing workspace stub (so links have a home)

### Step 7 — Add a new route/page stub

Frontend:
- Add route like `/projects/:projectId/drawings/:drawingId` (or `/workspace`)
- Just show: drawing id, project id, “coming soon”

**Goal**: dashboard links are real; navigation works.

---

## Phase 4 — Evidence system for AI markup (documents)

This is where your non-drawing docs become useful.

### Step 8 — Add “EvidenceRecord” normalization table

Backend model:
- `EvidenceRecord` with fields: `id`, `project_id`, `type`, `title`, `status`, `source_id`, `text_content`, `dates`, `attachments_json`, `cross_refs_json`

Create just the table + minimal CRUD.

**Goal**: you have one shape for specs/submittals/RFIs/etc.

---

### Step 9 — Ingest one document type first (RFIs is best)

Build a single ingestion job:
- Pull RFIs from Procore (or seed local)
- Normalize into `EvidenceRecord(type="rfi")`

**Goal**: pipeline works end-to-end with one type.

---

### Step 10 — Linking logic (evidence → sheets)

Start simple:
- if RFI text contains “S-102” or “A201”, map to those sheets

Store mapping in:
- `EvidenceDrawingLink` table OR `cross_refs_json`

**Goal**: sheet-level retrieval becomes possible.

---

### Step 11 — Retrieval (RAG-style) for a sheet

When marking up a drawing sheet, query top `EvidenceRecords` by:
- matching discipline tags
- matching sheet references
- matching revision window

**Goal**: your AI receives the right context.

---

## Phase 5 — Logging + tests (after endpoints exist)

### Step 12 — Structured logs for job transitions + finding creation

Once models exist:
- log `project_id`, `job_id`, `status`
- log `finding_id`, `evidence_ids`

### Step 13 — Playwright tests

Add 3 tests:
- project selector changes data
- jobs render
- findings link navigates to workspace route