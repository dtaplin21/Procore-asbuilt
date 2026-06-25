/**
 * Canonical deep-link helper for the Objects page — the single drawing
 * surface after the workspace/Objects merge (per the merge plan, Phase 1).
 *
 * URL contract:
 *   /objects?projectId=2&drawingId=8                       -> master sheet, latest run overlays (or none)
 *   /objects?projectId=2&drawingId=8&run=15                -> sheet + overlays for run 15
 *   /objects?projectId=2&drawingId=8&run=15&overlay=42     -> focus a specific overlay
 *
 * This replaces the old workspace URL pattern
 * (/projects/:id/drawings/:id/workspace) as the canonical destination for
 * "view this master drawing" links throughout the app — see
 * workspace-links.ts, which now wraps this function instead of building
 * its own /workspace URLs.
 */

export interface ObjectsRouteParams {
  projectId: string;
  drawingId: string;
  runId?: string;
  overlayId?: string;
}

/**
 * Build the path + query string for the Objects page.
 *
 * Kept as a plain string-builder (not a navigate() call) so it works
 * equally from React Router's <Link to={...}>, wouter's <Link href={...}>,
 * window.location assignment, or server-side link construction — callers
 * decide how to use the resulting string.
 */
export function objectsPagePath(
  projectId: string,
  drawingId: string,
  runId?: string | null,
  overlayId?: string | null,
): string {
  const params = new URLSearchParams();
  params.set("projectId", projectId);
  params.set("drawingId", drawingId);
  if (runId) {
    params.set("run", runId);
  }
  if (overlayId) {
    params.set("overlay", overlayId);
  }
  return `/objects?${params.toString()}`;
}

/**
 * Parse the Objects page's query params back out of a URLSearchParams
 * instance (or anything with a compatible .get() — e.g. React Router's
 * useSearchParams() return value). Centralizes the param NAMES in one
 * place so "run" vs "runId" vs "run_id" is never inconsistently spelled
 * across call sites.
 */
export function parseObjectsRouteParams(
  searchParams: Pick<URLSearchParams, "get">,
): Partial<ObjectsRouteParams> {
  return {
    projectId: searchParams.get("projectId") ?? undefined,
    drawingId: searchParams.get("drawingId") ?? undefined,
    runId: searchParams.get("run") ?? undefined,
    overlayId: searchParams.get("overlay") ?? undefined,
  };
}

/**
 * Build an Objects URL from an InspectionRun — the common case from the
 * Inspections page's "View on drawing" action and from
 * inspection_run_row.tsx.
 */
export function objectsPagePathForRun(params: {
  projectId: string;
  masterDrawingId: string;
  runId: string;
}): string {
  return objectsPagePath(params.projectId, params.masterDrawingId, params.runId);
}

const WORKSPACE_PATH =
  /^\/projects\/(\d+)\/drawings\/(\d+)\/workspace\/?$/;

/** Legacy workspace path → Objects URL (preserves run, overlay, findingId). */
export function workspacePathToObjectsUrl(
  pathname: string,
  search = "",
): string | null {
  const match = pathname.match(WORKSPACE_PATH);
  if (!match) return null;

  const [, projectId, drawingId] = match;
  const raw = search.startsWith("?") ? search.slice(1) : search;
  const params = new URLSearchParams(raw);
  const runId = params.get("run");
  const overlayId = params.get("overlay") ?? params.get("findingId");

  return objectsPagePath(
    projectId,
    drawingId,
    runId,
    overlayId,
  );
}
