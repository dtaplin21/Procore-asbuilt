## Notes / Documentation System

This folder is the running documentation set for the product + engineering work in this repo.

### Structure (4 pillars)

- `feature-overview/`: **Product-level** docs (what the feature is, who it’s for, UX/flows).
- `technical-implementation/`: **Engineering-level** docs (APIs, schemas, data flows, code pointers).
- `architectural-impact/`: **System/architecture** docs (cross-cutting changes, tradeoffs, dependencies).
- `future-hooks/`: **Expansion notes** (what to build next, hooks, migration paths, safe-to-defer TODOs).

### How to document a new feature

When you add a feature, create 1–4 docs (only where relevant):
- **Feature overview**: `Notes/feature-overview/<feature>.md`
- **Technical implementation**: `Notes/technical-implementation/<feature>.md`
- **Architectural impact**: `Notes/architectural-impact/<feature>.md`
- **Future hooks**: `Notes/future-hooks/<feature>.md`

Naming convention:
- Use kebab-case filenames, e.g. `project-scoping-foundation.md`
- If you want chronology, prefix with `YYYY-MM-DD_`.

### Templates

- Use `Notes/TEMPLATE_FEATURE_DOC.md` as a starting point.

### Existing docs

Some foundational docs currently live in the root of `Notes/`:
- `DATABASE_IMPLEMENTATION.md`
- `ERROR_LOGGING_STRATEGY.md`

Over time, we can copy/move them into the pillar folders when convenient.
