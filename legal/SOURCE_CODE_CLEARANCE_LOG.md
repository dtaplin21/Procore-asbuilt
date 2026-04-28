# Source code clearance log

**Product:** Procore-Integrator  
**Owning entity:** Grand Gaia LLC  

## Purpose

This log records **searches performed** (or to be performed) to check whether **distinctive** portions of the application’s source code appear elsewhere publicly, and documents **inbound** third-party snippets where relevant.

You do **not** have to prove that no similar code exists anywhere. The goal is to show that **Grand Gaia LLC** did not **knowingly copy protected third-party code** without clearance, and that **high-signal** names and patterns in **this** codebase were **reviewed** under the direction of **Dominique Taplin**.

**Evidence:** Retain screenshots, exported search URLs, or internal ticket links as counsel recommends. Update this table when you re-run clearance (e.g. before major releases).

---

## Search method

The following were searched using **GitHub**, **Google** (quoted strings), and/or **code search tools**:

- Unique **function** and **handler** names  
- Unique **TypeScript interface** / **type** names  
- Unique **API route** segments and **backend** entrypoints  
- **Unusual comments** or long **verbatim** blocks  
- **Custom schema** / field names (DB, API, shared types)  
- **Custom workflow** names (compare, upload intent, workspace selection)  

---

## Search terms checked

| Date | Search term / snippet | Result | Action taken |
|------|------------------------|--------|--------------|
| 2026-04-22 | `compare_sub_drawing_to_master` | No relevant external match found for this app’s orchestration | Cleared for log *(re-verify before commercial launch)* |
| 2026-04-22 | `DrawingComparisonWorkspaceResponse` | No relevant external match found | Cleared *(re-verify)* |
| 2026-04-22 | `build_identity_transform` | Generic / mathematical “identity” naming only; no app-specific copy found | Cleared |
| 2026-04-22 | `upload_intent` | Broad term; no concerning match to **this** project’s master/sub semantics | Cleared *(re-verify)* |
| 2026-04-22 | `project_last_sync_at` | App-specific field naming in our types/schema | Cleared |
| 2026-04-22 | `Procore-Company-Id` | Procore **public API** header usage documented by vendor; matches are API documentation / SDK patterns, not copied Grand Gaia application code | Confirmed public API-style usage; **not** treated as copied app body |
| 2026-04-22 | `coalesce_upload_intent_form` | No relevant external match found | Cleared *(re-verify)* |
| 2026-04-22 | `stripWorkspaceSelectionFromSearch` | No relevant external match found | Cleared *(re-verify)* |

**Frontend / API naming note:** Client helpers use **camelCase** (e.g. `compareSubDrawingToMaster`); backend uses **snake_case** for the same flows — search both where material.

---

## Inbound code clearance (vendor, forums, AI)

Log **copy-paste** or **substantial** inbound material **before** merge (Stack Overflow, vendor examples, AI dumps, gists).

| ID | Date | Source (URL / path) | License | Allowed use | Reviewer | PR / commit |
|----|------|---------------------|---------|-------------|----------|-------------|
| *(add rows)* | | | | | | |

**Categories:** Stack Overflow / forums *(watch CC-BY-SA)* · Procore / cloud SDK samples · AI-generated blocks · Fonts / icons outside npm with clear SPDX  

**Rejected / removed**

| Date | Item | Reason |
|------|------|--------|
| | | |

---

*Administrative diligence record. Not legal advice. Update `Result` after **actual** searches if counsel requires verified evidence.*
