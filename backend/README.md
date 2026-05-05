# FastAPI Backend

This is the FastAPI backend for the QC/QA AI Platform.

## Python version

Use **Python 3.11 or 3.12** for local development (see repo root ``.python-version`` for pyenv). **Python 3.14** may hit TLS certificate verification failures when connecting to cloud Postgres (e.g. Render) from macOS; prefer 3.12 or set ``DATABASE_SSL_INSECURE_DEV=true`` with ``APP_ENV=development`` only (see ``.env.example``).

## Setup

1. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

2. **Set up environment variables:**
Create a `.env` file in the `backend/` directory (FastAPI loads this path when you run uvicorn from `backend/` or via `npm run dev`). Do **not** put `OPENAI_API_KEY` in the repo root `.env` (Vite / Node only).
```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/procore_int
PROCORE_CLIENT_ID=your_client_id
PROCORE_CLIENT_SECRET=your_client_secret
PROCORE_REDIRECT_URI=http://localhost:2000/api/procore/oauth/callback
OPENAI_API_KEY=your_openai_key
# Optional:
# OPENAI_CHAT_MODEL=gpt-4o-mini
```

**Local development:** use ``APP_ENV=development`` (default) so tools like ``scripts/seed_dev_data.py`` are allowed. Keep ``OPENAI_API_KEY`` only on the API host as needed.

**Inspections:** inspection runs (`/api/projects/.../inspections/runs`) call OpenAI when `OPENAI_API_KEY` is set. Without it, type/outcome fall back to heuristics and `"unknown"`. Confirm configuration with `GET /health` (`openai_configured`).

On **Render** (or any API host), add `OPENAI_API_KEY` in the service environment; redeploy if you add it after first deploy.

3. **Initialize database:**
```bash
python -c "from database import init_db; init_db()"
```

4. **Wipe all application data (keep schema & migrations):**

Run from the **backend app directory** (the folder that contains `main.py` and `scripts/`), so imports and optional `backend/.env` resolve correctly.

**Local (venv inside `backend/`):**
```bash
cd backend
./venv/bin/python scripts/reset_app_data.py          # confirm by typing RESET
./venv/bin/python scripts/reset_app_data.py --yes
./venv/bin/python scripts/reset_app_data.py --yes --clear-uploads
```

**Render shell (and many PaaS shells):** there is often **no** `.venv` under `backend/`. Use `python` on your `PATH` from the same directory Render uses for the API (commonly `~/project/src/backend` or similar—check with `pwd`).
```bash
pwd
ls -la
ls -la scripts
which python
python --version
python scripts/reset_app_data.py --yes
python scripts/reset_app_data.py --yes --clear-uploads
```
If `python` is missing, try `python3`. If the platform installs deps in a **repo-root** venv, use that interpreter explicitly, e.g.:
```text
/opt/render/project/src/.venv/bin/python scripts/reset_app_data.py --yes --clear-uploads
```
(Exact path can differ; `which python` on the Render shell is authoritative.)

On Render, `DATABASE_URL` is usually already in the **environment** for the shell; you do not need a local `.env` file if that is true.

Preserves the ``alembic_version`` row and all table definitions; only **rows** are removed. ``--clear-uploads`` only affects files under ``backend/uploads/`` on the machine running the script.

5. **Development — mock company + projects (dashboard / upload):**

The dashboard project selector and **Upload drawing** button need at least one row in ``projects``. Drawing uploads enqueue a **JobQueue** row with a ``user_id`` resolved from ``user_companies`` (or any ``users`` row). This seed adds company, **demo user** ``dev-seed@example.local``, membership, and two projects (idempotent).

```bash
cd backend
./venv/bin/python scripts/seed_dev_data.py --yes
```

Typical clean slate:

```bash
./venv/bin/python scripts/reset_app_data.py --yes --clear-uploads
./venv/bin/python scripts/seed_dev_data.py --yes
```

The script **refuses** when ``APP_ENV=production`` unless you pass ``--allow-production`` (avoid on real tenant data).

6. **Legacy full drop** (rarely needed): ``python scripts/reset_db.py --drop-schema`` then ``alembic upgrade head``.

## Running the Server

### Development mode:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 2000
```

### Production mode:
```bash
uvicorn main:app --host 0.0.0.0 --port 2000
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:2000/docs
- ReDoc: http://localhost:2000/redoc

## Project Structure

```
backend/
├── main.py              # FastAPI app entry point
├── config.py            # Configuration settings
├── database.py          # Database setup
├── api/
│   └── routes/         # API route handlers
├── models/
│   ├── database.py     # SQLAlchemy models
│   └── schemas.py      # Pydantic schemas
└── services/
    └── storage.py      # Data access layer
```

