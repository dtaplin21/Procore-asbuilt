import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DrawingAlignment,
  DrawingDiff,
  DrawingSummary,
} from "@/types/drawing_workspace";
import {
  fetchAlignments,
  fetchDiffs,
  fetchDrawing,
} from "@/lib/api/drawing_workspace";
import { getErrorMessage } from "@/lib/errors";

type UseDrawingWorkspaceArgs = {
  projectId: number;
  masterDrawingId: number;
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

  selectedAlignment: DrawingAlignment | null;
  selectedDiffs: DrawingDiff[];
  selectedDiff: DrawingDiff | null;

  selectAlignment: (alignmentId: number) => void;
  selectDiff: (diffId: number) => void;

  reloadWorkspace: () => Promise<void>;
  reloadSelectedDiffs: () => Promise<void>;
};

export function useDrawingWorkspace({
  projectId,
  masterDrawingId,
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

  const workspaceRequestRef = useRef(0);
  const diffsRequestRef = useRef(0);

  const loadWorkspace = useCallback(async () => {
    const requestId = ++workspaceRequestRef.current;

    setWorkspaceLoading(true);
    setWorkspaceError(null);

    try {
      const [drawingResponse, alignmentsResponse] = await Promise.all([
        fetchDrawing(projectId, masterDrawingId),
        fetchAlignments(projectId, masterDrawingId),
      ]);

      if (requestId !== workspaceRequestRef.current) return;

      const nextAlignments = alignmentsResponse.alignments ?? [];

      setMasterDrawing(drawingResponse);
      setAlignments(nextAlignments);

      setSelectedAlignmentId((current) => {
        if (current && nextAlignments.some((item) => item.id === current)) {
          return current;
        }
        return nextAlignments[0]?.id ?? null;
      });

      setSelectedDiffId(null);
      setDiffsByAlignmentId({});
    } catch (error) {
      if (requestId !== workspaceRequestRef.current) return;
      setWorkspaceError(getErrorMessage(error, "Failed to load workspace."));
    } finally {
      if (requestId === workspaceRequestRef.current) {
        setWorkspaceLoading(false);
      }
    }
  }, [projectId, masterDrawingId]);

  const loadDiffsForAlignment = useCallback(
    async (alignmentId: number, force = false) => {
      if (!force && diffsByAlignmentId[alignmentId]) {
        return;
      }

      const requestId = ++diffsRequestRef.current;

      setDiffsLoading(true);
      setDiffsError(null);

      try {
        const response = await fetchDiffs(projectId, masterDrawingId, alignmentId);

        if (requestId !== diffsRequestRef.current) return;

        const nextDiffs = response.diffs ?? [];

        setDiffsByAlignmentId((prev) => ({
          ...prev,
          [alignmentId]: nextDiffs,
        }));

        setSelectedDiffId((current) => {
          if (current && nextDiffs.some((item) => item.id === current)) {
            return current;
          }
          return nextDiffs[0]?.id ?? null;
        });
      } catch (error) {
        if (requestId !== diffsRequestRef.current) return;
        setDiffsError(getErrorMessage(error, "Failed to load diffs."));
      } finally {
        if (requestId === diffsRequestRef.current) {
          setDiffsLoading(false);
        }
      }
    },
    [projectId, masterDrawingId, diffsByAlignmentId]
  );

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (selectedAlignmentId == null) return;
    void loadDiffsForAlignment(selectedAlignmentId);
  }, [selectedAlignmentId, loadDiffsForAlignment]);

  const selectedAlignment = useMemo(() => {
    return alignments.find((item) => item.id === selectedAlignmentId) ?? null;
  }, [alignments, selectedAlignmentId]);

  const selectedDiffs = useMemo(() => {
    if (selectedAlignmentId == null) return [];
    return diffsByAlignmentId[selectedAlignmentId] ?? [];
  }, [selectedAlignmentId, diffsByAlignmentId]);

  const selectedDiff = useMemo(() => {
    return selectedDiffs.find((item) => item.id === selectedDiffId) ?? null;
  }, [selectedDiffId, selectedDiffs]);

  const selectAlignment = useCallback((alignmentId: number) => {
    setSelectedAlignmentId(alignmentId);
    setSelectedDiffId(null);
    setDiffsError(null);
  }, []);

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

    selectedAlignment,
    selectedDiffs,
    selectedDiff,

    selectAlignment,
    selectDiff,

    reloadWorkspace,
    reloadSelectedDiffs,
  };
}
