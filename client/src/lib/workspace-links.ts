import type { WorkspaceLinkMetadata } from "@shared/schema";

export type WorkspaceLinkInput = {
  projectId: number;
  masterDrawingId: number;
  alignmentId?: number | null;
  diffId?: number | null;
};

export function buildWorkspaceUrl({
  projectId,
  masterDrawingId,
  alignmentId,
  diffId,
}: WorkspaceLinkInput): string {
  const params = new URLSearchParams();

  if (alignmentId != null) {
    params.set("alignmentId", String(alignmentId));
  }

  if (diffId != null) {
    params.set("diffId", String(diffId));
  }

  const query = params.toString();

  return `/projects/${projectId}/drawings/${masterDrawingId}/workspace${
    query ? `?${query}` : ""
  }`;
}

/** Map API workspace metadata into {@link buildWorkspaceUrl}. */
export function buildWorkspaceUrlFromMetadata(meta: WorkspaceLinkMetadata): string {
  return buildWorkspaceUrl({
    projectId: meta.projectId,
    masterDrawingId: meta.masterDrawingId,
    alignmentId: meta.alignmentId,
    diffId: meta.diffId,
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
    alignmentId: input.alignmentId,
    diffId: input.diffId,
  });
  if (findingId == null || String(findingId) === "") {
    return base;
  }
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}findingId=${encodeURIComponent(String(findingId))}`;
}

/** Picker route when there is no master drawing / diff context. */
export function buildDrawingPickerUrl(
  projectId: number,
  findingId?: string | number | null,
): string {
  if (findingId == null || String(findingId) === "") {
    return `/projects/${projectId}/drawings`;
  }
  return `/projects/${projectId}/drawings?findingId=${encodeURIComponent(String(findingId))}`;
}
