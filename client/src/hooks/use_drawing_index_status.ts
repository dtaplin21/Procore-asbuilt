import { useQuery } from "@tanstack/react-query";

import {
  drawingIndexStatusQueryKey,
  fetchDrawingIndexStatus,
} from "@/lib/api/drawing_index";
import { isDrawingIndexInProgress } from "@/lib/drawing-index/format_index_summary";

export function useDrawingIndexStatus(
  projectId: number | null | undefined,
  drawingId: number | null | undefined,
) {
  const enabled =
    projectId != null &&
    drawingId != null &&
    projectId > 0 &&
    drawingId > 0;

  return useQuery({
    queryKey:
      enabled && projectId != null && drawingId != null
        ? drawingIndexStatusQueryKey(projectId, drawingId)
        : ["drawing-index-status", "disabled"],
    queryFn: () => fetchDrawingIndexStatus(projectId!, drawingId!),
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return isDrawingIndexInProgress(status) ? 3000 : false;
    },
  });
}
