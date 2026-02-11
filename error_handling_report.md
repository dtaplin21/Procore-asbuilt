# Error Handling Review

Grades reflect how closely each file follows common error-handling practices (explicit failure detection, user-friendly messaging, observability, and graceful recovery).

- **A** – Defensive or no runtime risk (e.g., pure UI/render-only components)
- **B** – Basic handling present but could be more robust (e.g., logs missing, limited context)
- **C** – Minimal handling; important cases unhandled or swallowed
- **D** – Poor handling that will frequently mask bugs or crash the app
- **F** – No handling where failures are guaranteed
- **N/A** – Documentation/config with no executable logic

## Backend (FastAPI / Python)
| File | Grade | Notes |
| --- | --- | --- |
| backend/__init__.py | A | Package marker only. |
| backend/ai/__init__.py, backend/ai/agents/__init__.py | A | No logic yet. |
| backend/api/__init__.py, backend/api/routes/__init__.py | A | Import glue only. |
| backend/api/dependencies.py | C | Relies on FastAPI dependency injection but adds no validation/logging around DB acquisition; DB failures bubble without context. |
| backend/api/routes/dashboard.py | C | Single try/except raising 500 with raw message; no logging/metrics and uses bare Exception. |
| backend/api/routes/projects.py | C | Similar pattern; only 404 path is explicit while other DB errors are wrapped generically. |
| backend/api/routes/submittals.py | C | Same as above plus blindly trusts body for updates without validation or partial-failure handling. |
| backend/api/routes/rfis.py | C | Same deficits as other CRUD routes. |
| backend/api/routes/inspections.py | C | Same deficits as other CRUD routes. |
| backend/api/routes/objects.py | C | Same as others; doesn’t distinguish DB-not-ready vs real 500. |
| backend/api/routes/insights.py | C | Bare except; resolve endpoint has no optimistic concurrency/row-lock handling. |
| backend/api/routes/procore.py | D | Sync endpoint wraps everything in one blanket `except`, so token refresh/resource errors have no actionable context and 404 for missing token duplicates logic elsewhere. |
| backend/api/routes/procore_auth.py | C | Handles OAuth happy path but any failure surfaces only as HTTPException(500) with raw string, no audit/log; refresh path doesn’t catch httpx errors separately. |
| backend/config.py | C | Instantiates Settings eagerly without guarding missing env vars; misconfig raises at import time and is hard to trace. |
| backend/database.py | C | Opening engine/session lacks retries or diagnostics; init_db doesn’t catch/propagate migration failures meaning server crashes during startup. |
| backend/main.py | B | FastAPI startup hook calls init_db without guard/logging, but rest of file is framework wiring. |
| backend/models/__init__.py, backend/models/database.py, backend/models/schemas.py | B | Pure schema definitions; validation is left to Pydantic/SQLAlchemy defaults (no custom validators). |
| backend/services/__init__.py | A | Re-export only. |
| backend/services/procore_client.py | D | Every network call assumes success; missing rate-limit/backoff, no logging, `_get_company_id` assumes token exists, `_request` doesn’t catch `httpx.HTTPStatusError` to reclassify errors, so callers always see generic HTTPException. |
| backend/services/procore_oauth.py | D | Assumes OAuth endpoints always succeed; missing timeout handling, CSRF/state expiry, and commits even when user sync fails. Errors propagate as bare exceptions so routes can’t distinguish invalid code vs network failure. |
| backend/services/storage.py | D | Database writes never wrap commits in try/except or roll back on failure, so half-written state is possible; no handling for concurrent updates or invalid inputs. |
| backend/run.sh | C | Shell script doesn’t set `set -euo pipefail`; install/server steps continue after partial failure. |
| backend/README.md, backend/PROCORE_AUTH_SETUP.md | N/A | Documentation only. |
| backend/requirements.txt | N/A | Dependency list. |

## Node/Express Server
| File | Grade | Notes |
| --- | --- | --- |
| server/index.ts | D | Global error middleware rethrows errors after sending the response which will crash the process; no structured logging for exceptions or startup failures. |
| server/routes.ts | C | Each route wraps handler with try/catch returning 500 but provides no detail/logging; repeated logic for parsing query params risks inconsistent handling. |
| server/storage.ts | C | In-memory storage does not validate inputs or guard against missing records beyond returning undefined; callers must handle errors themselves. |
| server/static.ts | B | Explicitly throws descriptive error when dist missing but lacks fallback/health logging. |
| server/vite.ts | B | HMR middleware at least forwards errors to Express; only improvement would be more graceful handling instead of `process.exit` on logger.error. |

