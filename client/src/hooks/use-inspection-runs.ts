import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  InspectionRun,
  InspectionRunListResponse,
  DrawingOverlay,
  RunInspectionRequest,
} from "@shared/schema";

/**
 * Fetch inspection runs for a project.
 * GET /api/projects/${projectId}/inspections/runs
 * Query params: master_drawing_id, status (optional)
 */
export function useInspectionRuns(
  projectId: string | null,
  filters?: { masterDrawingId?: number | null; status?: string | null }
) {
  const params = new URLSearchParams();
  if (filters?.masterDrawingId != null) {
    params.set("master_drawing_id", String(filters.masterDrawingId));
  }
  if (filters?.status) {
    params.set("status", filters.status);
  }
  const query = params.toString();
  const url =
    projectId && projectId !== ""
      ? `/api/projects/${projectId}/inspections/runs${query ? `?${query}` : ""}`
      : "";

  return useQuery<InspectionRunListResponse>({
    queryKey: [url],
    enabled: !!projectId && !!url,
  });
}

/**
 * Run the inspection mapping pipeline.
 * POST /api/projects/${projectId}/inspections/runs
 * Body: { master_drawing_id, evidence_id?, inspection_type? }
 *
 * Invalidates inspection runs and overlays queries on success.
 */
export function useRunInspection(projectId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<InspectionRun, Error, RunInspectionRequest>({
    mutationFn: async (body) => {
      if (!projectId) {
        throw new Error("Project required");
      }
      const url = `/api/projects/${projectId}/inspections/runs`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          master_drawing_id: body.master_drawing_id,
          evidence_id: body.evidence_id ?? null,
          inspection_type: body.inspection_type ?? null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          typeof err.detail === "string" ? err.detail : "Failed to run inspection"
        );
      }
      return res.json();
    },
    onSuccess: (_, variables) => {
      if (projectId) {
        queryClient.invalidateQueries({
          predicate: (query) => {
            const key = query.queryKey[0];
            return (
              typeof key === "string" &&
              key.includes(`/api/projects/${projectId}/inspections/runs`)
            );
          },
        });
        queryClient.invalidateQueries({
          predicate: (query) => {
            const key = query.queryKey[0];
            return (
              typeof key === "string" &&
              key.includes(`/api/projects/${projectId}/drawings/${variables.master_drawing_id}/overlays`)
            );
          },
        });
      }
    },
  });
}

/**
 * Fetch drawing overlays for a master drawing.
 * GET /api/projects/${projectId}/drawings/${drawingId}/overlays
 * Query params: inspection_run_id, diff_id (optional)
 */
export function useDrawingOverlays(
  projectId: string | null,
  drawingId: string | null,
  filters?: { inspectionRunId?: number | null; diffId?: number | null }
) {
  const params = new URLSearchParams();
  if (filters?.inspectionRunId != null) {
    params.set("inspection_run_id", String(filters.inspectionRunId));
  }
  if (filters?.diffId != null) {
    params.set("diff_id", String(filters.diffId));
  }
  const query = params.toString();
  const url =
    projectId && drawingId
      ? `/api/projects/${projectId}/drawings/${drawingId}/overlays${query ? `?${query}` : ""}`
      : "";

  return useQuery<DrawingOverlay[]>({
    queryKey: [url],
    enabled: !!projectId && !!drawingId && !!url,
  });
}
