# Third-party notices

**Project:** Procore-Integrator  

This file summarizes **notices you may need to display** for open-source and third-party components shipped with or used to build the product. It should be kept in sync with `DEPENDENCY_LICENSE_REPORT.md` and any vendor `NOTICE` files.

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
