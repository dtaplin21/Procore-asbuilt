# Data retention policy (draft)

**Last updated:** 2026-04-28  
**Operator:** Grand Gaia LLC  
**Product:** Procore-Integrator  

> **Draft — counsel and engineering should validate against actual backups, replicas, and legal holds.**

## 1. Purpose

Define **how long** categories of data are kept and **how** deletion is performed, consistent with the **[Privacy policy draft](PRIVACY_POLICY.md)** and customer agreements.

## 2. Retention schedule *(fill with real periods)*

| Data category | Typical retention | Deletion / anonymization | Notes |
|---------------|-------------------|---------------------------|--------|
| Account / profile | *(e.g. life of contract + 30 days)* | | |
| OAuth / session tokens | *(e.g. per session or refresh policy)* | | |
| Uploaded drawings & derivatives | | | May include render artifacts |
| Comparison / diff / alignment records | | | |
| Audit / security logs | | | Often shorter or longer by law |
| Backup snapshots | | | Point-in-time may extend effective retention |
| Beta tester data | | | Align with **BETA** terms |

## 3. Customer-initiated deletion

*(Describe export / deletion requests, SLAs, and exceptions e.g. legal hold.)*

## 4. Backups & replicas

Backups may **delay** deletion until rotation. Document **maximum** recovery window.

## 5. Legal hold

Data subject to litigation or regulatory hold **may be retained** beyond standard schedules.

## 6. Review cycle

- [ ] Engineering confirms storage locations (DB, object store, logs).  
- [ ] Counsel approves periods and notices.  
- [ ] Annual review *(or quarterly for regulated customers)*.  

---

*Draft. Not legal advice.*
