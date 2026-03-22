## Goal

Deliver a **drawing workspace** that is the flagship experience of the product, where:

- A user selects or uploads a **sub drawing**.
- The system **compares it to a master drawing**, generates visual diffs, and traces those differences on the master sheet.
- The user can **return later** to see which sub drawings have been compared, what changed, and when, all within a single workspace UI.

The dashboard should act as an entry point into this workspace; the workspace itself is where users spend most of their time.

---

## Implementation Phases

### Phase 1 – Backend orchestration & API

**Objective:** Provide a single backend operation that performs “compare sub drawing to master” and returns a workspace‑ready response.

- **1.1 Orchestration service**
  - Implement a `drawing_comparison` service (e.g. `backend/services/drawing_comparison.py`) that:
    - Validates `project_id`, `master_drawing_id`, and `sub_drawing_id` all belong together.
    - Reuses or creates a `DrawingAlignment` for `(master_drawing_id, sub_drawing_id)`:
      - MVP behavior: `method="manual"`, neutral/identity `transform`, `status="complete"`.
    - Invokes `run_drawing_diff_for_alignment` to produce `DrawingDiff` rows.
    - Builds a workspace payload containing:
      - Master drawing summary.
      - Sub drawing summary.
      - Alignment summary.
      - One or more diff summaries (including `diff_regions`).

- **1.2 Compare endpoint**
  - Add `POST /api/projects/{project_id}/drawings/{master_drawing_id}/compare`:
    - Request body: `{ "sub_drawing_id": number }` (MVP assumes sub drawing already exists).
    - Behavior:
      - Calls the orchestration service’s `compare` method.
      - Maps the result to a Pydantic response model designed for the workspace.
    - Response:
      - `master_drawing`, `sub_drawing`, `alignment`, and `diffs` summaries.

- **1.3 Supporting queries**
  - Ensure existing endpoints support history/progress views:
    - `GET /api/projects/{project_id}/drawings/{master_drawing_id}/alignments`
      - Sorted by `created_at DESC`.
      - Includes sub drawing metadata (at least `id` and `name`).
    - `GET /api/projects/{project_id}/drawings/{master_drawing_id}/diffs?alignment_id=…`
      - Sorted by `created_at DESC`.
      - Includes `summary`, `severity`, `created_at`, and `diff_regions`.

**Done when:** A client can make one call to `/compare` and receive everything needed to render a comparison of a chosen sub drawing against a master drawing.

---

### Phase 2 – Workspace UI (read‑only + history)

**Objective:** Turn `DrawingWorkspacePage` into a real workspace that surfaces existing alignments and diffs for a master drawing.

- **2.1 Layout & state**
  - Replace the placeholder in `client/src/pages/drawing_workspace.tsx` with:
    - Center: drawing viewer for the **master** drawing.
    - Right sidebar:
      - Alignments list (sub drawings + status).
      - Diff timeline for the selected alignment.
  - Manage React state for:
    - `masterDrawing`, `alignments`, `selectedAlignmentId`.
    - `diffsByAlignmentId`, `selectedDiffId`.
    - Loading and error flags for network calls.

- **2.2 Data fetching**
  - On mount (given `projectId` and `drawingId`):
    - Fetch master drawing details.
    - Fetch alignments for the master drawing.
    - If any alignments exist:
      - Auto‑select the most recent alignment.
      - Fetch diffs for that alignment.

- **2.3 Rendering diffs**
  - Render the master drawing image from its `file_url`.
  - For the selected diff:
    - Render `diff_regions` as simple overlays:
      - Use normalized coordinates to position rectangles/polygons over the drawing.
      -add pan to zoom
      - make sure plan is production ready.

**Done when:** Navigating to `/projects/{projectId}/drawings/{drawingId}` shows the master drawing, existing alignments, and diff regions for at least one alignment.

---

### Phase 3 – “Compare a sub drawing” flow (end‑to‑end)

**Objective:** Allow a user to start a new comparison from the workspace with a single, prominent action.

- **3.1 Primary CTA in workspace**
  - Add a **“Compare a sub drawing”** button in the workspace sidebar.
  - Clicking it opens a modal or panel for selecting a sub drawing.

