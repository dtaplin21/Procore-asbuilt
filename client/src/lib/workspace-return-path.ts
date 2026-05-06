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

/** Sidebar fallback: last project id as decimal string (integer > 0). */
export const LAST_PROJECT_ID_STORAGE_KEY = "qcqa:lastProjectId";

export const WORKSPACE_STORAGE_CHANGE_EVENT = "qcqa-workspace-storage";

function safeSessionStorage(): Storage | null {
  if (typeof sessionStorage === "undefined") return null;
  return sessionStorage;
}

function notifyWorkspaceStorageUpdated(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(WORKSPACE_STORAGE_CHANGE_EVENT));
}

export function subscribeWorkspaceStorage(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(WORKSPACE_STORAGE_CHANGE_EVENT, callback);
  return () => window.removeEventListener(WORKSPACE_STORAGE_CHANGE_EVENT, callback);
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
    notifyWorkspaceStorageUpdated();
  } catch {
    /* quota / private mode */
  }
}

function isValidPositiveIntId(n: number): boolean {
  return Number.isInteger(n) && n > 0;
}

/** Optional fallback for nav when no full workspace path is stored. */
export function setLastProjectIdForWorkspaceFallback(projectId: number): void {
  if (!isValidPositiveIntId(projectId)) return;
  const s = safeSessionStorage();
  if (!s) return;
  try {
    s.setItem(LAST_PROJECT_ID_STORAGE_KEY, String(projectId));
    notifyWorkspaceStorageUpdated();
  } catch {
    /* quota / private mode */
  }
}

export function getLastProjectIdForWorkspaceFallback(): number | null {
  const s = safeSessionStorage();
  if (!s) return null;
  try {
    const raw = s.getItem(LAST_PROJECT_ID_STORAGE_KEY);
    if (raw == null || raw === "") return null;
    const n = Number(raw);
    if (!isValidPositiveIntId(n)) return null;
    return n;
  } catch {
    return null;
  }
}

export type WorkspaceSidebarNav = {
  /** Target when `disabled` is false; ignored when disabled. */
  href: string;
  disabled: boolean;
  tooltip: string;
};

/** Nav row: full workspace URL, else project drawing picker (B), else disabled (C). */
export function getWorkspaceSidebarNav(): WorkspaceSidebarNav {
  const last = getWorkspaceReturnPath();
  if (
    last &&
    last.startsWith("/projects/") &&
    last.includes("/workspace")
  ) {
    return {
      href: last,
      disabled: false,
      tooltip: "Workspace",
    };
  }
  const pid = getLastProjectIdForWorkspaceFallback();
  if (pid != null) {
    return {
      href: `/projects/${pid}/drawings`,
      disabled: false,
      tooltip: "Drawings — open workspace from a drawing",
    };
  }
  return {
    href: "/",
    disabled: true,
    tooltip: "Open a drawing workspace from the dashboard first.",
  };
}
