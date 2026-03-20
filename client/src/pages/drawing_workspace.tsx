import { useMemo } from "react";
import { useParams } from "wouter";

import AlignmentsPanel from "@/components/drawing-workspace/alignments_panel";
import DiffTimelinePanel from "@/components/drawing-workspace/diff_timeline_panel";
import DrawingWorkspaceLayout from "@/components/drawing-workspace/drawing_workspace_layout";
import MasterDrawingViewer from "@/components/drawing-workspace/master_drawing_viewer";
import WorkspaceErrorState from "@/components/drawing-workspace/workspace_error_state";
import WorkspaceLoadingState from "@/components/drawing-workspace/workspace_loading_state";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";

export default function DrawingWorkspacePage() {
  const params = useParams<{ projectId?: string; drawingId?: string }>();
  const projectId = params?.projectId;
  const drawingId = params?.drawingId;

  const parsedProjectId = Number(projectId);
  const parsedMasterDrawingId = Number(drawingId);

  const idsAreValid = useMemo(() => {
    return Number.isFinite(parsedProjectId) && Number.isFinite(parsedMasterDrawingId);
  }, [parsedProjectId, parsedMasterDrawingId]);

  if (!idsAreValid) {
    return (
      <div className="p-4">
        <WorkspaceErrorState message="Invalid project or master drawing id." />
      </div>
    );
  }

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
    selectedDiff,
    selectAlignment,
    selectDiff,
    reloadWorkspace,
    reloadSelectedDiffs,
  } = useDrawingWorkspace({
    projectId: parsedProjectId,
    masterDrawingId: parsedMasterDrawingId,
  });

  const header = (
    <div>
      <h1 className="text-xl font-semibold text-slate-900">Drawing Workspace</h1>
      <p className="text-sm text-slate-500">
        Project {parsedProjectId} • Master Drawing {parsedMasterDrawingId}
      </p>
    </div>
  );

  if (workspaceLoading) {
    return <DrawingWorkspaceLayout header={header} viewer={<WorkspaceLoadingState />} sidebar={null} />;
  }

  if (workspaceError) {
    return (
      <DrawingWorkspaceLayout
        header={header}
        viewer={<WorkspaceErrorState message={workspaceError} onRetry={() => void reloadWorkspace()} />}
        sidebar={null}
      />
    );
  }

  return (
    <DrawingWorkspaceLayout
      header={header}
      viewer={
        <MasterDrawingViewer
          drawing={masterDrawing}
          selectedDiff={selectedDiff}
        />
      }
      sidebar={
        <>
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
  );
}
