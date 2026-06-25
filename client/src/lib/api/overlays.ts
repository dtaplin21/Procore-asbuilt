import type { QueryClient } from "@tanstack/react-query";
import type { DrawingOverlay, InspectionRunListResponse } from "@shared/schema";

import { requestJson } from "@/lib/api/http";

export function overlaysQueryKey(drawingId: string, runId?: string | null) {
  return ["drawing-overlays", drawingId, runId ?? "latest"] as const;
}

export function buildDrawingOverlaysUrl(
  projectId: number,
  drawingId: number,
  filters?: { inspectionRunId?: number | string | null },
): string {
  const params = new URLSearchParams();
  if (filters?.inspectionRunId != null) {
    params.set("inspection_run_id", String(filters.inspectionRunId));
  }
  const query = params.toString();
  return `/api/projects/${projectId}/drawings/${drawingId}/overlays${query ? `?${query}` : ""}`;
}

export async function fetchDrawingOverlays(params: {
  projectId: string;
  drawingId: string;
  inspectionRunId: string;
}): Promise<DrawingOverlay[]> {
  const projectId = Number(params.projectId);
  const drawingId = Number(params.drawingId);
  if (!Number.isFinite(projectId) || !Number.isFinite(drawingId)) {
    return [];
  }
  return requestJson<DrawingOverlay[]>(
    buildDrawingOverlaysUrl(projectId, drawingId, {
      inspectionRunId: params.inspectionRunId,
    }),
  );
}

export async function fetchLatestRunOverlays(
  projectId: string,
  drawingId: string,
): Promise<DrawingOverlay[]> {
  const pid = Number(projectId);
  const did = Number(drawingId);
  if (!Number.isFinite(pid) || !Number.isFinite(did)) {
    return [];
  }

  const params = new URLSearchParams({
    master_drawing_id: String(did),
    status: "complete",
    limit: "1",
  });
  const runs = await requestJson<InspectionRunListResponse>(
    `/api/projects/${pid}/inspections/runs?${params.toString()}`,
  );
  const latest = runs.items[0];
  if (!latest?.id) {
    return [];
  }

  return fetchDrawingOverlays({
    projectId,
    drawingId,
    inspectionRunId: String(latest.id),
  });
}

export function invalidateOverlaysForRun(
  queryClient: QueryClient,
  drawingId: string,
  runId: string,
): void {
  queryClient.invalidateQueries({ queryKey: overlaysQueryKey(drawingId, runId) });
  queryClient.invalidateQueries({ queryKey: overlaysQueryKey(drawingId, null) });
}

export function invalidateOverlaysForDrawing(
  queryClient: QueryClient,
  drawingId: string,
): void {
  queryClient.invalidateQueries({ queryKey: ["drawing-overlays", drawingId] });
}
