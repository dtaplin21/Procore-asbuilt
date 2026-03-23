import { useMemo, useState } from "react";
import { useParams } from "wouter";

import AlignmentsPanel from "@/components/drawing-workspace/alignments_panel";
import CompareSubDrawingButton from "@/components/drawing-workspace/compare_sub_drawing_button";
import CompareSubDrawingModal from "@/components/drawing-workspace/compare_sub_drawing_modal";
import DiffTimelinePanel from "@/components/drawing-workspace/diff_timeline_panel";
import DrawingViewer from "@/components/drawing-workspace/drawing_viewer";
import DrawingWorkspaceLayout from "@/components/drawing-workspace/drawing_workspace_layout";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import type { WorkspaceRouteParams } from "@/types/drawing_workspace";

export default function DrawingWorkspacePage() {
  const { projectId, drawingId } = useParams<WorkspaceRouteParams>();
  const [isCompareModalOpen, setIsCompareModalOpen] = useState(false);
  const [selectedSubDrawingId, setSelectedSubDrawingId] = useState<number | null>(null);

  const openCompareModal = () => {
    setIsCompareModalOpen(true);
  };

  const closeCompareModal = () => {
    setIsCompareModalOpen(false);
  };

  const handleSelectSubDrawing = (drawingId: number | null) => {
    setSelectedSubDrawingId(drawingId);
  };

  const parsedProjectId = Number(projectId);
  const parsedDrawingId = Number(drawingId);

  const idsAreValid = useMemo(() => {
    return Number.isFinite(parsedProjectId) && Number.isFinite(parsedDrawingId);
  }, [parsedProjectId, parsedDrawingId]);

  if (!idsAreValid) {
    return (
      <div className="p-4 text-red-600">
        Invalid project id or drawing id.
      </div>
    );
  }

  const {
    masterDrawing,
    alignments,
    selectedAlignmentId,
    selectedDiffId,
    selectedDiffs,
    selectedDiff,
    workspaceLoading,
    diffsLoading,
    workspaceError,
    diffsError,
    selectAlignment,
    selectDiff,
    reloadWorkspace,
    reloadSelectedDiffs,
  } = useDrawingWorkspace({
    projectId: parsedProjectId,
    drawingId: parsedDrawingId,
  });

  const header = (
    <>
      <h1 className="text-xl font-semibold">Drawing Workspace</h1>
      <p className="text-sm text-slate-500">
        Project {parsedProjectId} • Drawing {parsedDrawingId}
      </p>

      {workspaceError ? (
        <div className="mt-4 rounded border border-red-200 bg-red-50 p-4">
          <div className="text-sm font-medium text-red-700">
            Failed to load workspace
          </div>
          <div className="mt-1 text-sm text-red-600">{workspaceError}</div>
          <button
            type="button"
            onClick={() => void reloadWorkspace()}
            className="mt-3 rounded border border-red-300 bg-white px-3 py-2 text-sm text-red-700"
            data-testid="retry-workspace"
          >
            Retry
          </button>
        </div>
      ) : null}
    </>
  );

  return (
    <>
      <DrawingWorkspaceLayout
        header={header}
        viewer={
          workspaceLoading ? (
            <div className="flex min-h-[70vh] items-center justify-center rounded-xl border bg-white p-8 text-sm text-slate-500">
              Loading master drawing...
            </div>
          ) : (
            <DrawingViewer
              drawing={masterDrawing}
              selectedDiff={selectedDiff}
            />
          )
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

      <CompareSubDrawingModal
        isOpen={isCompareModalOpen}
        projectId={parsedProjectId}
        masterDrawingId={parsedDrawingId}
        onClose={closeCompareModal}
        onSelectSubDrawing={handleSelectSubDrawing}
      />
    </>
  );
}