## Client (React/Vite)
| File | Grade | Notes |
| --- | --- | --- |
| client/index.html | A | Static shell only. |
| client/src/main.tsx | C | No React error boundary—any render error crashes entire app. |
| client/src/App.tsx | C | Router lacks fallback/loading/error boundaries and Procore sync simulation doesn’t catch API errors. |
| client/src/index.css | A | Styling only. |
| client/src/lib/queryClient.ts | B | Provides shared error raising via `throwIfResNotOk` and handles 401 flows, but there’s no retry/backoff strategy or error-to-toast mapping. |
| client/src/lib/utils.ts | A | Utility merge helper only. |
| client/src/pages/dashboard.tsx | D | React Query errors are ignored; when the request fails UI renders blank cards with no message. |
| client/src/pages/inspections.tsx | D | Same issue—`isError` never checked, and Dialog close swallows fetch errors silently. |
| client/src/pages/objects.tsx | D | No error state for data fetch; filteredObjects undefined results in empty screen with no feedback. |
| client/src/pages/settings.tsx | B | Local state only, but disconnect/connect callbacks don’t surface failures. |
| client/src/pages/not-found.tsx | A | Static fallback page. |
| client/src/components/app-sidebar.tsx | B | Navigational component; lacks error boundary for failed route transitions but otherwise UI-only. |
| client/src/components/procore-status.tsx | B | Displays errorMessage when provided but doesn’t surface sync API failures or add retry/backoff. |
| client/src/components/stat-card.tsx | A | Presentational only. |
| client/src/components/ai-insight-card.tsx | A | Presentational only. |
| client/src/components/ai-score-ring.tsx | A | Pure rendering. |
| client/src/components/status-badge.tsx | A | Pure rendering. |
| client/src/components/theme-provider.tsx | C | Forces dark theme without guarding against SSR/window undefined; missing try/catch around DOM access. |
| client/src/components/theme-toggle.tsx | A | No logic. |
| client/src/components/ui/* (accordion.tsx, alert*.tsx, avatar.tsx, ... , tooltip.tsx) | A | Generated ShadCN primitives; no asynchronous logic so no error handling required. |
| client/src/hooks/use-mobile.tsx | B | Watches window resize but doesn’t guard for SSR or cleanup failures; would benefit from try/catch when matchMedia unsupported. |
| client/src/hooks/use-toast.ts | B | Reducer manages dismissal queue but never handles failures in listeners, so a throwing listener could break the toast bus. |

## Shared, Config, and Scripts
| File | Grade | Notes |
| --- | --- | --- |
| shared/schema.ts | B | Defines types only; relies on consumers for validation. |
| script/build.ts | B | Build promise chain has catch/exit, but intermediate steps (rm/viteBuild/esbuild) aren’t individually wrapped so partial artifacts may remain. |
| tsconfig.json, tailwind.config.ts, postcss.config.js, components.json, package.json, package-lock.json | N/A | Build/config metadata. |
| playwright.config.ts | B | CI retries configured, but there’s no hook to fail fast when dev server fails to start aside from Playwright timeout. |
| drizzle.config.ts | C | Throws immediately if DATABASE_URL unset (good), but there’s no guidance for alternate envs or fallback to .env. |
| FASTAPI_SETUP.md, MIGRATION.md, design_guidelines.md, PROCORE_FOUNDATION_COMPLETE.md, replit.md, README files | N/A | Documentation only. |

## Tests
| File | Grade | Notes |
| --- | --- | --- |
| tests/e2e/helpers.ts | C | Helpers assume selectors always appear; no error capture or debugging screenshots for missing nodes. |
| tests/e2e/dashboard.spec.ts | C | Verifies happy paths only; no assertions around API failures or error toasts. |
| tests/e2e/navigation.spec.ts | C | Does not simulate network failures, so client-side error handling remains untested. |
| tests/e2e/procore-status.spec.ts | C | Only checks visible states, not failure/retry flows. |
| tests/README.md | N/A | Documentation. |
