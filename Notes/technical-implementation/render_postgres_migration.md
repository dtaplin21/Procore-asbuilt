# Local Postgres → Render Postgres (schema + data)

This document matches the automation in [`backend/scripts/dump_restore_render_postgres.sh`](../../backend/scripts/dump_restore_render_postgres.sh).

## What runs in the repo (no secrets)

- **Script:** `backend/scripts/dump_restore_render_postgres.sh` — `pg_dump` (custom format) then `pg_restore` with `--no-owner --no-acl`.
- **App driver:** `DATABASE_URL` for **FastAPI/SQLAlchemy** should ultimately use **psycopg v3** (`postgresql+psycopg://…`). Plain `postgres://` or `postgresql://` from Render is rewritten in [`backend/config.py`](../../backend/config.py).

## Automated usage (your machine, after you set env vars)

Requires local **PostgreSQL client tools** (`pg_dump`, `pg_restore`).

From the **repository root**:

```bash
export SOURCE_DATABASE_URL='postgresql+psycopg://USER:PASS@localhost:5432/procore_int'
export TARGET_DATABASE_URL='postgres://USER:PASS@HOST:5432/DB?sslmode=require'
bash backend/scripts/dump_restore_render_postgres.sh
```

- **SOURCE:** your local DB (any of `postgresql+psycopg://`, `postgresql://`, `postgres://` is fine; the script normalizes for libpq).
- **TARGET:** Render **External** Database URL when running from your laptop; include `sslmode=require` if Render requires SSL.

---

## Manual steps only you can perform

1. **Ensure Render PostgreSQL exists** and you have **External** and **Internal** connection strings.
2. **Install** `pg_dump` / `pg_restore` locally (e.g. `brew install libpq` and add to `PATH`, or Postgres.app).
3. **Set** `SOURCE_DATABASE_URL` and `TARGET_DATABASE_URL` with **real credentials** (do not commit them).
4. **Run** the script above (or equivalent manual `pg_dump` / `pg_restore` commands).
5. **Verify** on Render: `psql` with external URL → `\dt` and spot-check row counts.
6. **Render Web Service → Environment:** set **`DATABASE_URL`** to the **Internal** Database URL (Render rewrites `postgres://` → `postgresql+psycopg://` at app startup via `config.py`).
7. **Redeploy** the Web Service after changing env vars.

## Schema only (no row copy)

If you only need empty tables aligned with migrations:

```bash
cd backend
# DATABASE_URL pointing at Render (postgresql+psycopg://…)
./venv/bin/alembic upgrade head
```

That does **not** copy data — use the shell script for a full copy.

## Re-run / wipe target

For a **fresh** empty Render DB, one restore is enough. To replace everything on a non-empty DB, use a new Render database or `pg_restore --clean --if-exists` (destructive; use only on disposable data).
