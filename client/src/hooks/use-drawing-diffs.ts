import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DrawingDiffsListResponse, RunDrawingDiffRequest } from "@shared/schema";

/**
 * Fetch drawing diffs for a master drawing.
 * Cache key includes alignmentId so filtered vs unfiltered results are cached separately.
 *
 * Endpoint: GET /api/projects/${projectId}/drawings/${masterDrawingId}/diffs
 * Query param: ?alignment_id=X (optional)
 */
export function useDrawingDiffs(
  projectId: string | null,
  masterDrawingId: string | null,
  alignmentId: number | null
) {
  const url =
    projectId && masterDrawingId
      ? `/api/projects/${projectId}/drawings/${masterDrawingId}/diffs${alignmentId != null ? `?alignment_id=${alignmentId}` : ""}`
      : "";

  return useQuery<DrawingDiffsListResponse>({
    queryKey: [url],
    enabled: !!projectId && !!masterDrawingId && !!url,
  });
}

/**
 * Run the diff pipeline for an alignment.
 * POST /api/projects/${projectId}/drawings/${masterDrawingId}/diffs
 * Body: RunDrawingDiffRequest
 *
 * Invalidates all diff queries for this project+drawing on success.
 */
export function useRunDrawingDiff(
  projectId: string | null,
  masterDrawingId: string | null
) {
  const queryClient = useQueryClient();

  return useMutation<
    DrawingDiffsListResponse["items"],
    Error,
    { alignmentId: number }
  >({
    mutationFn: async ({ alignmentId }) => {
      if (!projectId || !masterDrawingId) {
        throw new Error("Project and master drawing required");
      }
      const url = `/api/projects/${projectId}/drawings/${masterDrawingId}/diffs`;
      const body: RunDrawingDiffRequest = { alignment_id: alignmentId };
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(typeof err.detail === "string" ? err.detail : "Failed to run diff");
      }
      return res.json();
    },
    onSuccess: () => {
      if (projectId && masterDrawingId) {
        queryClient.invalidateQueries({
          predicate: (query) => {
            const key = query.queryKey[0];
            return (
              typeof key === "string" &&
              key.includes(`/api/projects/${projectId}/drawings/${masterDrawingId}/diffs`)
            );
          },
        });
      }
    },
  });
}
