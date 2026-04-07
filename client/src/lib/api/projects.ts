import type { DashboardSummaryResponse } from "@shared/schema";

import { readApiError } from "@/lib/api/http";

export type FetchProjectDashboardSummaryOptions = {
  /** Scopes comparison KPIs to this master drawing (query `currentDrawingId`). */
  currentDrawingId?: number;
  /** Passed as `user_id` for Procore company context on the dashboard. */
  userId?: string | null;
};

/**
 * GET /api/projects/{project_id}/dashboard/summary
 *
 * When `currentDrawingId` is set, the backend scopes comparison progress to that master
 * and returns `current_drawing` in the payload when the id belongs to the project.
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

  const response = await fetch(url, {
    method: "GET",
    credentials: "include",
  });

  if (!response.ok) {
    await readApiError(response);
  }

  return (await response.json()) as DashboardSummaryResponse;
}
