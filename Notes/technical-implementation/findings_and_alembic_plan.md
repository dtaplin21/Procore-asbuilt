## Plan: Findings table + Alembic migrations

This plan locks in the next implementation slice:
- **DB model uses table name `findings`**
- API/UI can continue using the word **“insights”** (`/api/insights`)
- Add **Alembic** so schema changes are applied via migrations instead of `create_all()`

---

## Goals (MVP of the MVP)

1) Persist project-scoped AI insights as durable records (**findings**) in Postgres.
2) Support:
   - `GET /api/insights?project_id=<id>&limit=4`
   - `PATCH /api/insights/{id}/resolve`
3) Dashboard uses `selectedProjectId` to fetch project-scoped insights.
4) Schema changes happen via **Alembic**.

---

## Data model (DB = `findings`)

### Table: `findings`

Minimum fields:
- `id` (UUID string / text primary key)
- `project_id` (FK → `projects.id`, integer)
- `type` (text)
- `severity` (text)
- `title` (text)
- `description` (text)
- `affected_items` (JSON array, default `[]`)
- `resolved` (bool, default `false`)
- `created_at` (timestamp, default now)

Optional fields now (future-proofing):
- `related_submittal_id`, `related_rfi_id`, `related_inspection_id` (nullable text)
- `evidence` (nullable JSON) — list of evidence links `{ kind, id?, url?, excerpt? }`

---

## Implementation steps

### Step 1 — Add Alembic to backend dependencies
- Add `alembic` to `backend/requirements.txt` (Done)

### Step 2 — Initialize Alembic in `backend/`
Create:
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/script.py.mako`
- `backend/alembic/versions/` directory (Done)

Configure `env.py` so:
- DB URL comes from `config.settings.database_url`
- `target_metadata = Base.metadata` where `Base` is from `models.models`

### Step 3 — Create the `findings` ORM model
In `backend/models/models.py`:
- Add `Finding` (or `FindingRecord`) with `__tablename__ = "findings"`
- Add `project_id` FK relationship to `Project` (Done)

### Step 4 — Create the initial Alembic migration
- Generate a migration that creates the `findings` table and any missing columns/FKs.
- Apply it with `alembic upgrade head`. (done)

### Step 5 — Replace storage stubs for insights
In `backend/services/storage.py`:
- `get_insights(project_id, limit)` queries `findings`
- `resolve_insight(insight_id)` updates `resolved=True`

In `backend/api/routes/insights.py`:
- ensure `project_id` is accepted as an **int** (query param)
- keep the route path `/api/insights`

### Step 6 — Seed 1–2 findings (dev)
Pick one:
- one-time seed script `backend/scripts/seed_findings.py`, or
- manual SQL insert in `psql`

### Step 7 — Wire dashboard query to project scope
In `client/src/pages/dashboard.tsx`:
- Change insights query to: `/api/insights?project_id=<selectedProjectId>&limit=4`
- Use a query key that includes project scope to avoid cache mixing.

### Step 8 — Wire resolve button
UI:
- call `PATCH /api/insights/{id}/resolve`
- invalidate project-scoped insights query key

---

## Commands (developer workflow)

From repo root:

```bash
source backend/venv/bin/activate
pip install -r backend/requirements.txt

# Create/apply migrations
cd backend
alembic upgrade head
```

Verify in psql (connect to your `DATABASE_URL` DB):

```sql
\\dt
\\d findings
```

---

## Notes / guardrails

- `Base.metadata.create_all()` does **not** alter existing tables. Alembic is the correct tool for incremental schema changes.
- Keep “findings” as the DB term; keep “insights” as the UI/API term.

