import type { WorkspaceLinkMetadata } from "@shared/schema";

import { objectsPagePath } from "@/lib/objectsRoute";

export type WorkspaceLinkInput = {
  projectId: number;
  masterDrawingId: number;
  inspectionRunId?: number | null;
  overlayId?: number | null;
};

/** Master drawing surface on the Objects page with optional run + overlay selection. */
export function buildWorkspaceUrl({
  projectId,
  masterDrawingId,
  inspectionRunId,
  overlayId,
}: WorkspaceLinkInput): string {
  return objectsPagePath(
    String(projectId),
    String(masterDrawingId),
    inspectionRunId != null ? String(inspectionRunId) : null,
    overlayId != null ? String(overlayId) : null,
  );
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
 * Same as {@link buildWorkspaceUrl}, plus optional finding focus in the query string.
 * Use when the workspace supports highlighting a finding via `findingId`.
 */
export function buildWorkspaceUrlWithFinding(
  input: WorkspaceLinkInput | WorkspaceLinkMetadata,
  findingId: string | number | null | undefined,
): string {
  const base = buildWorkspaceUrl({
    projectId: input.projectId,
    masterDrawingId: input.masterDrawingId,
    inspectionRunId:
      "inspectionRunId" in input ? input.inspectionRunId : undefined,
    overlayId: "overlayId" in input ? input.overlayId : undefined,
  });
  if (findingId == null || String(findingId) === "") {
    return base;
  }
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}findingId=${encodeURIComponent(String(findingId))}`;
}

/** When the project already has a canonical master, this route usually redirects to the workspace; use only when `masterDrawingId` is still unset. */
export function buildDrawingPickerUrl(
  projectId: number,
  findingId?: string | number | null,
): string {
  if (findingId == null || String(findingId) === "") {
    return `/projects/${projectId}/drawings`;
  }
  return `/projects/${projectId}/drawings?findingId=${encodeURIComponent(String(findingId))}`;
}
