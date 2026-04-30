## Technical Implementation (Engineering-Level)

Put engineering-facing documentation here:

- Endpoint contracts + example payloads
- DB schema decisions and migrations
- Key modules/classes and how they interact
- Operational notes for running/testing locally

Use [`Notes/TEMPLATE_FEATURE_DOC.md`](../TEMPLATE_FEATURE_DOC.md) as a starting point and keep this folder focused on *how it works*.

**Maintenance:** When you add or rename a file here, update the list below. See [`Notes/DOC_MAINTENANCE.md`](../DOC_MAINTENANCE.md).

### Current docs

| File | Topic |
|------|--------|
| [`Inference pipeline.md`](./Inference%20pipeline.md) | Inference / ML pipeline |
| [`findings_and_alembic_plan.md`](./findings_and_alembic_plan.md) | Findings and Alembic planning |
| [`inspection_drawing_procore_pipline.md`](./inspection_drawing_procore_pipline.md) | Inspection / drawing / Procore pipeline |
| [`procore_token_persistence.md`](./procore_token_persistence.md) | Procore OAuth token DB persistence (Approach B) |
| [`render_postgres_migration.md`](./render_postgres_migration.md) | Copy local Postgres schema+data to Render (`dump_restore_render_postgres.sh`) |
