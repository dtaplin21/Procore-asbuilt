import type {
  DashboardSummaryResponse,
  DrawingDeleteSummaryResponse,
  JobListResponse,
} from "@shared/schema";

import { apiRequest, readApiError, requestJson, resolveFetchUrl } from "@/lib/api/http";

export type FetchProjectDashboardSummaryOptions = {
  /** Optional workspace master for `current_drawing` context (query `currentDrawingId`). */
  currentDrawingId?: number;
  /** Passed as `user_id` for Procore company context on the dashboard. */
  userId?: string | null;
};

/**
 * GET /api/projects/{project_id}/dashboard/summary
 *
 * KPIs include project-scoped inspection coverage (`inspectionCoverage`) derived from
 * complete rows in `inspection_runs`, not sub-drawing compare counts.
 */
export async function fetchProjectDashboardSummary(
  projectId: number,
  options?: FetchProjectDashboardSummaryOptions
): Promise<DashboardSummaryResponse> {
  const params = new URLSearchParams();

  if (options?.userId != null && options.userId !== "") {
    params.set("user_id", options.userId);
  }

  if (
    typeof options?.currentDrawingId === "number" &&
    Number.isFinite(options.currentDrawingId)
  ) {
    params.set("currentDrawingId", String(options.currentDrawingId));
  }

  const query = params.toString();
  const url = query
    ? `/api/projects/${projectId}/dashboard/summary?${query}`
    : `/api/projects/${projectId}/dashboard/summary`;

  const response = await fetch(resolveFetchUrl(url), {
    method: "GET",
    credentials: "include",
  });

  if (!response.ok) {
    await readApiError(response);
  }

  return (await response.json()) as DashboardSummaryResponse;
}

/**
 * GET /api/projects/{project_id}/drawings/{drawing_id}/delete-summary
 *
 * Read-only impact counts and master context for delete confirmation modals.
 */
export async function fetchDrawingDeleteSummary(
  projectId: number,
  drawingId: number
): Promise<DrawingDeleteSummaryResponse> {
  const response = await fetch(
    resolveFetchUrl(
      `/api/projects/${projectId}/drawings/${drawingId}/delete-summary`
    ),
    { method: "GET", credentials: "include" }
  );

  if (!response.ok) {
    await readApiError(response);
  }

  return (await response.json()) as DrawingDeleteSummaryResponse;
}

/**
 * DELETE /api/projects/{project_id}/drawings/{drawing_id}
 */
export async function deleteProjectDrawing(
  projectId: number,
  drawingId: number
): Promise<void> {
  await apiRequest(
    "DELETE",
    `/api/projects/${projectId}/drawings/${drawingId}`
  );
}

/** GET /api/projects/{project_id}/jobs — optional `status=active` (pending + in-flight). */
export async function fetchProjectJobs(
  projectId: number,
  status?: string
): Promise<JobListResponse> {
  const q =
    status != null && status !== ""
      ? `?status=${encodeURIComponent(status)}`
      : "";
  return requestJson<JobListResponse>(`/api/projects/${projectId}/jobs${q}`);
}
