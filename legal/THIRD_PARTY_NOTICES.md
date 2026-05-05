# Third-party notices

**Project:** Procore-Integrator  

This file summarizes **notices you may need to display** for open-source and third-party components shipped with or used to build the product. It should be kept in sync with `DEPENDENCY_LICENSE_REPORT.md` and any vendor `NOTICE` files.

## SPDX (Software Package Data Exchange)

**SPDX** standardizes how you record **license identifiers** (e.g. `MIT`, `Apache-2.0`), **license text** references, and **stable URIs** for well-known licenses—useful for SBOMs, CI checks, and enterprise diligence.

| Resource | URL / note |
|----------|------------|
| SPDX License List | https://spdx.org/licenses/ |
| SPDX specification | https://spdx.dev/ |
| CycloneDX SBOMs (this repo) | `legal/sbom/*.json` |

When you add notice blocks for dependencies (below), prefer **`SPDX-License-Identifier:`** where the license is on the SPDX list. For custom or non-SPDX licenses, paste or link the **full license text** as your counsel requires.

## How this repo is built

| Layer | Manifest | Notes |
|-------|----------|--------|
| Frontend | `package.json` (npm) | React, Vite, Radix UI, Tailwind, etc. |
| Backend | `backend/requirements.txt` | Python / FastAPI ecosystem |

## Notices template

*(Populate from your license report tool or lawyer’s template. Example structure:)*

```
Component: <name>
SPDX-License-Identifier: <e.g. MIT>
Copyright: <as required by license>
Source: <URL>
```

## Commercial / API services

| Service | Relationship | Notice / terms URL |
|---------|--------------|--------------------|
| Procore (APIs, branding) | *(integration — describe)* | https://www.procore.com/legal *(verify current URL)* |
| *(other)* | | |

## Action items

- [ ] Generate full notice text for production UI or installer (if required).
- [ ] Store raw license outputs under `/legal` or `docs/` if desired (e.g. `licenses-npm.json`).

---

*Does not list every dependency line-by-line; use `DEPENDENCY_LICENSE_REPORT.md` for the inventory.*
