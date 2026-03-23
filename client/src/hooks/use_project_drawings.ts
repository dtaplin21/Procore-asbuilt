import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchProjectDrawings } from "@/lib/api/drawings";
import type { ProjectDrawingCandidate } from "@/types/drawing_workspace";

type UseProjectDrawingsArgs = {
  projectId: number;
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
  const [drawings, setDrawings] = useState<ProjectDrawingCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    if (!enabled) return;

    const requestId = ++requestIdRef.current;

    setLoading(true);
    setError(null);

    try {
      const response = await fetchProjectDrawings(projectId);

      if (requestId !== requestIdRef.current) return;

      const filtered = (response.drawings ?? []).filter(
        (drawing) => drawing.id !== masterDrawingId
      );

      setDrawings(filtered);
    } catch (error) {
      if (requestId !== requestIdRef.current) return;

      setError(
        error instanceof Error
          ? error.message
          : "Failed to load project drawings."
      );
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [enabled, projectId, masterDrawingId]);

  useEffect(() => {
    void load();
  }, [load]);

  const stableDrawings = useMemo(() => drawings, [drawings]);

  return {
    drawings: stableDrawings,
    loading,
    error,
    reload: load,
  };
}
