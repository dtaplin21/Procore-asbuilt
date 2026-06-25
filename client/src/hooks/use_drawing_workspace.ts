import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMasterDrawing } from "@/lib/api/drawing_workspace";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";

type UseDrawingWorkspaceArgs = {
  projectId: number;
  drawingId: number;
};

type UseDrawingWorkspaceResult = {
  masterDrawing: DrawingWorkspaceDrawing | null;
  workspaceLoading: boolean;
  workspaceError: string | null;
  reloadWorkspace: () => Promise<void>;
};

export function useDrawingWorkspace({
  projectId,
  drawingId,
}: UseDrawingWorkspaceArgs): UseDrawingWorkspaceResult {
  const [masterDrawing, setMasterDrawing] = useState<DrawingWorkspaceDrawing | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);

  const workspaceRequestIdRef = useRef(0);

  const loadWorkspace = useCallback(async () => {
    const requestId = ++workspaceRequestIdRef.current;

    setWorkspaceLoading(true);
    setWorkspaceError(null);

    try {
      const drawingResponse = await fetchMasterDrawing(projectId, drawingId);

      if (requestId !== workspaceRequestIdRef.current) {
        return;
      }

      setMasterDrawing(drawingResponse);
    } catch (error) {
      if (requestId !== workspaceRequestIdRef.current) {
        return;
      }

      setWorkspaceError(
        error instanceof Error ? error.message : "Failed to load drawing workspace."
      );
    } finally {
      if (requestId === workspaceRequestIdRef.current) {
        setWorkspaceLoading(false);
      }
    }
  }, [projectId, drawingId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  // Poll for drawing when rendering (pending/processing) until ready or failed
  useEffect(() => {
    if (!masterDrawing || workspaceLoading) return;

    const status = (masterDrawing.processingStatus ?? "").toLowerCase();
    if (status !== "pending" && status !== "processing") return;

    const pollIntervalMs = 2000;
    const timer = setInterval(async () => {
      try {
        const updated = await fetchMasterDrawing(projectId, drawingId);
        setMasterDrawing(updated);
      } catch {
        // Ignore poll errors; next poll will retry
      }
    }, pollIntervalMs);

    return () => clearInterval(timer);
  }, [masterDrawing, projectId, drawingId, workspaceLoading]);

  const reloadWorkspace = useCallback(async () => {
    await loadWorkspace();
  }, [loadWorkspace]);

  return {
    masterDrawing,
    workspaceLoading,
    workspaceError,
    reloadWorkspace,
  };
}
