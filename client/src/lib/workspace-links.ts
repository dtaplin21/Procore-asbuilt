/**
 * Per the merge plan (Phase 1): buildWorkspaceUrl / buildWorkspaceUrlWithFinding
 * now build Objects URLs instead of /workspace URLs. The function NAMES are
 * kept as aliases during migration so every existing call site (dashboard,
 * drawing picker, drawing library, ai-insight-card, etc.) keeps working
 * without an immediate rename — only the URL they produce changes.
 *
 * New code should prefer calling objectsPagePath directly from
 * lib/objectsRoute.ts; these wrappers exist for the migration window and
 * can be deleted once every call site has been repointed (see merge plan
 * Phase 4/5 — "Dashboard / insights / drawing picker — all deep links →
 * Objects").
 */

import type { WorkspaceLinkMetadata } from "@shared/schema";

import { objectsPagePath } from "@/lib/objectsRoute";

/** @deprecated Prefer string args or objectsPagePath() during migration. */
export type WorkspaceLinkInput = {
  projectId: number;
  masterDrawingId: number;
  inspectionRunId?: number | null;
  overlayId?: number | null;
};

/**
 * @deprecated Prefer objectsPagePath() directly. Kept as a migration
 * alias — same signature shape as the old workspace-URL builder, but now
 * returns an Objects URL.
 */
export function buildWorkspaceUrl(projectId: string, drawingId: string): string;
export function buildWorkspaceUrl(input: WorkspaceLinkInput): string;
export function buildWorkspaceUrl(
  projectIdOrInput: string | WorkspaceLinkInput,
  drawingId?: string,
): string {
  if (typeof projectIdOrInput === "object") {
    return objectsPagePath(
      String(projectIdOrInput.projectId),
      String(projectIdOrInput.masterDrawingId),
      projectIdOrInput.inspectionRunId != null
        ? String(projectIdOrInput.inspectionRunId)
        : null,
      projectIdOrInput.overlayId != null
        ? String(projectIdOrInput.overlayId)
        : null,
    );
  }
  return objectsPagePath(projectIdOrInput, drawingId ?? "");
}

/** Map API workspace metadata into {@link buildWorkspaceUrl}. */
export function buildWorkspaceUrlFromMetadata(meta: WorkspaceLinkMetadata): string {
  return buildWorkspaceUrl({
    projectId: meta.projectId,
    masterDrawingId: meta.masterDrawingId,
    inspectionRunId: meta.inspectionRunId,
    overlayId: meta.overlayId,
  });
}

/**
 * @deprecated Prefer objectsPagePath() directly. "Finding" in the old
 * sub-drawing-compare model maps to "overlay" in the inspection-on-master
 * model — this wrapper accepts the old `findingId` parameter name and
 * forwards it as the overlay id.
 */
export function buildWorkspaceUrlWithFinding(
  projectId: string,
  drawingId: string,
  findingId: string,
): string;
export function buildWorkspaceUrlWithFinding(
  input: WorkspaceLinkInput | WorkspaceLinkMetadata,
  findingId: string | number | null | undefined,
): string;
export function buildWorkspaceUrlWithFinding(
  projectIdOrInput: string | WorkspaceLinkInput | WorkspaceLinkMetadata,
  drawingIdOrFindingId?: string | number | null,
  findingId?: string | number | null,
): string {
  if (typeof projectIdOrInput === "object") {
    const input = projectIdOrInput;
    const overlayId =
      drawingIdOrFindingId == null || String(drawingIdOrFindingId) === ""
        ? null
        : String(drawingIdOrFindingId);
    return objectsPagePath(
      String(input.projectId),
      String(input.masterDrawingId),
      input.inspectionRunId != null ? String(input.inspectionRunId) : null,
      overlayId ?? (input.overlayId != null ? String(input.overlayId) : null),
    );
  }

  const overlay =
    findingId == null || String(findingId) === "" ? null : String(findingId);
  return objectsPagePath(
    projectIdOrInput,
    String(drawingIdOrFindingId ?? ""),
    null,
    overlay,
  );
}

/** Prefer this over buildWorkspaceUrlWithFinding in new call sites. */
export function buildObjectsUrlWithRun(
  projectId: string,
  drawingId: string,
  runId: string,
): string {
  return objectsPagePath(projectId, drawingId, runId);
}

export function buildObjectsUrlWithOverlay(
  projectId: string,
  drawingId: string,
  runId: string,
  overlayId: string,
): string {
  return objectsPagePath(projectId, drawingId, runId, overlayId);
}

/** When the project already has a canonical master, this route usually redirects to Objects; use only when `masterDrawingId` is still unset. */
export function buildDrawingPickerUrl(
  projectId: number,
  findingId?: string | number | null,
): string {
  if (findingId == null || String(findingId) === "") {
    return `/projects/${projectId}/drawings`;
  }
  return `/projects/${projectId}/drawings?findingId=${encodeURIComponent(String(findingId))}`;
}
