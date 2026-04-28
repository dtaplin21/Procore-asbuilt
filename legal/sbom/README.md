# Software Bill of Materials (SBOM)

**Product:** Procore-Integrator  
**Format:** [CycloneDX](https://cyclonedx.org/) JSON  

## Files

| Artifact | Description |
|----------|-------------|
| `frontend-cyclonedx.json` | NPM dependency tree (root `package.json` / lockfile) |
| `backend-cyclonedx.json` | Python dependencies from `backend/requirements.txt` |

> **Note:** If `requirements.txt` uses **unpinned** versions, the backend SBOM may list components **without** resolved versions—prefer pinned or `pip freeze` output for production diligence *(see CycloneDX docs for `pip freeze` pipeline)*.

## Regenerate

From repository root:

```bash
npm run sbom:frontend
npm run sbom:backend
```

**Tools:**

- Frontend: `@cyclonedx/cyclonedx-npm` via `npx`.  
- Backend: `cyclonedx-bom` in `backend/venv` (`cyclonedx-py requirements …`).  

**Related:** Human-readable license summaries live in **`../DEPENDENCY_LICENSE_REPORT.md`** and `../frontend-licenses.json` / `../backend-licenses.json`.

---

*Regenerate before major releases or when dependencies change materially.*