- **3.2 Sub drawing selection**
  - Inside the modal:
    - Show a list of candidate sub drawings (project drawings excluding the current master).
    - Support search/filter by name.
  - MVP assumption:
    - Sub drawing already exists (uploaded via existing flows).

- **3.3 Compare call & state update**
  - When the user selects a sub drawing:
    - Call `POST /api/projects/{projectId}/drawings/{drawingId}/compare` with `{ sub_drawing_id }`.
    - Show a progress indicator while the request is in flight.
  - On success:
    - Merge the returned alignment and diffs into workspace state:
      - Add/refresh the alignment in the list.
      - Store diffs under that alignment.
      - Auto‑select the new alignment and latest diff.
    - Update the canvas overlays to reflect the new diff.

**Done when:** A user can choose an existing sub drawing from the workspace and see the comparison result appear immediately in the alignment list, diff timeline, and on the drawing.

---

### Phase 4 – Deep‑linking & progress framing

**Objective:** Make the workspace the natural destination from dashboard/insights and clearly communicate comparison progress.

- **4.1 URL selection state**
  - Extend the workspace URL to accept:
    - `?alignmentId=…&diffId=…`.
  - On load:
    - If present, pre‑select the specified alignment and diff.
  - Optionally:
    - Keep the URL updated as the user changes selection so views can be shared/bookmarked.

- **4.2 Dashboard & insights integration**
  - For dashboard cards or insights tied to drawings/diffs:
    - Link into the workspace using:
      - `/projects/{projectId}/drawings/{masterDrawingId}?alignmentId=…&diffId=…`.
  - Ensure underlying records (diffs/findings) store the identifiers needed to construct this link.

- **4.3 Progress surface**
  - In the workspace sidebar and/or dashboard:
    - Surface counts like:
      - “X sub drawings compared to this master.”
      - “N open high‑severity diffs on this drawing.”

**Done when:** Users can arrive from dashboard/insights into a specific master/alignment/diff, and the workspace clearly shows comparison coverage and severity at a glance.

---

### Phase 5 – UX polish & AI‑forward enhancements

**Objective:** Turn a solid workflow into a differentiated AI‑first experience.

- **5.1 Visual sub overlay**
  - Extend the pipeline and renderer so the warped **sub drawing** itself can be drawn as a semi‑transparent overlay over the master (using `DrawingAlignment.transform`).

- **5.2 Smart suggestions**
  - When a new drawing is created (upload or sync):
    - Suggest likely master drawings to compare against (based on name, discipline, or Procore metadata).
  - Optionally auto‑populate the “Compare a sub drawing” modal with recommended pairs.

- **5.3 Metrics & storytelling**
  - Add headline metrics to the dashboard and workspace:
    - “X of Y relevant sub drawings have been compared for this project.”
    - “N unresolved high‑severity diffs across your active projects.”

**Done when:** The drawing workspace not only works end‑to‑end, but also clearly tells the story that “our AI continuously compares your drawings, highlights changes, and tracks progress over time” in a way that is obvious to the client.

## Drawing Workspace & Sub‑vs‑Master Diff Orchestration

### 1. Product Goal & Narrative

- **Headline feature**: A drawing workspace where users can:
  - Upload or select a **sub drawing** (detail, revision, or child sheet).
  - Have the AI **compare it to a master drawing**, align it, and generate visual diffs.
  - See the **sub drawing traced/overlaid** on the master, with differences highlighted.
  - Return later and see a **timeline of progress**: which subs have been compared, what changed, and when.

This document focuses on the **end‑to‑end orchestration** and **UI experience** that makes this feel like a single, polished workflow rather than a collection of low‑level APIs.

---

### 2. Current Building Blocks (As Implemented)

**Data model (backend/models/models.py)**

- `Drawing`
  - Represents both **master** and **sub** drawings.
  - Key fields: `id`, `project_id`, `name`, `source` (`upload` / `procore`), `storage_key`, `file_url`, `content_type`, `page_count`, `created_at`, `updated_at`.
  - Relationships:
    - `alignments_as_master` → list of `DrawingAlignment` where this drawing is the master.
    - `alignments_as_sub` → list of `DrawingAlignment` where this drawing is the sub.
    - `regions`, `inspection_runs`, `findings`, `overlays`.

- `DrawingRegion`
  - Optional region of interest on the **master** drawing (normalized geometry).
  - Used when we only want to compare a subset of the sheet.

