import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchAlignmentDiffs,
  fetchMasterDrawing,
  fetchMasterDrawingAlignments,
} from "@/lib/api/drawing_workspace";
import type {
  DrawingAlignment,
  DrawingDiff,
  DrawingSummary,
} from "@/types/drawing_workspace";

type UseDrawingWorkspaceArgs = {
  projectId: number;
  drawingId: number;
};

type UseDrawingWorkspaceResult = {
  masterDrawing: DrawingSummary | null;
  alignments: DrawingAlignment[];
  selectedAlignmentId: number | null;
  selectedDiffId: number | null;
  diffsByAlignmentId: Record<number, DrawingDiff[]>;

  workspaceLoading: boolean;
  diffsLoading: boolean;

  workspaceError: string | null;
  diffsError: string | null;

  selectedDiffs: DrawingDiff[];
  selectedAlignment: DrawingAlignment | null;
  selectedDiff: DrawingDiff | null;

  selectAlignment: (alignmentId: number) => Promise<void>;
  selectDiff: (diffId: number) => void;

  reloadWorkspace: () => Promise<void>;
  reloadSelectedDiffs: () => Promise<void>;
};

export function useDrawingWorkspace({
  projectId,
  drawingId,
}: UseDrawingWorkspaceArgs): UseDrawingWorkspaceResult {
  const [masterDrawing, setMasterDrawing] = useState<DrawingSummary | null>(null);
  const [alignments, setAlignments] = useState<DrawingAlignment[]>([]);
  const [selectedAlignmentId, setSelectedAlignmentId] = useState<number | null>(null);
  const [selectedDiffId, setSelectedDiffId] = useState<number | null>(null);
  const [diffsByAlignmentId, setDiffsByAlignmentId] = useState<Record<number, DrawingDiff[]>>(
    {}
  );

  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [diffsLoading, setDiffsLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [diffsError, setDiffsError] = useState<string | null>(null);

  const workspaceRequestIdRef = useRef(0);
  const diffsRequestIdRef = useRef(0);

  const loadDiffsForAlignment = useCallback(
    async (alignmentId: number, force = false) => {
      if (!force && diffsByAlignmentId[alignmentId]) {
        return;
      }

      const requestId = ++diffsRequestIdRef.current;

      setDiffsLoading(true);
      setDiffsError(null);

      try {
        const response = await fetchAlignmentDiffs(projectId, drawingId, alignmentId);

        if (requestId !== diffsRequestIdRef.current) {
          return;
        }

        const nextDiffs = response.diffs ?? [];

        setDiffsByAlignmentId((prev) => ({
          ...prev,
          [alignmentId]: nextDiffs,
        }));

        setSelectedDiffId((current) => {
          if (current && nextDiffs.some((diff) => diff.id === current)) {
            return current;
          }
          return nextDiffs[0]?.id ?? null;
        });
      } catch (error) {
        if (requestId !== diffsRequestIdRef.current) {
          return;
        }

        setDiffsError(error instanceof Error ? error.message : "Failed to load diffs.");
      } finally {
        if (requestId === diffsRequestIdRef.current) {
          setDiffsLoading(false);
        }
      }
    },
    [projectId, drawingId, diffsByAlignmentId]
  );

  const loadWorkspace = useCallback(async () => {
    const requestId = ++workspaceRequestIdRef.current;

    setWorkspaceLoading(true);
    setWorkspaceError(null);
    setDiffsError(null);

    try {
      const [drawingResponse, alignmentsResponse] = await Promise.all([
        fetchMasterDrawing(projectId, drawingId),
        fetchMasterDrawingAlignments(projectId, drawingId),
      ]);

      if (requestId !== workspaceRequestIdRef.current) {
        return;
      }

      const nextAlignments = alignmentsResponse.alignments ?? [];

      setMasterDrawing(drawingResponse);
      setAlignments(nextAlignments);

      setDiffsByAlignmentId({});
      setSelectedDiffId(null);

      if (nextAlignments.length > 0) {
        const mostRecentAlignment = nextAlignments[0];
        setSelectedAlignmentId(mostRecentAlignment.id);

        await loadDiffsForAlignment(mostRecentAlignment.id, true);
      } else {
        setSelectedAlignmentId(null);
      }
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
  }, [projectId, drawingId, loadDiffsForAlignment]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const selectAlignment = useCallback(
    async (alignmentId: number) => {
      setSelectedAlignmentId(alignmentId);
      setSelectedDiffId(null);
      setDiffsError(null);
      await loadDiffsForAlignment(alignmentId);
    },
    [loadDiffsForAlignment]
  );

  const selectDiff = useCallback((diffId: number) => {
    setSelectedDiffId(diffId);
  }, []);

  const reloadWorkspace = useCallback(async () => {
    await loadWorkspace();
  }, [loadWorkspace]);

  const reloadSelectedDiffs = useCallback(async () => {
    if (selectedAlignmentId == null) return;
    await loadDiffsForAlignment(selectedAlignmentId, true);
  }, [selectedAlignmentId, loadDiffsForAlignment]);

  const selectedDiffs = useMemo(() => {
    if (selectedAlignmentId == null) return [];
    return diffsByAlignmentId[selectedAlignmentId] ?? [];
  }, [selectedAlignmentId, diffsByAlignmentId]);

  const selectedAlignment = useMemo(() => {
    return alignments.find((alignment) => alignment.id === selectedAlignmentId) ?? null;
  }, [alignments, selectedAlignmentId]);

  const selectedDiff = useMemo(() => {
    return selectedDiffs.find((diff) => diff.id === selectedDiffId) ?? null;
  }, [selectedDiffs, selectedDiffId]);

  return {
    masterDrawing,
    alignments,
    selectedAlignmentId,
    selectedDiffId,
    diffsByAlignmentId,

    workspaceLoading,
    diffsLoading,

    workspaceError,
    diffsError,

    selectedDiffs,
    selectedAlignment,
    selectedDiff,

    selectAlignment,
    selectDiff,

    reloadWorkspace,
    reloadSelectedDiffs,
  };
}
