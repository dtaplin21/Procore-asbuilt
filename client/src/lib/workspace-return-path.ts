/**
 * Last drawing workspace URL for sidebar "return to workspace" navigation.
 *
 * **Storage:** `sessionStorage` — scoped to the browser tab; a new tab has no
 * remembered path until the user visits a workspace in that tab.
 *
 * **Key:** `qcqa:lastDrawingWorkspace`
 *
 * **Value:** Full client path to restore, including query string when needed:
 * - Path: `/projects/:projectId/drawings/:drawingId/workspace`
 * - Query: workspace selection uses `alignmentId` and `diffId`
 *   (see `client/src/hooks/use_workspace_selection_query_params.ts`). Other keys (e.g. dashboard
 *   `projectId`, insight `findingId`) may appear; preserve the full `location`
 *   string from wouter when saving so nothing is dropped unintentionally.
 */

export const WORKSPACE_RETURN_PATH_STORAGE_KEY = "qcqa:lastDrawingWorkspace";

function safeSessionStorage(): Storage | null {
  if (typeof sessionStorage === "undefined") return null;
  return sessionStorage;
}

export function getWorkspaceReturnPath(): string | null {
  const s = safeSessionStorage();
  if (!s) return null;
  try {
    const raw = s.getItem(WORKSPACE_RETURN_PATH_STORAGE_KEY);
    if (!raw || !raw.trim()) return null;
    const path = raw.trim();
    if (!path.startsWith("/")) return null;
    return path;
  } catch {
    return null;
  }
}

/** Persist path like `/projects/2/drawings/3/workspace` or with `?alignmentId=1&diffId=2`. */
export function setWorkspaceReturnPath(fullPath: string): void {
  const s = safeSessionStorage();
  if (!s) return;
  const trimmed = fullPath.trim();
  if (!trimmed.startsWith("/")) return;
  try {
    s.setItem(WORKSPACE_RETURN_PATH_STORAGE_KEY, trimmed);
  } catch {
    /* quota / private mode */
  }
}
