# Security policy

**Product:** Procore-Integrator  
**Maintainer:** Grand Gaia LLC  

## Supported versions

Security updates are applied to the **current development / release branch** Grand Gaia actively maintains. Older tags may not receive patches—contact Grand Gaia for support terms.

## Reporting a vulnerability

**Please do not** open public GitHub issues for undisclosed security vulnerabilities.

1. Email **Grand Gaia LLC** at a dedicated security contact *(replace with `security@yourdomain.com` when published)*.  
2. Include: affected component, reproduction steps, impact assessment (if known), and whether the report is embargoed.  
3. Allow a reasonable time for triage and remediation before public disclosure, consistent with responsible disclosure practice.

Grand Gaia will acknowledge receipt when possible and coordinate fixes and release notes as appropriate.

## Scope (typical)

In scope: this repository’s application code, default configuration, and documented deployment patterns **as maintained by Grand Gaia**.  

Out of scope: third-party services (e.g. Procore platform security—report to the vendor), social engineering, physical attacks, or issues in dependencies without a practical fix in this product *(still welcome as informational reports)*.

## Secure development (summary)

- Dependencies tracked under `/legal` (license report + SBOM).  
- Prefer least-privilege credentials and environment-based secrets *(never commit secrets)*.  
- Review high-risk changes (auth, file upload, OAuth, multi-tenant data) before release.

---

*This policy may be updated. Not legal advice. Replace placeholder security email before external publication.*
