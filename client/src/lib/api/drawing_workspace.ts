import type {
  DrawingAlignmentsResponse,
  DrawingComparisonWorkspaceResponse,
  DrawingDiffsResponse,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

import { requestJson } from "@/lib/api/http";

export async function fetchMasterDrawing(
  projectId: number,
  drawingId: number,
  page?: number
): Promise<DrawingWorkspaceDrawing> {
  let path = `/api/projects/${projectId}/drawings/${drawingId}`;
  if (page != null && page >= 1) {
    path += `?page=${encodeURIComponent(String(page))}`;
  }
  return requestJson<DrawingWorkspaceDrawing>(path);
}

export async function fetchMasterDrawingAlignments(
  projectId: number,
  drawingId: number
): Promise<DrawingAlignmentsResponse> {
  return requestJson<DrawingAlignmentsResponse>(
    `/api/projects/${projectId}/drawings/${drawingId}/alignments`
  );
}

export async function fetchAlignmentDiffs(
  projectId: number,
  drawingId: number,
  alignmentId: number
): Promise<DrawingDiffsResponse> {
  const path = `/api/projects/${projectId}/drawings/${drawingId}/diffs?alignment_id=${encodeURIComponent(String(alignmentId))}`;
  return requestJson<DrawingDiffsResponse>(path);
}

export async function compareSubDrawing(
  projectId: number,
  drawingId: number,
  subDrawingId: number
): Promise<DrawingComparisonWorkspaceResponse> {
  return requestJson<DrawingComparisonWorkspaceResponse>(
    `/api/projects/${projectId}/drawings/compare/${drawingId}/${subDrawingId}`,
    { method: "POST" }
  );
}

/** POST compare — route master + chosen sub, aligned with backend naming. */
export async function compareSubDrawingToMaster(params: {
  projectId: number;
  masterDrawingId: number;
  subDrawingId: number;
}): Promise<DrawingComparisonWorkspaceResponse> {
  return compareSubDrawing(
    params.projectId,
    params.masterDrawingId,
    params.subDrawingId
  );
}
