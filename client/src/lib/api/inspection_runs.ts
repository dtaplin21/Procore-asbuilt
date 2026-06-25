import type { QueryClient } from "@tanstack/react-query";
import type {
  DrawingOverlay,
  InspectionRun,
  InspectionRunEvidenceUploadResponse,
  RunInspectionRequest,
} from "@shared/schema";

import { readApiError, requestJson, resolveFetchUrl } from "@/lib/api/http";

export function buildDrawingOverlaysUrl(
  projectId: number,
  drawingId: number,
  filters?: { inspectionRunId?: number | null; diffId?: number | null }
): string {
  const params = new URLSearchParams();
  if (filters?.inspectionRunId != null) {
    params.set("inspection_run_id", String(filters.inspectionRunId));
  }
  if (filters?.diffId != null) {
    params.set("diff_id", String(filters.diffId));
  }
  const query = params.toString();
  return `/api/projects/${projectId}/drawings/${drawingId}/overlays${query ? `?${query}` : ""}`;
}

export async function fetchDrawingOverlays(
  projectId: number,
  drawingId: number,
  filters?: { inspectionRunId?: number | null; diffId?: number | null }
): Promise<DrawingOverlay[]> {
  return requestJson<DrawingOverlay[]>(buildDrawingOverlaysUrl(projectId, drawingId, filters));
}

export async function createInspectionRun(
  projectId: number,
  body: RunInspectionRequest
): Promise<InspectionRun> {
  const response = await fetch(
    resolveFetchUrl(`/api/projects/${projectId}/inspections/runs`),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      credentials: "include",
      body: JSON.stringify({
        master_drawing_id: body.master_drawing_id,
        evidence_id: body.evidence_id ?? null,
        inspection_type: body.inspection_type ?? null,
        skip_pipeline: body.skip_pipeline ?? false,
      }),
    }
  );
  if (!response.ok) {
    await readApiError(response);
  }
  return response.json() as Promise<InspectionRun>;
}

/**
 * POST /api/projects/{project_id}/inspections/runs/{run_id}/evidence
 * Multipart file upload — runs document pipeline and persists overlays.
 */
export async function uploadInspectionRunEvidence(
  projectId: number,
  inspectionRunId: number,
  file: File
): Promise<InspectionRunEvidenceUploadResponse> {
  if (!(file instanceof File)) {
    throw new TypeError("uploadInspectionRunEvidence requires a File instance");
  }

  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    resolveFetchUrl(
      `/api/projects/${projectId}/inspections/runs/${inspectionRunId}/evidence`
    ),
    {
      method: "POST",
      credentials: "include",
      body: formData,
    }
  );

  if (!response.ok) {
    await readApiError(response);
  }

  return response.json() as Promise<InspectionRunEvidenceUploadResponse>;
}

export function invalidateDrawingOverlayQueries(
  queryClient: QueryClient,
  projectId: number,
  drawingId: number
): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (query) => {
      const key = query.queryKey[0];
      return (
        typeof key === "string" &&
        key.includes(`/api/projects/${projectId}/drawings/${drawingId}/overlays`)
      );
    },
  });
}

export async function refreshInspectionWorkspaceQueries(
  queryClient: QueryClient,
  projectId: number,
  masterDrawingId: number
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({
      predicate: (query) => {
        const key = query.queryKey[0];
        return (
          typeof key === "string" &&
          key.includes(`/api/projects/${projectId}/inspections/runs`) &&
          key.includes(`master_drawing_id=${masterDrawingId}`)
        );
      },
    }),
    invalidateDrawingOverlayQueries(queryClient, projectId, masterDrawingId),
  ]);
}
