import type {
  DrawingIndexStatusResponse,
  DrawingReindexResponse,
} from "@/lib/drawing-index/format_index_summary";

import { requestJson } from "@/lib/api/http";
import {
  coerceDrawingIdForApi,
  coerceProjectIdForApi,
} from "@/lib/api/route_ids";

export function drawingIndexStatusQueryKey(
  projectId: number,
  drawingId: number,
): readonly ["drawing-index-status", number, number] {
  return ["drawing-index-status", projectId, drawingId];
}

export async function fetchDrawingIndexStatus(
  projectId: number | string,
  drawingId: number | string,
): Promise<DrawingIndexStatusResponse> {
  const pid = coerceProjectIdForApi(projectId);
  const did = coerceDrawingIdForApi(drawingId);
  return requestJson<DrawingIndexStatusResponse>(
    `/api/projects/${pid}/drawings/${did}/index-status`,
  );
}

export async function reindexDrawing(
  projectId: number | string,
  drawingId: number | string,
): Promise<DrawingReindexResponse> {
  const pid = coerceProjectIdForApi(projectId);
  const did = coerceDrawingIdForApi(drawingId);
  return requestJson<DrawingReindexResponse>(
    `/api/projects/${pid}/drawings/${did}/reindex`,
    { method: "POST" },
  );
}
