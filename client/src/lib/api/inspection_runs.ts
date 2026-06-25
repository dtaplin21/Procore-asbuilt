import type { QueryClient } from "@tanstack/react-query";
import type {
  InspectionRunEvidenceUploadResponse,
  RunInspectionRequest,
} from "@shared/schema";

import {
  createInspectionRun as createInspectionRunApi,
  uploadInspectionRunEvidence as uploadInspectionRunEvidenceApi,
} from "@/lib/api/inspections";
import { invalidateOverlaysForDrawing } from "@/lib/api/overlays";

/** @deprecated Prefer `@/lib/api/inspections` — kept for existing hook imports. */
export async function createInspectionRun(
  projectId: number,
  body: RunInspectionRequest,
) {
  const run = await createInspectionRunApi({
    projectId: String(projectId),
    masterDrawingId: String(body.master_drawing_id),
    skipPipeline: body.skip_pipeline ?? false,
  });
  return {
    id: Number(run.id),
    project_id: Number(run.projectId),
    master_drawing_id: Number(run.masterDrawingId),
    evidence_id: body.evidence_id ?? null,
    inspection_type: body.inspection_type ?? null,
    status: run.status,
    started_at: null,
    completed_at: null,
    error_message: null,
    created_at: run.createdAt,
    updated_at: run.createdAt,
  } satisfies import("@shared/schema").InspectionRun;
}

/** @deprecated Prefer `@/lib/api/inspections` — kept for existing hook imports. */
export async function uploadInspectionRunEvidence(
  projectId: number,
  inspectionRunId: number,
  file: File,
  masterDrawingId: number,
): Promise<InspectionRunEvidenceUploadResponse> {
  const response = await uploadInspectionRunEvidenceApi({
    projectId: String(projectId),
    runId: String(inspectionRunId),
    masterDrawingId: String(masterDrawingId),
    file,
  });
  return {
    evidence_id: Number(response.evidence_id),
    overlays_created: response.overlays_created,
    unresolved_count: response.unresolved_count,
    untagged_region_count: response.untagged_region_count,
    overlay_ids: response.overlay_ids.map(Number),
  };
}

export function invalidateDrawingOverlayQueries(
  queryClient: QueryClient,
  _projectId: number,
  drawingId: number
): Promise<void> {
  invalidateOverlaysForDrawing(queryClient, String(drawingId));
  return Promise.resolve();
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
