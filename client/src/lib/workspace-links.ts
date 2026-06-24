import type { WorkspaceLinkMetadata } from "@shared/schema";

export type WorkspaceLinkInput = {
  projectId: number;
  masterDrawingId: number;
  /** Legacy compare selection — ignored when building workspace URLs (PR1). */
  alignmentId?: number | null;
  /** Legacy compare selection — ignored when building workspace URLs (PR1). */
  diffId?: number | null;
};

/** Master workspace route only; does not deep-link into removed compare UI state. */
export function buildWorkspaceUrl({
  projectId,
  masterDrawingId,
}: WorkspaceLinkInput): string {
  return `/projects/${projectId}/drawings/${masterDrawingId}/workspace`;
}

/** Map API workspace metadata into {@link buildWorkspaceUrl}. Compare selection fields are dropped. */
export function buildWorkspaceUrlFromMetadata(meta: WorkspaceLinkMetadata): string {
  return buildWorkspaceUrl({
    projectId: meta.projectId,
    masterDrawingId: meta.masterDrawingId,
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
