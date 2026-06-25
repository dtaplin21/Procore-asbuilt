import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchProjectDashboardSummary } from "@/lib/api/projects";

export type UseCanonicalMasterDrawingResult = {
  masterDrawingId: number | null;
  name: string | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
};

/** Canonical master from GET /api/projects/{id}/dashboard/summary. */
export function useCanonicalMasterDrawing(
  projectId: number | null,
): UseCanonicalMasterDrawingResult {
  const query = useQuery({
    queryKey: ["project-dashboard-summary", projectId, "canonical-master"],
    queryFn: () => fetchProjectDashboardSummary(projectId!),
    enabled: projectId != null && projectId > 0,
  });

  const masterDrawingId = useMemo(() => {
    const id = query.data?.project?.masterDrawingId;
    if (typeof id === "number" && Number.isInteger(id) && id > 0) {
      return id;
    }
    return null;
  }, [query.data?.project?.masterDrawingId]);

  const name = useMemo(() => {
    if (masterDrawingId == null) return null;
    const fromSummary = query.data?.masterDrawing?.name;
    if (fromSummary?.trim()) return fromSummary.trim();
    return `Drawing ${masterDrawingId}`;
  }, [masterDrawingId, query.data?.masterDrawing?.name]);

  const error =
    query.error instanceof Error
      ? query.error
      : query.error
        ? new Error(String(query.error))
        : null;

  return {
    masterDrawingId,
    name,
    isLoading: query.isLoading,
    isError: query.isError,
    error,
  };
}