- `DrawingAlignment`
  - Represents a **relationship between a master drawing and a sub drawing**.
  - Key fields: `master_drawing_id`, `sub_drawing_id`, `region_id`, `method`, `transform`, `status`, `error_message`, timestamps.
  - `transform` is a JSON blob containing the affine/homography matrix and any confidence metadata.
  - Relationships:
    - `master_drawing`, `sub_drawing`, `region`, `drawing_diffs`.

- `DrawingDiff`
  - Output of the **comparison between master and sub** for a specific alignment.
  - Key fields: `alignment_id`, `finding_id (optional)`, `summary`, `severity`, `diff_regions` (normalized 0‑1 geometry), `created_at`.
  - Relationships:
    - `alignment`, `finding`, `overlays`.

- `DrawingOverlay`
  - Generic overlay geometry tied to `master_drawing_id`, optionally linked to `inspection_run_id` or `diff_id`.
  - Can be used to store the **visual trace** of the sub‑vs‑master differences for efficient retrieval in the workspace.

**APIs**

- `backend/api/routes/drawing_alignment.py`
  - `POST /api/projects/{project_id}/drawings/{master_drawing_id}/alignments`
    - Creates a `DrawingAlignment` (master ↔ sub, method, optional region).
  - `GET /api/projects/{project_id}/drawings/{master_drawing_id}/alignments`
    - Lists alignments for a master drawing (used for “progress” sidebar).
  - `PATCH /api/projects/{project_id}/drawings/{master_drawing_id}/alignments/{alignment_id}`
    - Updates `status`, `transform`, `error_message`.

- `backend/api/routes/drawing_diffs.py`
  - `GET /api/projects/{project_id}/drawings/{master_drawing_id}/diffs`
  - `POST /api/projects/{project_id}/drawings/{master_drawing_id}/diffs/run`
  - `GET /api/projects/{project_id}/drawings/{master_drawing_id}/diffs/{diff_id}`

- `backend/ai/pipelines/drawing_diff.py`
  - `run_drawing_diff_for_alignment(db, alignment, severity_threshold="high")`
  - Handles:
    - Resolving master/sub file paths.
    - Warping sub into master frame using `alignment.transform`.
    - Running vision/AI model.
    - Creating `DrawingDiff` rows (and optionally `Finding` + `DrawingOverlay`).

- `client/src/pages/drawing_workspace.tsx`
  - Currently a **placeholder** that shows project/drawing IDs but no real viewer.

---

### 3. Target End‑to‑End Workflow (User‑First View)

From the user’s perspective, the “headline” flow should look like this:

1. **Open Drawing Workspace**
   - Route: `/projects/{projectId}/drawings/{drawingId}` (master drawing).
   - UI shows:
     - Large **canvas** for the master drawing.
     - Right/left **panel** with:
       - Existing **alignments** and their statuses.
       - Existing **diff runs** (with severity, summary, created_at).
       - A primary **Call to Action**: “Compare a sub drawing”.

2. **Choose or upload a sub drawing**
   - Options:
     - **Pick an existing drawing** (from project’s drawings list).
     - Or **Upload a new sub drawing** (PDF/image).
   - After the user selects a file or drawing:
     - Backend ensures we have a `Drawing` row for the sub (create if upload).

3. **Align sub to master**
   - Phase 1 (MVP): **manual alignment**:
     - User clicks “Create alignment”.
     - Backend immediately creates `DrawingAlignment` with:
       - `method="manual"`, identity `transform`, `status="complete"`.
     - Front‑end can later support manual transform editing UI if needed.
   - Phase 2+: AI‑assisted alignment:
     - `method="vision"` or `"feature_match"`, alignment pipeline computes transform and updates `DrawingAlignment.transform` + `status`.

4. **Run diff**
   - UI button in alignment list: “Run comparison”.
   - Calls `POST /diffs/run` for the chosen `alignment_id`.
   - Backend:
     - Runs `run_drawing_diff_for_alignment`.
     - Creates `DrawingDiff` rows (each with `diff_regions`).
     - Optionally creates `DrawingOverlay` geometry for rendering.

