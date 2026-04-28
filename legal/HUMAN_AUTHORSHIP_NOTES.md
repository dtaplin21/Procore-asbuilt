# Human authorship notes

**Product:** Procore-Integrator  
**Owning entity:** Grand Gaia LLC  

The following parts of the application were **designed, selected, arranged, reviewed, or modified** by **Dominique Taplin**, in coordination with Grand Gaia LLC’s direction. This supplements **`AI_DEVELOPMENT_RECORD.md`** (what tools produced drafts) and **`OWNERSHIP_RECORD.md`** (ownership and roles).

## Product direction

- Construction / QC–focused Procore integration  
- Master drawing and sub-drawing comparison workflow  
- Project-scoped dashboard concept  
- Inspection and evidence workflow  
- Beta testing and licensing strategy (including proprietary / all-rights-reserved posture documented under **`LICENSE`** and **`/legal`**)  

## Architecture

- **Backend:** FastAPI (Python), project-based API layout under `backend/api/`  
- **Database:** PostgreSQL  
- **ORM:** SQLAlchemy  
- **Migrations:** Alembic (`backend/alembic/`)  
- **Frontend:** React with TypeScript, Vite build (`client/`), shared types where applicable (`shared/`)  
- **Procore integration:** OAuth / connection handling and API usage patterns (see `ProcoreConnection` and related services)  
- **Async work:** Background jobs / worker patterns as implemented in `backend/services/`  

## Data model

Human-directed modeling and iteration over entities including, **without limitation**:

- Projects  
- Drawings (and renditions / processing state as modeled)  
- Drawing regions  
- Drawing alignments  
- Drawing diffs  
- Evidence records (and links to drawings where modeled)  
- Inspection runs  
- Inspection results  
- Drawing overlays  
- Procore connection records  

**Related areas** also shaped under the same oversight: findings, users/companies/tenancy as implemented, job queue, idempotency keys, Procore writeback, and other tables in `backend/models/models.py` as the product evolved.

## UI / UX

- Project dashboard layout and project context  
- Drawing upload workflow (including intent / master vs sub where implemented)  
- Master / sub drawing selection and drawing picker flows  
- Workspace comparison flow (sidebar, alignments, diff timeline, modals)  
- Alerts and warnings for sensitive behaviors (e.g. overwrite / workspace switch / upload intent)  
- Theming and primary workflow emphasis aligned to product branding (see client UI)  

## Implementation oversight

- Reviewed generated and third-party example code before reliance  
- Selected patterns consistent with FastAPI, SQLAlchemy, and React usage in this repo  
- Edited implementation details, APIs, and migrations  
- Tested endpoints and integration behavior  
- Debugged migrations and schema drift  
- Verified end-to-end app behavior for core workflows  

**Conclusion:** The application is **not** uncritical compilation of raw AI output; it reflects **human authorship and curation** in the areas above, in line with records in **`AI_DEVELOPMENT_RECORD.md`**.

## U.S. Copyright Office context (general)

U.S. copyright protection extends to **human-authored** expression. Where **AI-assisted** material is involved, the Copyright Office has issued guidance requiring **disclosure** of AI content and limiting registration of purely AI-generated portions; registrants typically identify **human-authored** contributions. Policies and forms change—verify **current** Circulars and registration practice before filing.

**For this project:** Grand Gaia LLC treats Dominique Taplin’s **direction, selection, arrangement, review, and integration** (documented here and in **`OWNERSHIP_RECORD.md`**) as central to the human-authored character of **Procore-Integrator**. Consult qualified counsel for registration strategy, disclaimers, and deposit requirements.

---

*Administrative notes only. Not legal advice.*
