/**
 * Remembers "the last drawing the user was looking at" so sidebar nav and
 * "back to drawing" actions land somewhere useful. Per the merge plan
 * (Phase 1/2): this now stores Objects URLs (/objects?...) instead of the
 * old /projects/:id/drawings/:id/workspace path.
 *
 * Storage: sessionStorage, scoped per browser tab/session — deliberately
 * NOT localStorage, since "last viewed drawing" shouldn't leak across
 * separate browser sessions/devices for the same logged-in user (that's
 * server-side state if you want it to persist that broadly).
 */

import { objectsPagePath, workspacePathToObjectsUrl } from "@/lib/objectsRoute";

const STORAGE_KEY = "lastDrawingReturnPath";

/** Sidebar + migration helpers (same module, same storage key). */
const LEGACY_STORAGE_KEY = "qcqa:lastDrawingWorkspace";
export const LAST_PROJECT_ID_STORAGE_KEY = "qcqa:lastProjectId";
export const WORKSPACE_STORAGE_CHANGE_EVENT = "qcqa-workspace-storage";
/** @deprecated Use STORAGE_KEY via getDrawingReturnPath. */
export const WORKSPACE_RETURN_PATH_STORAGE_KEY = STORAGE_KEY;

function notifyWorkspaceStorageUpdated(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(WORKSPACE_STORAGE_CHANGE_EVENT));
}

export function setDrawingReturnPath(
  projectId: string,
  drawingId: string,
  runId?: string | null,
): void {
  const path = objectsPagePath(projectId, drawingId, runId ?? undefined);
  try {
    window.sessionStorage.setItem(STORAGE_KEY, path);
    notifyWorkspaceStorageUpdated();
  } catch {
    // sessionStorage can throw in some embedded/private-browsing
    // contexts — losing "remember last drawing" is not worth a crash.
  }
}

/**
 * Returns the last-remembered Objects URL, or null if none is stored yet
 * (e.g. first visit this session). Callers should fall back to a sensible
 * default (e.g. the project's drawing list) when this returns null.
 */
export function getDrawingReturnPath(): string | null {
  try {
    const current = window.sessionStorage.getItem(STORAGE_KEY);
    if (current?.trim()) {
      return current.trim();
    }
    const legacy = window.sessionStorage.getItem(LEGACY_STORAGE_KEY);
    return legacy?.trim() ? legacy.trim() : null;
  } catch {
    return null;
  }
}

export function clearDrawingReturnPath(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
    window.sessionStorage.removeItem(LEGACY_STORAGE_KEY);
    notifyWorkspaceStorageUpdated();
  } catch {
    // no-op — see setDrawingReturnPath
  }
}

/** Store a full Objects URL (e.g. when overlay query params are present). */
export function setWorkspaceReturnPath(fullPath: string): void {
  const trimmed = fullPath.trim();
  if (!trimmed.startsWith("/")) return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, trimmed);
    notifyWorkspaceStorageUpdated();
  } catch {
    /* quota / private mode */
  }
}

/** @deprecated Prefer {@link getDrawingReturnPath}. */
export function getWorkspaceReturnPath(): string | null {
  return getDrawingReturnPath();
}

export function subscribeWorkspaceStorage(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(WORKSPACE_STORAGE_CHANGE_EVENT, callback);
  return () => window.removeEventListener(WORKSPACE_STORAGE_CHANGE_EVENT, callback);
}

function isValidPositiveIntId(n: number): boolean {
  return Number.isInteger(n) && n > 0;
}

export function setLastProjectIdForWorkspaceFallback(projectId: number): void {
  if (!isValidPositiveIntId(projectId)) return;
  try {
    window.sessionStorage.setItem(LAST_PROJECT_ID_STORAGE_KEY, String(projectId));
    notifyWorkspaceStorageUpdated();
  } catch {
    /* quota / private mode */
  }
}

export function getLastProjectIdForWorkspaceFallback(): number | null {
  try {
    const raw = window.sessionStorage.getItem(LAST_PROJECT_ID_STORAGE_KEY);
    if (raw == null || raw === "") return null;
    const n = Number(raw);
    if (!isValidPositiveIntId(n)) return null;
    return n;
  } catch {
    return null;
  }
}

export type ObjectsSidebarNav = {
  href: string;
  tooltip: string;
};

function resolveObjectsHrefFromReturnPath(path: string): string | null {
  if (path.startsWith("/objects")) {
    return path;
  }
  if (path.startsWith("/projects/") && path.includes("/workspace")) {
    const q = path.indexOf("?");
    const pathname = q === -1 ? path : path.slice(0, q);
    const search = q === -1 ? "" : path.slice(q);
    return workspacePathToObjectsUrl(pathname, search);
  }
  return null;
}

/**
 * Smart Objects sidebar link (merge plan Phase 1, Option A):
 * remembered drawing deep link → last project → bare /objects.
 */
export function getObjectsSidebarNav(): ObjectsSidebarNav {
  const last = getDrawingReturnPath();
  if (last) {
    const href = resolveObjectsHrefFromReturnPath(last);
    if (href) {
      return {
        href,
        tooltip: "Return to last viewed drawing",
      };
    }
  }
  const pid = getLastProjectIdForWorkspaceFallback();
  if (pid != null) {
    return {
      href: `/objects?projectId=${pid}`,
      tooltip: "Objects for your last project",
    };
  }
  return {
    href: "/objects",
    tooltip: "Drawing viewer and QC/QA objects",
  };
}
