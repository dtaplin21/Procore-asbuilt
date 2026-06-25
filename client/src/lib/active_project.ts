/**
 * Active project context — session-scoped project selection shared across routes.
 * Resolution: URL (query or path) → sessionStorage → null.
 */

export const ACTIVE_PROJECT_ID_STORAGE_KEY = "qcqa:activeProjectId";

const PROJECT_PATH = /^\/projects\/(\d+)(?:\/|$)/;
const WORKSPACE_STUB_PATH = /^\/workspace\/(\d+)(?:\/|$)/;

export function isValidPositiveIntId(n: number): boolean {
  return Number.isInteger(n) && n > 0;
}

export function parsePositiveIntId(raw: string | null | undefined): number | null {
  if (raw == null || raw.trim() === "") return null;
  const n = Number(raw.trim());
  if (!isValidPositiveIntId(n)) return null;
  return n;
}

export function getActiveProjectIdFromStorage(): number | null {
  try {
    return parsePositiveIntId(
      window.sessionStorage.getItem(ACTIVE_PROJECT_ID_STORAGE_KEY),
    );
  } catch {
    return null;
  }
}

export function setActiveProjectIdInStorage(projectId: number | null): void {
  try {
    if (projectId == null || !isValidPositiveIntId(projectId)) {
      window.sessionStorage.removeItem(ACTIVE_PROJECT_ID_STORAGE_KEY);
    } else {
      window.sessionStorage.setItem(
        ACTIVE_PROJECT_ID_STORAGE_KEY,
        String(projectId),
      );
    }
  } catch {
    /* quota / private mode */
  }
}

export function parseProjectIdFromLocation(
  pathname: string,
  search = "",
): number | null {
  const rawSearch = search.startsWith("?") ? search.slice(1) : search;
  const fromQuery = parsePositiveIntId(
    new URLSearchParams(rawSearch).get("projectId"),
  );
  if (fromQuery != null) return fromQuery;

  const projectMatch = pathname.match(PROJECT_PATH);
  if (projectMatch) {
    return parsePositiveIntId(projectMatch[1]);
  }

  const workspaceMatch = pathname.match(WORKSPACE_STUB_PATH);
  if (workspaceMatch) {
    return parsePositiveIntId(workspaceMatch[1]);
  }

  return null;
}

/** URL (query or path) → sessionStorage → null. */
export function resolveActiveProjectId(
  pathname: string,
  search = "",
): number | null {
  const fromUrl = parseProjectIdFromLocation(pathname, search);
  if (fromUrl != null) return fromUrl;
  return getActiveProjectIdFromStorage();
}

/** Dashboard-only URL sync (uses replaceState; does not notify React Router). */
export function replaceDashboardProjectIdInUrl(projectId: string | null): void {
  const url = new URL(window.location.href);
  if (projectId) url.searchParams.set("projectId", projectId);
  else url.searchParams.delete("projectId");
  window.history.replaceState({}, "", url.toString());
}

/** Strip cross-project deep-link params when the active project changes on /objects. */
export function objectsSearchParamsAfterProjectChange(
  current: URLSearchParams,
  newProjectId: number,
): URLSearchParams {
  const next = new URLSearchParams(current);
  next.set("projectId", String(newProjectId));
  next.delete("drawingId");
  next.delete("run");
  next.delete("overlay");
  return next;
}
