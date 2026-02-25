---
name: Procore token DB persistence
overview: "Persist Procore OAuth tokens in Postgres using `procore_connections` (Approach B: per company + Procore user) with scopes + uniqueness, replacing the current in-memory token store so connections survive restarts."
todos:
  - id: notes-outline
    content: Write `Notes/technical-implementation/procore_token_persistence.md` outline for Approach B (schema, flow, endpoints, verification).
    status: pending
  - id: db-migration
    content: Add ProcoreConnection columns (scope/token_type) + unique constraint (company_id, procore_user_id) via Alembic.
    status: pending
  - id: db-store-layer
    content: Implement DB-backed Procore connection store helpers and remove reliance on in-memory `procore_token_store`.
    status: pending
  - id: oauth-flow-update
    content: Update OAuth callback + refresh logic to persist tokens in `procore_connections` and activate a selected company context.
    status: pending
  - id: client-update
    content: Update Procore API client to load/refresh tokens from DB and set Procore-Company-Id based on active connection/company selection.
    status: pending
  - id: frontend-company-select
    content: Add company selection wiring to set active company and make Sync Projects use that context.
    status: pending
  - id: verify
    content: "Manual verification: restart persistence, refresh flow, company switching, project sync upsert."
    status: pending
isProject: false
---

## Context (current state)

- Tokens are currently stored in-memory in `backend/services/procore_token_store.py` (lost on restart).
- OAuth + Procore API client read tokens from that in-memory store:
  - `backend/services/procore_oauth.py`
  - `backend/services/procore_client.py`
- DB model already exists: `ProcoreConnection` in `backend/models/models.py` with `company_id`, `access_token`, `refresh_token`, `token_expires_at`, `procore_user_id`, `is_active`.
- Alembic is present and already used (`backend/alembic/versions/*.py`).

## Decision locked in

- Use **Approach B**: persist tokens per **(company_id, procore_user_id)**.
- Add **unique constraints** and store **scopes**.
- Company selection: user selects which company context to use (we’ll default to the first company on connect, then allow switching).

## Deliverable doc

Create a new implementation outline doc at `Notes/technical-implementation/procore_token_persistence.md` containing:

- Goals
- Data model changes
- Migration steps
- Updated OAuth flow
- Updated API client token retrieval/refresh
- Frontend company selection + sync flow
- Test/verification checklist

## Data model + migration (Alembic)

Update `backend/models/models.py` (`ProcoreConnection`):

- Add columns:
  - `token_type` (string, default "Bearer")
  - `scope` (text/string; store raw scope string from Procore)
  - Optional but recommended: `revoked_at` (datetime nullable) or `disconnected_at` for audit
- Add **Uniqueness**:
  - `UniqueConstraint('company_id','procore_user_id', name='uq_procore_connections_company_user')`
  - Ensure `procore_user_id` is indexed (and consider making it non-null once flow stores after `/me`).
- Optional (recommended): enforce only one “active company context” per Procore user:
  - Postgres partial unique index on `procore_user_id` where `is_active=true` (so switching company is safe).

Create an Alembic revision that:

- Adds the new columns
- Adds the unique constraint
- Adds indexes / partial unique index (if chosen)

## Replace in-memory store with DB store

Create a small DB-backed store module (new file), e.g. `backend/services/procore_connection_store.py`, providing:

- `get_active_connection(db, procore_user_id) -> ProcoreConnection | None`
- `get_connection(db, company_id, procore_user_id) -> ProcoreConnection | None`
- `upsert_connection(db, company_id, procore_user_id, access_token, refresh_token, token_expires_at, token_type, scope) -> ProcoreConnection`
- `set_active_company(db, procore_user_id, company_id)` (sets others inactive)
- `delete_connection(db, procore_user_id, company_id)`

Then update callers:

- `backend/services/procore_oauth.py`
  - `exchange_code_for_tokens()` should **return token payload** (don’t store in-memory).
  - After calling `/me` and `/companies`, persist to `procore_connections` via the DB store.
  - `refresh_token()` should refresh and **persist updated tokens** into the correct `procore_connections` row.
- `backend/services/procore_client.py`
  - Replace `get_token(self.user_id)` usage with DB lookup:
    - Find active connection for the Procore user.
    - Use the connection’s tokens; refresh if expiring.
  - Derive `Procore-Company-Id` header from the selected active company:
    - Either store Procore company id on `companies.procore_company_id` and join, or store it redundantly on `procore_connections`.

## Update Procore auth/routes to support company selection

Update `backend/api/routes/procore_auth.py`:

- On OAuth callback:
  - Exchange code → access token
  - Call `/me` to get `procore_user_id`
  - Call `/companies` to get accessible companies
  - Ensure local `companies` rows exist for those (store `procore_company_id`)
  - Choose a default active company (first company) and persist the `procore_connections` row for it
  - Redirect to frontend including `user_id=<procore_user_id>` (as today) and optionally `company_id=<internal_company_id>`
- Add an endpoint to switch active company context (company selector support), e.g.:
  - `POST /api/procore/company/select?user_id=<procore_user_id>&company_id=<internal_company_id>`
  - Implementation: mark previous `procore_connections` inactive; upsert/activate the selected one.

## Frontend wiring (minimal)

- After connect, fetch companies (already possible via `GET /api/procore/companies?user_id=...`).
- Add a simple company selector (likely in Settings), calling the new “select company” endpoint.
- Sync Projects button uses the active company context to pull projects and upsert into `projects`.

## Verification checklist

- Restart backend → connection status remains connected (tokens in DB).
- `GET /api/procore/status?user_id=...` uses DB store, not in-memory.
- Token refresh updates DB row and subsequent requests use new `access_token`.
- Switching company changes `Procore-Company-Id` and projects list changes accordingly.
- Alembic migration applies cleanly on a fresh DB and an existing dev DB.

