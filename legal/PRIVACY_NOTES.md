# Privacy notes (internal draft)

**Project:** Procore-Integrator  
**Controller / operator (draft):** Grand Gaia LLC  

> **Important:** For customer-facing products, publish a **Privacy Policy** reviewed by counsel. This file is an **internal working outline** of data practices.  
> **Public draft (counsel review):** [`../docs/trust/PRIVACY_POLICY.md`](../docs/trust/PRIVACY_POLICY.md) — subprocessors: [`../docs/trust/SUBPROCESSOR_AND_API_COMPLIANCE.md`](../docs/trust/SUBPROCESSOR_AND_API_COMPLIANCE.md).

## Data the application may process

*(Update after architecture review.)*

| Category | Examples | Stored where | Retention |
|----------|----------|--------------|-----------|
| Account / auth | *(e.g. session, OAuth tokens)* | | |
| Project / drawing metadata | | | |
| User content | Uploads, comparisons | | |
| Logs / analytics | | | |

## Third parties / subprocessors

| Party | Purpose | Data shared |
|-------|---------|-------------|
| Procore | *(API integration)* | *(describe)* |
| Hosting / DB | | |
| AI vendors | *(if any production AI)* | |

## Security measures (high level)

- Transport encryption *(HTTPS)*  
- Access controls *(describe)*  
- *(Add items relevant to your deployment)*  

## User rights

*(GDPR/CCPA/other — list rights and contact method once defined.)*

## Action items

- [ ] Map actual data flows from frontend → backend → integrations.
- [ ] Add DPIA or similar if required by your org.
- [ ] Publish external Privacy Policy URL when ready.

---

*Not legal advice.*
