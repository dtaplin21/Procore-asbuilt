import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";
import type { DrawingDiffResponse, DrawingDiffsListResponse } from "@shared/schema";

import { runDrawingDiff } from "@/lib/api/drawing_diffs";
import { getQueryFn } from "@/lib/queryClient";

/**
 * Stable React Query key for GET drawing diffs (see `useDrawingDiffs`).
 * Use `invalidateDrawingDiffsQueries` after POST run-diff so list consumers refetch.
 *
 * Note: `useDrawingWorkspace` keeps diffs in React state (fetch), not this key — refresh
 * that UI via `reloadSelectedDiffs` / `onRerunComplete` on the alignments panel.
 */
export function drawingDiffsQueryKey(
  projectId: number,
  masterDrawingId: number,
  alignmentId: number | null
) {
  return [
    "drawing-diffs",
    projectId,
    masterDrawingId,
    alignmentId ?? "all",
  ] as const;
}

/** Invalidate every cached GET diffs list for this project + master drawing (all alignment filters). */
export function invalidateDrawingDiffsQueries(
  queryClient: QueryClient,
  projectId: number,
  masterDrawingId: number
) {
  void queryClient.invalidateQueries({
    queryKey: ["drawing-diffs", projectId, masterDrawingId],
  });
}

/**
 * Fetch drawing diffs for a master drawing.
 * Cache key includes alignmentId so filtered vs unfiltered results are cached separately.
 *
 * Endpoint: GET /api/projects/${projectId}/drawings/${masterDrawingId}/diffs
 * Query param: ?alignment_id=X (optional)
 */
export function useDrawingDiffs(
  projectId: number | null,
  masterDrawingId: number | null,
  alignmentId: number | null
) {
  const url =
    projectId != null && masterDrawingId != null
      ? `/api/projects/${projectId}/drawings/${masterDrawingId}/diffs${alignmentId != null ? `?alignment_id=${alignmentId}` : ""}`
      : "";

  const queryFn = getQueryFn<DrawingDiffsListResponse>({ on401: "throw" });

  return useQuery<DrawingDiffsListResponse>({
    queryKey:
      projectId != null && masterDrawingId != null
        ? drawingDiffsQueryKey(projectId, masterDrawingId, alignmentId)
        : ["drawing-diffs", "disabled"],
    queryFn: (ctx) => queryFn({ ...ctx, queryKey: [url] }),
    enabled: projectId != null && masterDrawingId != null && !!url,
  });
}

/**
 * Variables for `mutate` / `mutateAsync` only. `projectId` and `masterDrawingId` are **not**
 * passed here — they are fixed when you call `useRunDrawingDiff(projectId, masterDrawingId)`.
 * Mapping to `alignment_id` happens in {@link runDrawingDiff} (API layer).
 */
export type RunDrawingDiffMutationVariables = {
  alignmentId: number;
};

/**
 * Run the diff pipeline for an alignment.
 * POST /api/projects/${projectId}/drawings/${masterDrawingId}/diffs
 * Body: RunDrawingDiffRequest
 *
 * On success, invalidates `drawing-diffs` queries for this project + master drawing so
 * `useDrawingDiffs` refetches. Broad enough for MVP; narrows to same drawing as the POST.
 *
 * **Usage**:
 * ```ts
 * const { mutateAsync } = useRunDrawingDiff(projectId, masterDrawingId);
 * await mutateAsync({ alignmentId });
 * ```
 */
export function useRunDrawingDiff(
  projectId: number | null,
  masterDrawingId: number | null
): UseMutationResult<
  DrawingDiffResponse[],
  Error,
  RunDrawingDiffMutationVariables
> {
  const queryClient = useQueryClient();

  return useMutation<
    DrawingDiffResponse[],
    Error,
    RunDrawingDiffMutationVariables
  >({
    mutationFn: async ({ alignmentId }) => {
      if (projectId == null || masterDrawingId == null) {
        throw new Error("Project and master drawing required");
      }
      return runDrawingDiff({
        projectId,
        masterDrawingId,
        alignmentId,
      });
    },
    onSuccess: () => {
      if (projectId != null && masterDrawingId != null) {
        invalidateDrawingDiffsQueries(queryClient, projectId, masterDrawingId);
      }
    },
  });
}
