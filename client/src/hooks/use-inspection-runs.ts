import { useMutation, useQuery, useQueryClient, type Query } from "@tanstack/react-query";
import type {
  DrawingOverlay,
  InspectionRun,
  InspectionRunListResponse,
  InspectionRunEvidenceUploadResponse,
  RunInspectionRequest,
} from "@shared/schema";

import {
  createInspectionRun,
  refreshInspectionWorkspaceQueries,
  uploadInspectionRunEvidence,
} from "@/lib/api/inspection_runs";
import {
  fetchDrawingOverlays,
  fetchLatestRunOverlays,
  invalidateOverlaysForRun,
  overlaysQueryKey,
} from "@/lib/api/overlays";
import { requestJson, resolveFetchUrl } from "@/lib/api/http";

export type InspectionRunsFilters = {
  masterDrawingId?: number | null;
  status?: string | null;
};

/** Canonical GET path for inspection runs — shared by sidebar, writeback, and invalidation. */
export function buildInspectionRunsUrl(
  projectId: number,
  filters?: InspectionRunsFilters
): string {
  const params = new URLSearchParams();
  if (filters?.masterDrawingId != null) {
    params.set("master_drawing_id", String(filters.masterDrawingId));
  }
  if (filters?.status) {
    params.set("status", filters.status);
  }
  const query = params.toString();
  return `/api/projects/${projectId}/inspections/runs${query ? `?${query}` : ""}`;
}

/** React Query key for inspection runs list queries. */
export function inspectionRunsQueryKey(
  projectId: number,
  filters?: InspectionRunsFilters
): readonly [string] {
  return [buildInspectionRunsUrl(projectId, filters)];
}

export async function fetchInspectionRuns(
  projectId: number,
  filters?: InspectionRunsFilters
): Promise<InspectionRunListResponse> {
  return requestJson<InspectionRunListResponse>(
    buildInspectionRunsUrl(projectId, filters)
  );
}

export function useInspectionRuns(
  projectId: number | null,
  filters?: InspectionRunsFilters,
  options?: {
    refetchInterval?:
      | number
      | false
      | ((
          query: Query<InspectionRunListResponse, Error>
        ) => number | false | undefined);
  }
) {
  const url =
    projectId != null ? buildInspectionRunsUrl(projectId, filters) : "";

  return useQuery<InspectionRunListResponse>({
    queryKey: [url],
    queryFn: () => fetchInspectionRuns(projectId as number, filters),
    enabled: !!projectId && !!url,
    refetchInterval: options?.refetchInterval,
  });
}

/**
 * Legacy LLM inspection mapping pipeline (POST /inspections/runs with evidence_id).
 */
export function useRunInspection(projectId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<InspectionRun, Error, RunInspectionRequest>({
    mutationFn: async (body) => {
      if (!projectId) {
        throw new Error("Project required");
      }
      const url = resolveFetchUrl(`/api/projects/${projectId}/inspections/runs`);
      const res = await fetch(url, {
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
        const pid = Number(projectId);
        void refreshInspectionWorkspaceQueries(
          queryClient,
          pid,
          variables.master_drawing_id
        );
      }
    },
  });
}

export function useCreateInspectionRun(projectId: number | null) {
  return useMutation<InspectionRun, Error, RunInspectionRequest>({
    mutationFn: (body) => {
      if (projectId == null) {
        throw new Error("Project required");
      }
      return createInspectionRun(projectId, body);
    },
  });
}

export type UploadInspectionRunEvidenceVariables = {
  inspectionRunId: number;
  file: File;
  masterDrawingId: number;
};

/**
 * Document pipeline upload: POST .../inspections/runs/{run_id}/evidence
 */
export function useUploadInspectionRunEvidence(projectId: number | null) {
  const queryClient = useQueryClient();

  return useMutation<
    InspectionRunEvidenceUploadResponse,
    Error,
    UploadInspectionRunEvidenceVariables
  >({
    mutationFn: async ({ inspectionRunId, file, masterDrawingId }) => {
      if (projectId == null) {
        throw new Error("Project required");
      }
      return uploadInspectionRunEvidence(
        projectId,
        inspectionRunId,
        file,
        masterDrawingId,
      );
    },
    onSuccess: (_, variables) => {
      if (projectId != null) {
        invalidateOverlaysForRun(
          queryClient,
          String(variables.masterDrawingId),
          String(variables.inspectionRunId),
        );
        void refreshInspectionWorkspaceQueries(
          queryClient,
          projectId,
          variables.masterDrawingId,
        );
      }
    },
  });
}

export { overlaysQueryKey };

export interface UseDrawingOverlaysOptions {
  projectId: string | undefined;
  drawingId: string | undefined;
  /** Specific run to show overlays for. If omitted/null, shows the
   * latest complete run's overlays (per merge plan Phase 2 default). */
  runId?: string | null;
  enabled?: boolean;
}

export function useDrawingOverlays({
  projectId,
  drawingId,
  runId,
  enabled = true,
}: UseDrawingOverlaysOptions) {
  return useQuery<DrawingOverlay[]>({
    queryKey: overlaysQueryKey(drawingId ?? "", runId),
    queryFn: () => {
      if (!projectId || !drawingId) {
        return Promise.resolve([]);
      }
      return runId
        ? fetchDrawingOverlays({
            projectId,
            drawingId,
            inspectionRunId: runId,
          })
        : fetchLatestRunOverlays(projectId, drawingId);
    },
    enabled: enabled && Boolean(projectId && drawingId),
    staleTime: 60_000,
  });
}

export function useInvalidateOverlaysForRun() {
  const queryClient = useQueryClient();
  return (drawingId: string, runId: string) => {
    invalidateOverlaysForRun(queryClient, drawingId, runId);
  };
}
