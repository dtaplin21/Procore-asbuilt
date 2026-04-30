# Local Postgres → Render Postgres (schema + data)

This document matches the automation in [`backend/scripts/dump_restore_render_postgres.sh`](../../backend/scripts/dump_restore_render_postgres.sh).

## What runs in the repo (no secrets)

- **Script:** `backend/scripts/dump_restore_render_postgres.sh` — `pg_dump` (custom format) then `pg_restore` with `--no-owner --no-acl`. Applies libpq SSL mitigations for Render external URLs.
- **Script:** `backend/scripts/psql_render_external.sh` — `psql` against `RENDER_EXTERNAL_DATABASE_URL` with the same SSL behavior (use instead of bare `psql` when you hit certificate verify errors).
- **App driver:** `DATABASE_URL` for **FastAPI/SQLAlchemy** should ultimately use **psycopg v3** (`postgresql+psycopg://…`). Plain `postgres://` or `postgresql://` from Render is rewritten in [`backend/config.py`](../../backend/config.py).

## Automated usage (your machine, after you set env vars)

Requires local **PostgreSQL client tools** (`pg_dump`, `pg_restore`).

From the **repository root** (temporary exports only — do not commit real URLs):

```bash
export SOURCE_DATABASE_URL='postgresql+psycopg://USER:PASS@localhost:5432/procore_int'
export RENDER_EXTERNAL_DATABASE_URL='postgres://USER:PASS@HOST:5432/DB?sslmode=require'
bash backend/scripts/dump_restore_render_postgres.sh
```

- **SOURCE:** your local DB (any of `postgresql+psycopg://`, `postgresql://`, `postgres://` is fine; the script normalizes for libpq).
- **RENDER_EXTERNAL_DATABASE_URL:** Render **External** Database URL when running from your laptop; include `sslmode=require` if Render requires SSL. (Legacy: `TARGET_DATABASE_URL` is still accepted if the new variable is unset.)

---

## Manual steps only you can perform

1. **Ensure Render PostgreSQL exists** and you have **External** and **Internal** connection strings.
2. **Install** `pg_dump` / `pg_restore` locally (e.g. `brew install libpq` and add to `PATH`, or Postgres.app).
3. **Set** `SOURCE_DATABASE_URL` and `RENDER_EXTERNAL_DATABASE_URL` with **real credentials** (do not commit them).
4. **Run** the script above (or equivalent manual `pg_dump` / `pg_restore` commands).
5. **Verify** on Render: `psql` with external URL → `\dt` and spot-check row counts.
6. **Render Web Service → Environment:** set **`DATABASE_URL`** to the **Internal** Database URL (Render rewrites `postgres://` → `postgresql+psycopg://` at app startup via `config.py`).
7. **Redeploy** the Web Service after changing env vars.

## Troubleshooting: `SSL error: certificate verify failed` (psql / libpq)

### What the repo fixes automatically

[`backend/scripts/dump_restore_render_postgres.sh`](../../backend/scripts/dump_restore_render_postgres.sh) and [`backend/scripts/psql_render_external.sh`](../../backend/scripts/psql_render_external.sh) (for a quick `psql` session):

- **Unsets** `PGSSLROOTCERT`, `PGSSLCERT`, `PGSSLKEY`, `PGSSLCRL` for that process only so local CA paths do not force verification against the wrong chain.
- **Sets** `PGSSLMODE=require` (encrypt; do not require server cert verification the way `verify-full` does).
- **Normalizes the Render URL:** rewrites `sslmode=verify-full` / `verify-ca` to `require`, and appends `sslmode=require` if missing.

Prefer the psql wrapper so you do not rely on a bare `psql "$RENDER_EXTERNAL_DATABASE_URL"` inheriting a strict shell environment:

```bash
export RENDER_EXTERNAL_DATABASE_URL='postgres://...'
bash backend/scripts/psql_render_external.sh
bash backend/scripts/psql_render_external.sh -c '\dt'
```

### If problems persist (manual)

Even with `sslmode=require`, a broken `~/.postgresql/root.crt` can still affect some libpq builds. Use the steps below only if the scripts above still fail.

#### Step 1 — SSL-related environment variables (outside the helper scripts)

```bash
env | grep PGSSL
```

If you see values such as `PGSSLMODE=verify-full` or `PGSSLROOTCERT=...`, clear them for this session:

```bash
unset PGSSLMODE
unset PGSSLROOTCERT
```

Then retry the **wrapper** script, not a long-lived shell with old exports.

#### Step 2 — Local Postgres cert file (`~/.postgresql/root.crt`)

```bash
ls -la ~/.postgresql
```

If `root.crt` exists and is stale or not the CA Render expects, temporarily bypass it:

```bash
mv ~/.postgresql/root.crt ~/.postgresql/root.crt.bak
```

Retry `psql_render_external.sh`. Restore when finished if other local workflows need it:

```bash
mv ~/.postgresql/root.crt.bak ~/.postgresql/root.crt
```

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
