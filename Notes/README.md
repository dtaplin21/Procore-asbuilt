## Notes / Documentation System

This folder is the running documentation set for the product + engineering work in this repo.

**Ongoing upkeep:** See [`DOC_MAINTENANCE.md`](./DOC_MAINTENANCE.md) for triggers, checklists, and how to update pillar indexes when files change.

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

- Use [`TEMPLATE_FEATURE_DOC.md`](./TEMPLATE_FEATURE_DOC.md) as a starting point.

### Foundational docs (root of `Notes/`)

| Doc | Role |
|-----|------|
| [`DATABASE_IMPLEMENTATION.md`](./DATABASE_IMPLEMENTATION.md) | Database setup and implementation notes |
| [`ERROR_LOGGING_STRATEGY.md`](./ERROR_LOGGING_STRATEGY.md) | Logging and error-handling conventions |
| [`IMPLEMENTATION_PHASES.md`](./IMPLEMENTATION_PHASES.md) | Phased roadmap / implementation order |
| [`CHANGES_BEFORE_PRODUCTION.md`](./CHANGES_BEFORE_PRODUCTION.md) | Pre-production change list |
| [`Production_checklist.md`](./Production_checklist.md) | Short production checklist |
| [`DOC_MAINTENANCE.md`](./DOC_MAINTENANCE.md) | How to maintain this documentation set |

Over time, foundational docs can move into pillar folders when convenient; if you move one, update this table and the pillar `README.md` index.
