/**
 * Canonical deep-link helper for the Objects page — the single drawing
 * surface after the workspace/Objects merge (per the merge plan, Phase 1).
 *
 * URL contract:
 *   /objects?projectId=2&drawingId=8                       -> master sheet, latest run overlays (or none)
 *   /objects?projectId=2&drawingId=8&run=15                -> sheet + overlays for run 15
 *   /objects?projectId=2&drawingId=8&run=15&overlay=42     -> focus a specific overlay
 *   /objects?projectId=2&drawingId=8&region=r1              -> focus a specific region (PR5)
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
  /** PR5: focus a specific backend region (e.g. from a region-aware
   * deep link or the inspection-run-row "region" link). Independent of
   * overlayId — a region can be focused without an overlay being
   * focused, and vice versa. */
  regionId?: string;
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
 * Options-object variant covering the full param set including PR5's
 * regionId — added as a separate function rather than a 5th positional
 * parameter on objectsPagePath() so existing call sites (and their
 * tests) don't need to change. Prefer this for any new call site that
 * needs to set regionId.
 */
export function objectsPagePathWithParams(
  params: Partial<ObjectsRouteParams> & { projectId: string; drawingId: string },
): string {
  const search = new URLSearchParams();
  search.set("projectId", params.projectId);
  search.set("drawingId", params.drawingId);
  if (params.runId) search.set("run", params.runId);
  if (params.overlayId) search.set("overlay", params.overlayId);
  if (params.regionId) search.set("region", params.regionId);
  return `/objects?${search.toString()}`;
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
    regionId: searchParams.get("region") ?? undefined,
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

/** Legacy workspace path → Objects URL (preserves run, overlay, findingId, region). */
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
  const regionId = params.get("region");

  return objectsPagePathWithParams({
    projectId,
    drawingId,
    runId: runId ?? undefined,
    overlayId: overlayId ?? undefined,
    regionId: regionId ?? undefined,
  });
}
