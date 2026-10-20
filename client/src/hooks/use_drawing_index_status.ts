import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import {
  drawingIndexStatusQueryKey,
  fetchDrawingIndexStatus,
} from "@/lib/api/drawing_index";
import { invalidateOverlaysForDrawing } from "@/lib/api/overlays";
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
  const queryClient = useQueryClient();
  const seenIndexedAt = useRef<{ drawingId: number; indexedAt: string | null } | null>(null);

  const query = useQuery({
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

  const indexedAt = query.data?.indexed_at ?? null;
  const status = query.data?.status;
  useEffect(() => {
    if (!enabled || drawingId == null) return;
    const previous = seenIndexedAt.current;
    const sameDrawing = previous?.drawingId === drawingId;
    seenIndexedAt.current = { drawingId, indexedAt };
    if (!sameDrawing || previous.indexedAt === indexedAt) return;
    if (status === "ready") {
      invalidateOverlaysForDrawing(queryClient, String(drawingId));
    }
  }, [drawingId, enabled, indexedAt, queryClient, status]);

  return query;
}
