/**
 * React Query hooks for drawing regions — CRUD (PR2) for the region editor
 * (PR3) and the inspection summary query for Objects' region layer (PR4).
 * use-region-inspection-summary.ts re-exports the summary hook from here.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createDrawingRegion,
  deleteDrawingRegion,
  drawingRegionsQueryKey,
  fetchDrawingRegions,
  fetchRegionInspectionSummary,
  regionInspectionSummaryQueryKey,
  updateDrawingRegion,
} from "@/lib/api/drawing_regions";
import type {
  CreateDrawingRegionInput,
  DrawingRegion,
  RegionInspectionSummaryEntry,
  UpdateDrawingRegionInput,
} from "@/lib/drawing-regions/types";

export {
  drawingRegionsQueryKey,
  regionInspectionSummaryQueryKey,
} from "@/lib/api/drawing_regions";

export type DrawingRegionsScope = {
  projectId: number | string | null | undefined;
  masterDrawingId: number | string | null | undefined;
};

function isScopeEnabled(scope: DrawingRegionsScope): boolean {
  if (scope.projectId == null || scope.masterDrawingId == null) {
    return false;
  }
  const projectId = Number(scope.projectId);
  const masterDrawingId = Number(scope.masterDrawingId);
  return (
    Number.isFinite(projectId) &&
    projectId > 0 &&
    Number.isFinite(masterDrawingId) &&
    masterDrawingId > 0
  );
}

export function useDrawingRegions(scope: DrawingRegionsScope) {
  const projectId = scope.projectId ?? "";
  const masterDrawingId = scope.masterDrawingId ?? "";

  return useQuery<DrawingRegion[]>({
    queryKey: drawingRegionsQueryKey(projectId, masterDrawingId),
    queryFn: () =>
      fetchDrawingRegions({
        projectId,
        masterDrawingId,
      }),
    enabled: isScopeEnabled(scope),
  });
}

export function useRegionInspectionSummary(scope: DrawingRegionsScope) {
  const projectId = scope.projectId ?? "";
  const masterDrawingId = scope.masterDrawingId ?? "";

  return useQuery<RegionInspectionSummaryEntry[]>({
    queryKey: regionInspectionSummaryQueryKey(projectId, masterDrawingId),
    queryFn: async () => {
      const response = await fetchRegionInspectionSummary({
        projectId,
        masterDrawingId,
      });
      return response.items;
    },
    enabled: isScopeEnabled(scope),
    staleTime: 60_000,
  });
}

type MutationScope = {
  projectId: number | string;
  masterDrawingId: number | string;
};

export function useCreateDrawingRegion(scope: MutationScope) {
  const queryClient = useQueryClient();
  const { projectId, masterDrawingId } = scope;

  return useMutation<DrawingRegion, Error, CreateDrawingRegionInput>({
    mutationFn: (input) =>
      createDrawingRegion({
        projectId,
        masterDrawingId,
        body: input,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: drawingRegionsQueryKey(projectId, masterDrawingId),
      });
      queryClient.invalidateQueries({
        queryKey: regionInspectionSummaryQueryKey(projectId, masterDrawingId),
      });
    },
  });
}

export function useUpdateDrawingRegion(scope: MutationScope) {
  const queryClient = useQueryClient();
  const { projectId, masterDrawingId } = scope;

  return useMutation<
    DrawingRegion,
    Error,
    { regionId: number | string; input: UpdateDrawingRegionInput }
  >({
    mutationFn: ({ regionId, input }) =>
      updateDrawingRegion({
        projectId,
        masterDrawingId,
        regionId,
        body: input,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: drawingRegionsQueryKey(projectId, masterDrawingId),
      });
      queryClient.invalidateQueries({
        queryKey: regionInspectionSummaryQueryKey(projectId, masterDrawingId),
      });
    },
  });
}

export function useDeleteDrawingRegion(scope: MutationScope) {
  const queryClient = useQueryClient();
  const { projectId, masterDrawingId } = scope;

  return useMutation<void, Error, number | string>({
    mutationFn: (regionId) =>
      deleteDrawingRegion({
        projectId,
        masterDrawingId,
        regionId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: drawingRegionsQueryKey(projectId, masterDrawingId),
      });
      queryClient.invalidateQueries({
        queryKey: regionInspectionSummaryQueryKey(projectId, masterDrawingId),
      });
    },
  });
}
