import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useLocation, useParams, Link } from "wouter";
import type { DrawingResponse } from "@shared/schema";

import InspectionRunsPanel from "@/components/drawing-workspace/inspection_runs_panel";
import { UploadDrawingModal } from "@/components/drawing-workspace/UploadDrawingModal";
import { DeleteDrawingDialog } from "@/components/drawings/DeleteDrawingDialog";
import DrawingComparisonWorkspace from "@/components/drawings/DrawingComparisonWorkspace";
import DrawingWorkspaceLayout from "@/components/drawing-workspace/drawing_workspace_layout";
import WorkspaceErrorState from "@/components/drawing-workspace/workspace_error_state";
import WorkspaceLoadingState from "@/components/drawing-workspace/workspace_loading_state";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import { toast } from "@/hooks/use-toast";
import { fetchProjectDashboardSummary } from "@/lib/api/projects";
import {
  setLastProjectIdForWorkspaceFallback,
  setWorkspaceReturnPath,
} from "@/lib/workspace-return-path";
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
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedInspectionRunId, setSelectedInspectionRunId] = useState<number | null>(
    null
  );

  const projectId = parsedProjectId;
  /** Route master drawing id — workspace sheet for this URL. */
  const masterDrawingId = parsedDrawingId;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const path = `${window.location.pathname}${window.location.search}`;
    setWorkspaceReturnPath(path);
    setLastProjectIdForWorkspaceFallback(parsedProjectId);
  }, [location, parsedProjectId, parsedDrawingId]);

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

  const {
    masterDrawing,
    workspaceLoading,
    workspaceError,
    reloadWorkspace,
  } = useDrawingWorkspace({
    projectId: parsedProjectId,
    drawingId: parsedDrawingId,
  });

  const routeDrawingForDelete = useMemo(() => {
    const name =
      masterDrawing?.id === parsedDrawingId
        ? masterDrawing.name
        : currentDrawingName ?? `Drawing ${parsedDrawingId}`;
    return { id: parsedDrawingId, name };
  }, [masterDrawing, parsedDrawingId, currentDrawingName]);

  const handleUploadSuccess = useCallback(
    (drawing: DrawingResponse) => {
      setLocation(`/projects/${projectId}/drawings/${drawing.id}/workspace`);
    },
    [projectId, setLocation]
  );

  const header = (
    <div>
      <h1 className="text-xl font-semibold text-foreground">Drawing Workspace</h1>
      <p className="text-sm text-muted-foreground">
        Project {parsedProjectId} • Drawing {parsedDrawingId}
      </p>
    </div>
  );

  const uploadModal = (
    <UploadDrawingModal
      open={uploadModalOpen}
      onOpenChange={setUploadModalOpen}
      projectId={projectId}
      workspaceMasterDrawingId={masterDrawingId}
      onUploadSuccess={handleUploadSuccess}
    />
  );

  const sidebarUploadControls = (uploadDisabled: boolean) => (
    <div className="space-y-2">
      <button
        type="button"
        className="inline-flex w-full items-center justify-center rounded-md border border-primary bg-background px-3 py-2 text-sm font-medium text-primary shadow-sm hover:bg-primary-soft disabled:opacity-60"
        onClick={() => setUploadModalOpen(true)}
        disabled={uploadDisabled}
        data-testid="upload-drawing-open"
      >
        Upload drawing
      </button>
      <Link
        href={`/projects/${projectId}/drawings/manage`}
        className="inline-flex w-full items-center justify-center rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-muted"
        data-testid="workspace-manage-drawings"
      >
        Manage drawings
      </Link>
      <button
        type="button"
        className="inline-flex w-full items-center justify-center rounded-md border border-destructive/40 bg-background px-3 py-2 text-sm font-medium text-destructive shadow-sm hover:bg-destructive/10 disabled:opacity-60"
        onClick={() => setDeleteDialogOpen(true)}
        data-testid="workspace-delete-drawing-open"
      >
        <Trash2 className="mr-2 h-4 w-4 shrink-0" aria-hidden />
        Delete drawing
      </button>
    </div>
  );

  const sidebarContent = (uploadDisabled: boolean) => (
    <>
      {sidebarUploadControls(uploadDisabled)}
      <InspectionRunsPanel
        projectId={projectId}
        masterDrawingId={masterDrawingId}
        selectedRunId={selectedInspectionRunId}
        onSelectRun={setSelectedInspectionRunId}
      />
    </>
  );

  const deleteDrawingDialog = (
    <DeleteDrawingDialog
      projectId={projectId}
      drawing={routeDrawingForDelete}
      open={deleteDialogOpen}
      onOpenChange={setDeleteDialogOpen}
      onDeleteSuccess={(deletedId) => {
        if (deletedId !== parsedDrawingId) return;
        toast({
          title: "Drawing deleted",
          description: "Removed from this project.",
        });
        setLocation(`/projects/${projectId}/drawings`);
      }}
    />
  );

  if (workspaceLoading) {
    return (
      <>
        <DrawingWorkspaceLayout
          header={header}
          viewer={<WorkspaceLoadingState />}
          sidebar={sidebarContent(true)}
        />

        {uploadModal}
        {deleteDrawingDialog}
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
          sidebar={sidebarContent(false)}
        />

        {uploadModal}
        {deleteDrawingDialog}
      </>
    );
  }

  return (
    <>
      <DrawingWorkspaceLayout
        header={header}
        viewer={
          <DrawingComparisonWorkspace
            projectId={projectId}
            masterDrawing={masterDrawing}
            selectedInspectionRunId={selectedInspectionRunId}
          />
        }
        sidebar={sidebarContent(false)}
      />

      {uploadModal}
      {deleteDrawingDialog}
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
