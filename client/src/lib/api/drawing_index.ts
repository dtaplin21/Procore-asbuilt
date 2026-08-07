import type {
  DrawingIndexStatusResponse,
  DrawingReindexResponse,
} from "@/lib/drawing-index/format_index_summary";

import { requestJson } from "@/lib/api/http";
import {
  coerceDrawingIdForApi,
  coerceProjectIdForApi,
} from "@/lib/api/route_ids";

export interface DrawingSurveyPointRecord {
  id: number;
  northing: number;
  easting: number;
  station: string | null;
  structure_label: string | null;
  label_bbox_json: Record<string, number>;
  page: number;
  source: string;
}

export interface DrawingSurveyPointListResponse {
  items: DrawingSurveyPointRecord[];
  total: number;
  page: number;
  limit: number;
}

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

/** Dev/debug: indexed N/E survey points for coordinate matching on a drawing page. */
export async function fetchDrawingSurveyPoints(
  projectId: number | string,
  drawingId: number | string,
  options?: { page?: number; limit?: number },
): Promise<DrawingSurveyPointListResponse> {
  const pid = coerceProjectIdForApi(projectId);
  const did = coerceDrawingIdForApi(drawingId);
  const params = new URLSearchParams({
    page: String(options?.page ?? 1),
    limit: String(options?.limit ?? 500),
  });
  return requestJson<DrawingSurveyPointListResponse>(
    `/api/projects/${pid}/drawings/${did}/survey-points?${params.toString()}`,
  );
}
