import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "wouter";

import AlignmentsPanel from "@/components/drawing-workspace/alignments_panel";
import CompareSubDrawingButton from "@/components/drawing-workspace/compare_sub_drawing_button";
import CompareSubDrawingModal from "@/components/drawing-workspace/compare_sub_drawing_modal";
import DiffTimelinePanel from "@/components/drawing-workspace/diff_timeline_panel";
import DrawingComparisonWorkspace from "@/components/drawings/DrawingComparisonWorkspace";
import DrawingWorkspaceLayout from "@/components/drawing-workspace/drawing_workspace_layout";
import WorkspaceErrorState from "@/components/drawing-workspace/workspace_error_state";
import WorkspaceLoadingState from "@/components/drawing-workspace/workspace_loading_state";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import { useWorkspaceSelectionQueryParams } from "@/hooks/use_workspace_selection_query_params";
import { compareSubDrawingToMaster } from "@/lib/api/drawing_workspace";
import { fetchProjectDashboardSummary } from "@/lib/api/projects";
import type { WorkspaceRouteParams } from "@/types/drawing_workspace";

type DrawingWorkspaceBodyProps = {
  parsedProjectId: number;
  parsedDrawingId: number;
};

export function DrawingWorkspaceBody({
  parsedProjectId,
  parsedDrawingId,
}: DrawingWorkspaceBodyProps) {
  const [compareModalOpen, setCompareModalOpen] = useState(false);
  const [selectedSubDrawingId, setSelectedSubDrawingId] = useState<number | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const projectId = parsedProjectId;
  const masterDrawingId = parsedDrawingId;

  const {
    alignmentIdFromUrl,
    diffIdFromUrl,
    setSelectionQueryParams,
  } = useWorkspaceSelectionQueryParams();

  /** Dashboard summary — UX-only `current_drawing.name` for the compare modal (same scope as workspace route). */
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

  const handleConfirmCompare = async (subDrawingId: number) => {
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
      setCompareModalOpen(false);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to compare drawings";
      setCompareError(message);
    } finally {
      setCompareLoading(false);
    }
  };

  const header = (
    <div>
      <h1 className="text-xl font-semibold text-slate-900">Drawing Workspace</h1>
      <p className="text-sm text-slate-500">
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
      onSelectSubDrawing={setSelectedSubDrawingId}
      compareLoading={compareLoading}
      compareError={compareError}
      onConfirmCompare={handleConfirmCompare}
    />
  );

  if (workspaceLoading) {
    return (
      <>
        <DrawingWorkspaceLayout
          header={header}
          viewer={<WorkspaceLoadingState />}
          sidebar={
            <CompareSubDrawingButton onClick={openCompareModal} disabled />
          }
        />

        {compareModal}
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
          sidebar={<CompareSubDrawingButton onClick={openCompareModal} />}
        />

        {compareModal}
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
            <CompareSubDrawingButton onClick={openCompareModal} />

            <AlignmentsPanel
              alignments={alignments}
              selectedAlignmentId={selectedAlignmentId}
              loading={workspaceLoading}
              onSelectAlignment={selectAlignment}
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