5. **View and revisit results**
   - Canvas overlays:
     - Render `diff_regions`(or `DrawingOverlay`) as highlighted polygons/rectangles on the master drawing.
     - Optional: toggle “show sub outline / hide sub outline”.
   - Progress panel:
     - Shows **timeline** of diff runs (by `created_at`) and severity.
     - Clicking an entry focuses that diff’s regions on the canvas.
   - Because everything is persisted (`DrawingAlignment`, `DrawingDiff`, `DrawingOverlay`), the user can return later and see:
     - Which subs were compared.
     - When.
     - What was flagged.

This entire experience should be driven from a **single workspace UI**, rather than separate screens.

---

### 4. Orchestration Layer: Proposed `evidence_retrieval`‑style Service for Drawings

We already have a pattern for encapsulating non‑trivial logic in services (e.g., `rfi_ingestion`, `evidence_linking`). For the sub‑vs‑master drawing experience, we should introduce a **drawing comparison orchestration service**, e.g.:

- `backend/services/drawing_comparison.py` (name tbd; avoid editing in this document, this is architectural intent).

**Responsibilities:**

1. **Sub drawing onboarding**
   - Given `project_id` and either:
     - An existing `drawing_id` (sub), or
     - An upload (handled via existing drawing upload route), this service:
       - Ensures a `Drawing` row exists for the sub.
       - Returns the `Drawing` instance for downstream steps.

2. **Alignment management**
   - Given `master_drawing_id` and `sub_drawing_id`:
     - Create a `DrawingAlignment` (if none exists) with `method="manual"` and:
       - Identity `transform` as a minimum.
       - `status="complete"` for MVP so the diff can run immediately.
     - Optionally support:
       - Reusing existing alignment if an identical pair already exists.
       - Updating alignment method/transform when AI alignment is added.

3. **Diff execution**
   - Given an `alignment_id`, call into the AI pipeline:
     - `run_drawing_diff_for_alignment(db, alignment, severity_threshold="high")`.
   - Store and/or update:
     - `DrawingDiff` rows.
     - `DrawingOverlay` rows (for fast rendering).

4. **Workspace‑ready response shape**
   - Return a **single structured response** to the front‑end, e.g.:
     - `master_drawing` metadata.
     - `sub_drawing` metadata.
     - `alignment` (status, method, created_at, transform).
     - The **latest `DrawingDiff`** (or all diffs) with:
       - `summary`, `severity`, `created_at`, `diff_regions`.
       - Pre‑translated overlay geometry (if any).

This orchestration service gives the UI **one call** to perform “upload/choose sub → align → diff → return everything needed to paint the screen”.

---

### 5. Drawing Workspace UI Plan (Headline Feature)

We should treat the **drawing workspace** as the primary UI surface of the product. The dashboard should funnel users into here when they click any drawing‑related insight or diff.

#### 5.1 Layout

- **Main canvas (center)**
  - Renders master drawing at interactive zoom/pan.
  - Overlays:
    - `DrawingOverlay` geometry (if present).
    - `DrawingDiff.diff_regions` as clickable/highlighted regions.

- **Right sidebar**
  - Sections:
    - **Sub drawings & alignments**
      - List of alignments for this master:
        - `sub_drawing_name`
        - method (manual/vision)
        - status (queued/processing/complete/failed)
        - created_at
      - Primary button: **“Compare a sub drawing”**.
    - **Diff timeline**
      - For the selected alignment:
        - List of `DrawingDiff` entries with summary, severity, created_at.
        - Clicking a diff:
          - Focuses its regions on the canvas.

- **Top toolbar**
  - Controls:
    - Zoom in/out, fit to screen.
    - Toggle overlays (on/off).
    - Toggle “sub outline” (if we render warped sub as a semi‑transparent overlay).

#### 5.2 Core Interactions

1. **Compare a sub drawing**
   - Button opens a modal:
     - Tab 1: “Choose existing sub drawing” → list of `Drawing` records in the project other than the master.
     - Tab 2: “Upload new sub drawing” → uses existing upload endpoint, then refreshes the list.
   - Once selected:
     - Front‑end POSTs to orchestration endpoint (e.g. `/api/projects/{project_id}/drawings/{master_drawing_id}/compare`).
     - That endpoint:
       - Ensures a `Drawing` for the sub.
       - Creates alignment (if missing).
       - Runs diff.
       - Returns workspace payload.
   - UI shows:
     - Progress spinner while diff is running.
     - Then updates:
       - Alignments list → new row.
       - Diff timeline → new diff entry at top.
       - Canvas → new highlights.

