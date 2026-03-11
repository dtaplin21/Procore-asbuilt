1. Add supabase to handle imported files. (currently we use the local database)
###############################################################################################################################
2.  Recommendations

  1. Replace the placeholder CRUD service implementations with real persistence or remove the routers; in the interim, add schemas/validation and
     explicit “not implemented” errors so clients don’t assume success (backend/api/routes/submittals.py, backend/services/storage.py).
  2. Harden the Node wrapper by removing the throw err in server/index.ts:65-71, logging structured details, and promoting shared error helpers in
     server/routes.ts so Express doesn’t silently swallow stack traces.
  3. Add a React error boundary plus per-query error states/toasts (start with Dashboard/Inspections/Objects) and make all fetch helpers verify
     res.ok before parsing (client/src/App.tsx:94-186, client/src/pages/*.tsx), so users always see actionable feedback instead of blank screens.
