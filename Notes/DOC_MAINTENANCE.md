# Documentation maintenance

How to keep engineering and product notes accurate as the repo changes. The canonical structure is described in [`README.md`](./README.md).

## When to update docs (triggers)

| Change | What to review or update |
|--------|---------------------------|
| New user-facing feature | One or more pillar docs under `feature-overview/`, `technical-implementation/`, `architectural-impact/`, `future-hooks/` (only where relevant); update that pillar’s `README.md` index. |
| API or shared types | [`shared/schema.ts`](../shared/schema.ts); add or refresh a note in `technical-implementation/` if behavior is non-obvious. |
| Database or migrations | [`DATABASE_IMPLEMENTATION.md`](./DATABASE_IMPLEMENTATION.md); Alembic/Drizzle notes if applicable. |
| Logging or errors | [`ERROR_LOGGING_STRATEGY.md`](./ERROR_LOGGING_STRATEGY.md). |
| Phases / roadmap | [`IMPLEMENTATION_PHASES.md`](./IMPLEMENTATION_PHASES.md). |
| Pre-production checklist items | [`CHANGES_BEFORE_PRODUCTION.md`](./CHANGES_BEFORE_PRODUCTION.md), [`Production_checklist.md`](./Production_checklist.md). |
| Test layout or commands | [`tests/README.md`](../tests/README.md); root [`package.json`](../package.json) scripts. |
| Stack, routing, or major modules | [`replit.md`](../replit.md) (project brief for tools and contributors). |
| Backend runbooks | [`backend/README.md`](../backend/README.md). |

## Files to check on each release (lightweight pass)

1. **`Notes/README.md`** — Pillar list and links still match reality.
2. **Each pillar `README.md`** — Lists or describes current docs in that folder (see indexes below).
3. **`Notes/IMPLEMENTATION_PHASES.md`** — Phases reflect current priorities.
4. **`replit.md`** — Architecture section still matches the stack (React, Vite, Express, Drizzle, etc.).

## Pillar indexes (keep in sync)

Update the `README.md` inside each pillar when you add, rename, or remove a doc:

- [`feature-overview/README.md`](./feature-overview/README.md)
- [`technical-implementation/README.md`](./technical-implementation/README.md)
- [`architectural-impact/README.md`](./architectural-impact/README.md)
- [`future-hooks/README.md`](./future-hooks/README.md)

## Naming and placement

- Prefer **kebab-case** filenames (e.g. `drawing-workspace-alignments.md`).
- Optional chronological prefix: `YYYY-MM-DD_…`.
- Prefer technical deep-dives under `technical-implementation/` rather than the root of `Notes/`, unless the doc is truly cross-cutting (then root or `architectural-impact/`).

## Code-adjacent “living documentation”

These are not Markdown but should be updated with the same triggers as API docs:

- `shared/schema.ts` — Shared contracts between client and server.
- Client API modules under `client/src/lib/api/` — Endpoint paths and request shapes.
- Root `package.json` scripts — Documented behavior for `dev`, `test`, `test:unit`, etc.

## New feature doc workflow

1. Copy [`TEMPLATE_FEATURE_DOC.md`](./TEMPLATE_FEATURE_DOC.md) into the right pillar folder.
2. Fill only sections that add value; delete the rest.
3. Add one line to the pillar `README.md` index pointing to the new file.
4. If the feature affects phases, adjust `IMPLEMENTATION_PHASES.md`.