2. **Re‑run diff for existing alignment**
   - Each alignment row has an overflow menu:
     - “Re‑run comparison”.
   - Calls `POST /diffs/run` and refreshes diff list for that alignment.

3. **View specific diff**
   - Clicking a diff entry in the timeline:
     - Loads that `DrawingDiff` (if not already) from `/diffs/{diff_id}`.
     - Updates overlays/regions on the canvas to show only that diff.

4. **Navigate from dashboard/insights**
   - Dashboard can link directly into:
     - `/projects/{projectId}/drawings/{drawingId}` (master).
     - Optionally include query params for:
       - `?alignmentId=...&diffId=...` to auto‑select an alignment/diff when opening workspace.

---

### 6. Implementation Phases

#### Phase 1 – Backend Orchestration Endpoint

**Goal**: A single backend endpoint that the UI can call to “compare a sub to this master and give me everything I need to render the workspace state”.

High‑level steps:

1. **Define orchestration service** (drawing comparison service as described above).
2. **Add API endpoint** (example shape):
   - `POST /api/projects/{project_id}/drawings/{master_drawing_id}/compare`
   - Body:
     - Either `sub_drawing_id` **or** upload context (if we decide to drive upload from here).
   - Response:
     - `alignment` + `latest_diff` + overlays + minimal `Drawing` metadata.
3. **Reuse existing lower‑level pieces**:
   - `Drawing` upload/list endpoints (no duplication).
   - `create_drawing_alignment` & `run_drawing_diff_for_alignment`.
   - `DrawingOverlay` creation if applicable.

#### Phase 2 – Workspace UI v1 (Read‑only + basic actions)

**Goal**: Make the workspace feel like the center of gravity and expose progress.

1. **Upgrade `DrawingWorkspacePage`**:
   - Replace placeholder with:
     - Viewer for master drawing.
     - Sidebar listing alignments and diffs (using existing endpoints).
2. **Wire alignment/diff fetching**:
   - Use:
     - `GET /drawings/{master_drawing_id}/alignments`
     - `GET /drawings/{master_drawing_id}/diffs`
3. **Render basic overlays**:
   - For each `DrawingDiff`, render `diff_regions` with simple highlight shapes (rectangles/polygons) using normalized geometry.

At this point, the workspace shows what’s been run, but might still require separate steps to create alignments/diffs.

#### Phase 3 – Integrated “Compare Sub Drawing” Flow

**Goal**: Click a single button, choose a sub drawing, and see the comparison result appear in the workspace.

1. **Add “Compare a sub drawing” modal**:
   - Pull list of candidate sub drawings.
   - Simple search/filter by name.
2. **Call orchestration endpoint**:
   - On confirm, call the combined “compare” API (Phase 1).
   - Show progress and update UI with new alignment/diff.
3. **Handle errors gracefully**:
   - Alignment/diff pipeline failures surface as user‑friendly messages in the sidebar.

#### Phase 4 – UX Polish and AI‑Forward Experience

**Ideas (post‑MVP, but aligned with headline positioning):**

- **Automatic suggestions**:
  - When a new drawing is uploaded, suggest likely master drawings to compare to (based on name similarity or Procore metadata).
- **Visual sub overlay**:
  - Render the warped sub drawing itself as a semi‑transparent layer over the master using `alignment.transform`.
- **Progress metrics**:
  - In sidebar and dashboard:
    - “X of Y sub drawings compared”.
    - “N high‑severity diffs outstanding”.

---

### 7. How This Becomes the Headline Feature

- The **dashboard** should pivot users into the drawing workspace whenever they click on:
  - A finding tied to a `DrawingDiff`.
  - A notification about “new diff detected on drawing X”.
- The **workspace** itself is where users:
  - Understand the state of a project’s drawings (what’s been compared, what changed).
  - Interact with AI‑generated overlays and findings.
- By putting this orchestration/UX front and center, the product’s story becomes:
  > “Our AI continuously compares new and revised drawings to your master sheets, highlights changes visually, and lets you track progress over time in a dedicated drawing workspace.”

This document should be treated as the **source of truth** for how we wire together existing models, services, and APIs to deliver that experience, and as the reference when making trade‑offs in implementation details.

