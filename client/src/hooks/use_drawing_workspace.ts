import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  compareSubDrawing,
  fetchAlignmentDiffs,
  fetchMasterDrawing,
  fetchMasterDrawingAlignments,
} from "@/lib/api/drawing_workspace";
import type {
  DrawingAlignment,
  DrawingDiff,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

type UseDrawingWorkspaceArgs = {
  projectId: number;
  drawingId: number;
};

type UseDrawingWorkspaceResult = {
  masterDrawing: DrawingWorkspaceDrawing | null;
  alignments: DrawingAlignment[];
  selectedAlignmentId: number | null;
  selectedDiffId: number | null;
  diffsByAlignmentId: Record<number, DrawingDiff[]>;

  workspaceLoading: boolean;
  diffsLoading: boolean;
  compareLoading: boolean;

  workspaceError: string | null;
  diffsError: string | null;
  compareError: string | null;

  selectedDiffs: DrawingDiff[];
  selectedAlignment: DrawingAlignment | null;
  selectedDiff: DrawingDiff | null;

  selectAlignment: (alignmentId: number) => Promise<void>;
  selectDiff: (diffId: number) => void;

  reloadWorkspace: () => Promise<void>;
  reloadSelectedDiffs: () => Promise<void>;

  runCompare: (subDrawingId: number) => Promise<{
    alignment: DrawingAlignment;
    diffs: DrawingDiff[];
  }>;
};

export function useDrawingWorkspace({
  projectId,
  drawingId,
}: UseDrawingWorkspaceArgs): UseDrawingWorkspaceResult {
  const [masterDrawing, setMasterDrawing] = useState<DrawingWorkspaceDrawing | null>(null);
  const [alignments, setAlignments] = useState<DrawingAlignment[]>([]);
  const [selectedAlignmentId, setSelectedAlignmentId] = useState<number | null>(null);
  const [selectedDiffId, setSelectedDiffId] = useState<number | null>(null);
  const [diffsByAlignmentId, setDiffsByAlignmentId] = useState<Record<number, DrawingDiff[]>>(
    {}
  );

  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [diffsLoading, setDiffsLoading] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [diffsError, setDiffsError] = useState<string | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);

  const workspaceRequestIdRef = useRef(0);
  const diffsRequestIdRef = useRef(0);
  const compareRequestIdRef = useRef(0);
  const diffsByAlignmentIdRef = useRef<Record<number, DrawingDiff[]>>({});
  diffsByAlignmentIdRef.current = diffsByAlignmentId;

  const loadDiffsForAlignment = useCallback(
    async (alignmentId: number, force = false) => {
      if (!force && diffsByAlignmentIdRef.current[alignmentId]) {
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
    [projectId, drawingId]
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

  const mergeAlignmentIntoList = useCallback(
    (incomingAlignment: DrawingAlignment) => {
      setAlignments((prev) => {
        const existingIndex = prev.findIndex(
          (item) => item.id === incomingAlignment.id
        );

        if (existingIndex === -1) {
          return [incomingAlignment, ...prev];
        }

        const next = [...prev];
        next[existingIndex] = incomingAlignment;

        next.sort((a, b) => {
          const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
          const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
          return bTime - aTime;
        });

        return next;
      });
    },
    []
  );

  const storeDiffsForAlignment = useCallback(
    (alignmentId: number, diffs: DrawingDiff[]) => {
      setDiffsByAlignmentId((prev) => ({
        ...prev,
        [alignmentId]: diffs,
      }));
    },
    []
  );

  const runCompare = useCallback(
    async (subDrawingId: number) => {
      const requestId = ++compareRequestIdRef.current;
      setCompareLoading(true);
      setCompareError(null);

      try {
        const response = await compareSubDrawing(projectId, drawingId, subDrawingId);

        const incomingAlignment = response.alignment;
        const incomingDiffs = response.diffs ?? [];

        const sortedDiffs = [...incomingDiffs].sort((a, b) => {
          const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
          const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
          return bTime - aTime;
        });

        if (requestId !== compareRequestIdRef.current) {
          return { alignment: incomingAlignment, diffs: sortedDiffs };
        }

        mergeAlignmentIntoList(incomingAlignment);
        storeDiffsForAlignment(incomingAlignment.id, sortedDiffs);

        setSelectedAlignmentId(incomingAlignment.id);

        const latestDiff = sortedDiffs[0] ?? null;
        setSelectedDiffId(latestDiff?.id ?? null);

        setDiffsError(null);

        if (response.masterDrawing) {
          try {
            const refreshed = await fetchMasterDrawing(projectId, drawingId);
            if (requestId !== compareRequestIdRef.current) {
              return { alignment: incomingAlignment, diffs: sortedDiffs };
            }
            setMasterDrawing(refreshed);
          } catch {
            /* keep existing master */
          }
        }

        return {
          alignment: incomingAlignment,
          diffs: sortedDiffs,
        };
      } catch (error) {
        if (requestId !== compareRequestIdRef.current) {
          throw error;
        }

        const message =
          error instanceof Error ? error.message : "Failed to compare sub drawing.";
        setCompareError(message);
        throw error;
      } finally {
        if (requestId === compareRequestIdRef.current) {
          setCompareLoading(false);
        }
      }
    },
    [projectId, drawingId, mergeAlignmentIntoList, storeDiffsForAlignment]
  );

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
    compareLoading,

    workspaceError,
    diffsError,
    compareError,

    selectedDiffs,
    selectedAlignment,
    selectedDiff,

    selectAlignment,
    selectDiff,

    reloadWorkspace,
    reloadSelectedDiffs,
    runCompare,
  };
}
