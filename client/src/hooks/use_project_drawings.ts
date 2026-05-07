import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  coerceDrawingIdForApi,
  fetchProjectDrawings,
  projectDrawingsQueryKey,
} from "@/lib/api/drawings";
import type {
  ProjectDrawingsResponse,
  ProjectDrawingCandidate,
} from "@/types/drawing_workspace";

type UseProjectDrawingsArgs = {
  projectId: number;
  /** Master / left drawing to omit from the sub list — must match `drawing.id` numerically (parse route params before passing). */
  masterDrawingId: number;
  enabled?: boolean;
};

type UseProjectDrawingsResult = {
  drawings: ProjectDrawingCandidate[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
};

export function useProjectDrawings({
  projectId,
  masterDrawingId,
  enabled = true,
}: UseProjectDrawingsArgs): UseProjectDrawingsResult {
  const {
    data,
    isFetching,
    error: queryError,
    refetch,
  } = useQuery<ProjectDrawingsResponse>({
    queryKey: projectDrawingsQueryKey(projectId),
    queryFn: () => fetchProjectDrawings(projectId),
    enabled: enabled && Number.isFinite(projectId) && projectId > 0,
  });

  const drawings = useMemo(() => {
    const list = data?.drawings ?? [];
    let normalizedMaster: number;
    try {
      normalizedMaster = coerceDrawingIdForApi(masterDrawingId);
    } catch {
      return list;
    }
    return list.filter((drawing) => drawing.id !== normalizedMaster);
  }, [data, masterDrawingId]);

  const error =
    queryError instanceof Error
      ? queryError.message
      : queryError
        ? String(queryError)
        : null;

  return {
    drawings,
    loading: isFetching,
    error,
    reload: async () => {
      await refetch();
    },
  };
}
