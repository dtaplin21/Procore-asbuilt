import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useParams } from "wouter";
import type { DrawingResponse } from "@shared/schema";

import AlignmentsPanel from "@/components/drawing-workspace/alignments_panel";
import CompareSubDrawingButton from "@/components/drawing-workspace/compare_sub_drawing_button";
import CompareSubDrawingModal from "@/components/drawing-workspace/compare_sub_drawing_modal";
import DiffTimelinePanel from "@/components/drawing-workspace/diff_timeline_panel";
import { UploadDrawingModal } from "@/components/drawing-workspace/UploadDrawingModal";
import DrawingComparisonWorkspace from "@/components/drawings/DrawingComparisonWorkspace";
import DrawingWorkspaceLayout from "@/components/drawing-workspace/drawing_workspace_layout";
import WorkspaceErrorState from "@/components/drawing-workspace/workspace_error_state";
import WorkspaceLoadingState from "@/components/drawing-workspace/workspace_loading_state";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import {
  stripWorkspaceSelectionFromSearch,
  useWorkspaceSelectionQueryParams,
} from "@/hooks/use_workspace_selection_query_params";
import { compareSubDrawingToMaster } from "@/lib/api/drawing_workspace";
import { fetchProjectDashboardSummary } from "@/lib/api/projects";
import {
  setLastProjectIdForWorkspaceFallback,
  setWorkspaceReturnPath,
} from "@/lib/workspace-return-path";
import type { DrawingUploadIntent } from "@/components/drawings/DrawingUploadWithIntent";
import type { WorkspaceRouteParams } from "@/types/drawing_workspace";

type DrawingWorkspaceBodyProps = {
  parsedProjectId: number;
  parsedDrawingId: number;
};

