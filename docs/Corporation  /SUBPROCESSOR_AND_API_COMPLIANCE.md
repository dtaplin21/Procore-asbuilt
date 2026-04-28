# Subprocessors & third-party API compliance (draft)

**Operator:** Grand Gaia LLC  
**Product:** Procore-Integrator  
**Last updated:** 2026-04-28  

> **Maintain this list for customer DPAs and security questionnaires.** Link the current version from your Privacy Policy.

## 1. Subprocessors *(infrastructure & services)*

| Subprocessor | Purpose | Data types *(high level)* | Location *(if known)* | Agreement / notes |
|--------------|---------|----------------------------|------------------------|-------------------|
| *(e.g. cloud host)* | Compute / DB | | | |
| *(e.g. object storage)* | File storage | Uploads | | |
| Procore | Construction platform API | Project/drawing identifiers, OAuth tokens, synced entities | Procore / customer-configured | Customer’s Procore agreement; **developer terms** at Procore |
| *(e.g. email)* | Transactional mail | Email, name | | |
| *(e.g. error tracking)* | Diagnostics | Logs, IPs | | |

*Add AI vendors only if customer data is sent to them in production.*

## 2. Third-party API terms (compliance posture)

Grand Gaia designs **Procore-Integrator** to operate with **Procore** APIs using patterns documented by Procore (e.g. OAuth, required headers such as `Procore-Company-Id` where applicable).  

**Action items:**

- [ ] Maintain links to **current** Procore developer / API terms your integration relies on.  
- [ ] Document **which** Procore apps / permissions you request and why (for security review).  
- [ ] Ensure customer contracts allow the integration and data processing you perform.  

*(Add rows for any other third-party APIs: payment, maps, etc.)*

## 3. Customer-facing API

If Grand Gaia offers a **documented API** to customers, publish **[`API_TERMS.md`](API_TERMS.md)** and reference it in order forms.

## 4. Review cadence

- [ ] Quarterly subprocessors review.  
- [ ] Update when adding a vendor that touches personal data or auth.  

---

*Draft. Not legal advice.*
