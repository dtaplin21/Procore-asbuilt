# Trust & compliance pack (drafts)

**Operator:** Grand Gaia LLC  
**Product:** Procore-Integrator  

Customer and vendor diligence materials **drafted for refinement** with counsel and ops. Public URLs (website, status page, trust portal) should mirror the **approved** versions of these documents.

| Document | Path | Purpose |
|----------|------|---------|
| Security disclosures | [`../../SECURITY.md`](../../SECURITY.md) (repo root) | Vulnerability reporting |
| Privacy policy (public draft) | [`../../legal/PRIVACY_POLICY.md`](../../legal/PRIVACY_POLICY.md) | End-user / customer privacy |
| Data retention | [`DATA_RETENTION_POLICY.md`](DATA_RETENTION_POLICY.md) | Retention & deletion |
| SOC 2 roadmap | [`SOC2_ROADMAP.md`](SOC2_ROADMAP.md) | Attestation planning |
| API terms (your API) | [`API_TERMS.md`](API_TERMS.md) | Terms for API consumers |
| Subprocessors & third-party APIs | [`SUBPROCESSOR_AND_API_COMPLIANCE.md`](SUBPROCESSOR_AND_API_COMPLIANCE.md) | Procore, hosting, etc. |
| Insurance checklist | [`VENDOR_INSURANCE_CHECKLIST.md`](VENDOR_INSURANCE_CHECKLIST.md) | COI / cyber / E&O |

**Internal (not necessarily customer-facing):**

| Document | Path |
|----------|------|
| Ownership, beta, licenses, SBOM | [`../../legal/`](../../legal/) |
| Internal privacy working notes | [`../../legal/PRIVACY_NOTES.md`](../../legal/PRIVACY_NOTES.md) |
| CycloneDX SBOM artifacts | [`../../legal/sbom/`](../../legal/sbom/) |

## Regenerate SBOM

From repository root:

```bash
npm run sbom:frontend
npm run sbom:backend
```

See [`../../legal/sbom/README.md`](../../legal/sbom/README.md).
