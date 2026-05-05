# Dependency license report

The application uses third-party open-source dependencies.

License reports were generated for frontend and backend dependencies and stored in this folder.

**Reports:**

- `frontend-licenses.json`
- `frontend-license-summary.txt`
- `backend-licenses.json`
- `backend-license-summary.txt`

**CycloneDX SBOM (machine-readable):** see **`sbom/`** — [`sbom/README.md`](sbom/README.md); regenerate with `npm run sbom:frontend` and `npm run sbom:backend`.

**Last generated:** 2026-04-22 (regenerate before major releases or when dependencies change.)

---

## Commercial-use review

Review should check for:

- GPL  
- AGPL  
- LGPL  
- SSPL  
- Unknown licenses  
- Non-commercial licenses  
- Custom restrictive licenses  

Permissive licenses such as **MIT**, **Apache-2.0**, **BSD**, and **ISC** are generally more compatible with proprietary commercial software, but **all** dependency licenses should be reviewed before commercial launch.

**SPDX** (https://spdx.org/licenses/) standardizes **license identifiers** and stable references for common open-source licenses. Use SPDX IDs in SBOMs, `THIRD_PARTY_NOTICES.md` blocks, and internal clearance where possible. For dependencies not on the SPDX list, capture the full license text as counsel requires.

---

## Regenerating reports

From the **repository root**:

```bash
mkdir -p legal
npx license-checker --production --json > legal/frontend-licenses.json
npx license-checker --production --summary > legal/frontend-license-summary.txt
```

From **`backend/`** (with project venv):

```bash
./venv/bin/pip install pip-licenses
./venv/bin/pip-licenses --format=json --output-file=../legal/backend-licenses.json
./venv/bin/pip-licenses > ../legal/backend-license-summary.txt
```

---

## Project context

| Stack | Manifest | Report |
|-------|----------|--------|
| Frontend | Root `package.json` | `frontend-*.json` / `.txt` |
| Backend | `backend/requirements.txt` (+ venv installs) | `backend-*.json` / `.txt` |

Grand Gaia LLC’s **original** code is proprietary (root **`LICENSE`**). Third-party packages remain under **their** respective licenses; this report inventories those declarations as emitted by the tools above.

**Follow-up:** Open `frontend-licenses.json` / `backend-licenses.json` and resolve any **`UNKNOWN`** or compound license strings (e.g. `MIT AND …`) with counsel or manual `package.json` / PyPI inspection.  

*Expected:* the root npm package (`rest-express` / this repo) may appear as **`UNKNOWN`** in `frontend-licenses.json` because the root **`LICENSE`** is proprietary, not an SPDX OSS id—this is not a third-party dependency.

**Note:** `pip-licenses` was installed into `backend/venv` to generate reports. For a clean production venv, reinstall from `requirements.txt` only, or use a disposable venv for license audits.

---

*Administrative / compliance aid. Not legal advice.*
