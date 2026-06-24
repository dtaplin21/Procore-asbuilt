import { useQuery } from "@tanstack/react-query";
import {
  fetchProjectDrawings,
  projectDrawingsQueryKey,
} from "@/lib/api/drawings";
import type {
  ProjectDrawingsResponse,
  ProjectDrawingCandidate,
} from "@/types/drawing_workspace";

type UseProjectDrawingsArgs = {
  projectId: number;
  enabled?: boolean;
};

type UseProjectDrawingsResult = {
  drawings: ProjectDrawingCandidate[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
};

/** Lists all project drawings (master-only upload model). */
export function useProjectDrawings({
  projectId,
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

  const drawings = data?.drawings ?? [];

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