export function DrawingWorkspaceBody({
  parsedProjectId,
  parsedDrawingId,
}: DrawingWorkspaceBodyProps) {
  const [location, setLocation] = useLocation();
  const [compareModalOpen, setCompareModalOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [selectedSubDrawingId, setSelectedSubDrawingId] = useState<number | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const projectId = parsedProjectId;
  /** Workspace “master” side of compare — always from route `drawingId`, not from dashboard summary. */
  const masterDrawingId = parsedDrawingId;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const path = `${window.location.pathname}${window.location.search}`;
    setWorkspaceReturnPath(path);
    setLastProjectIdForWorkspaceFallback(parsedProjectId);
  }, [location, parsedProjectId, parsedDrawingId]);

  useEffect(() => {
    setSelectedSubDrawingId(null);
  }, [parsedProjectId, parsedDrawingId]);

  const {
    alignmentIdFromUrl,
    diffIdFromUrl,
    setSelectionQueryParams,
  } = useWorkspaceSelectionQueryParams();

  /** UX-only label (`current_drawing.name`); optional. Do not use summary ids for `masterDrawingId` (avoid circularity). */
  const summaryQuery = useQuery({
    queryKey: [
      "project-dashboard-summary",
      parsedProjectId,
      parsedDrawingId,
    ],
    queryFn: () =>
      fetchProjectDashboardSummary(parsedProjectId, {
        currentDrawingId: parsedDrawingId,
      }),
  });

  const currentDrawingName =
    summaryQuery.data?.current_drawing?.name ?? null;

  const openCompareModal = () => {
    setCompareModalOpen(true);
  };

  const {
    masterDrawing,
    alignments,
    selectedAlignmentId,
    selectedDiffId,
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
    beginCompareOperation,
    mergeCompareResponse,
  } = useDrawingWorkspace({
    projectId: parsedProjectId,
    drawingId: parsedDrawingId,
    initialAlignmentId: alignmentIdFromUrl,
    initialDiffId: diffIdFromUrl,
  });

  useEffect(() => {
    setSelectionQueryParams({
      alignmentId: selectedAlignmentId,
      diffId: selectedDiffId,
    });
  }, [selectedAlignmentId, selectedDiffId, setSelectionQueryParams]);

  const runCompareSubToMaster = useCallback(
    async (subDrawingId: number) => {
      const requestId = beginCompareOperation();
      setCompareLoading(true);
      setCompareError(null);
      try {
        const response = await compareSubDrawingToMaster({
          projectId,
          masterDrawingId,
          subDrawingId,
        });
        await mergeCompareResponse(response, requestId);
        setSelectedSubDrawingId(subDrawingId);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to compare drawings";
        setCompareError(message);
        throw error;
      } finally {
        setCompareLoading(false);
      }
    },
    [
      beginCompareOperation,
      masterDrawingId,
      mergeCompareResponse,
      projectId,
    ]
  );

  const handleConfirmCompare = useCallback(
    async (subDrawingId: number) => {
      try {
        await runCompareSubToMaster(subDrawingId);
        setCompareModalOpen(false);
      } catch {
        // compareError set in runCompareSubToMaster
      }
    },
    [runCompareSubToMaster]
  );

  const handleUploadSuccess = useCallback(
    async (drawing: DrawingResponse, intent: DrawingUploadIntent) => {
      if (intent === "master") {
        const q = location.indexOf("?");
        const search = q === -1 ? "" : location.slice(q);
        const nextQuery = stripWorkspaceSelectionFromSearch(search);
        setLocation(
          `/projects/${projectId}/drawings/${drawing.id}/workspace${nextQuery}`
        );
        return;
      }
      await runCompareSubToMaster(drawing.id);
    },
    [location, projectId, runCompareSubToMaster, setLocation]
  );

  const header = (
    <div>
      <h1 className="text-xl font-semibold text-foreground">Drawing Workspace</h1>
      <p className="text-sm text-muted-foreground">
        Project {parsedProjectId} • Drawing {parsedDrawingId}
      </p>
    </div>
  );

  const compareModal = (
    <CompareSubDrawingModal
      open={compareModalOpen}
      onOpenChange={setCompareModalOpen}
      projectId={projectId}
      masterDrawingId={masterDrawingId}
      currentDrawingName={currentDrawingName}
      selectedDrawingId={selectedSubDrawingId}
      onSelectSubDrawing={(drawingId) => setSelectedSubDrawingId(drawingId)}
      compareLoading={compareLoading}
      compareError={compareError}
      onConfirmCompare={handleConfirmCompare}
    />
  );

  const uploadModal = (
    <UploadDrawingModal
      open={uploadModalOpen}
      onOpenChange={setUploadModalOpen}
      projectId={projectId}
      workspaceMasterDrawingId={masterDrawingId}
      onUploadSuccess={handleUploadSuccess}
      isExternallyBusy={compareLoading}
    />
  );

  const sidebarUploadControls = (uploadDisabled: boolean) => (
    <div className="space-y-2">
      <CompareSubDrawingButton onClick={openCompareModal} disabled={uploadDisabled} />
      <button
        type="button"
        className="inline-flex w-full items-center justify-center rounded-md border border-primary bg-background px-3 py-2 text-sm font-medium text-primary shadow-sm hover:bg-primary-soft disabled:opacity-60"
        onClick={() => setUploadModalOpen(true)}
        disabled={uploadDisabled}
        data-testid="upload-drawing-open"
      >
        Upload drawing
      </button>
    </div>
  );

  if (workspaceLoading) {
    return (
      <>
        <DrawingWorkspaceLayout
          header={header}
          viewer={<WorkspaceLoadingState />}
          sidebar={sidebarUploadControls(true)}
        />

        {compareModal}
        {uploadModal}
      </>
    );
  }

  if (workspaceError) {
    return (
      <>
        <DrawingWorkspaceLayout
          header={header}
          viewer={
            <WorkspaceErrorState
              message={workspaceError}
              onRetry={() => void reloadWorkspace()}
            />
          }
          sidebar={sidebarUploadControls(false)}
        />

        {compareModal}
        {uploadModal}
      </>
    );
  }

  return (
    <>
      <DrawingWorkspaceLayout
        header={header}
        viewer={
          <DrawingComparisonWorkspace
            projectId={parsedProjectId}
            masterDrawing={masterDrawing}
            selectedAlignment={selectedAlignment}
            selectedDiff={selectedDiff}
          />
        }
        sidebar={
          <>
            {sidebarUploadControls(compareLoading)}

            <AlignmentsPanel
              projectId={projectId}
              masterDrawingId={masterDrawingId}
              alignments={alignments}
              selectedAlignmentId={selectedAlignmentId}
              loading={workspaceLoading}
              onSelectAlignment={selectAlignment}
              onRerunComplete={() => void reloadSelectedDiffs()}
            />

            <DiffTimelinePanel
              diffs={selectedDiffs}
              selectedDiffId={selectedDiffId}
              loading={diffsLoading}
              error={diffsError}
              onSelectDiff={selectDiff}
              onRetry={() => void reloadSelectedDiffs()}
            />
          </>
        }
      />

      {compareModal}
      {uploadModal}
    </>
  );
}

export default function DrawingWorkspacePage() {
  const { projectId, drawingId } = useParams<WorkspaceRouteParams>();

  const parsedProjectId = Number(projectId);
  const parsedDrawingId = Number(drawingId);

  const idsAreValid = useMemo(() => {
    return Number.isFinite(parsedProjectId) && Number.isFinite(parsedDrawingId);
  }, [parsedProjectId, parsedDrawingId]);

  if (!idsAreValid) {
    return (
      <div className="p-4">
        <WorkspaceErrorState message="Invalid project or drawing id." />
      </div>
    );
  }

  return (
    <DrawingWorkspaceBody
      parsedProjectId={parsedProjectId}
      parsedDrawingId={parsedDrawingId}
    />
  );
}
