import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useLocation, useParams, Link } from "wouter";
import type { DrawingResponse } from "@shared/schema";

import AlignmentsPanel from "@/components/drawing-workspace/alignments_panel";
import DiffTimelinePanel from "@/components/drawing-workspace/diff_timeline_panel";
import { UploadDrawingModal } from "@/components/drawing-workspace/UploadDrawingModal";
import { DeleteDrawingDialog } from "@/components/drawings/DeleteDrawingDialog";
import DrawingComparisonWorkspace from "@/components/drawings/DrawingComparisonWorkspace";
import DrawingWorkspaceLayout from "@/components/drawing-workspace/drawing_workspace_layout";
import WorkspaceErrorState from "@/components/drawing-workspace/workspace_error_state";
import WorkspaceLoadingState from "@/components/drawing-workspace/workspace_loading_state";
import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import {
  stripWorkspaceSelectionFromSearch,
  useWorkspaceSelectionQueryParams,
} from "@/hooks/use_workspace_selection_query_params";
import { toast } from "@/hooks/use-toast";
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

type CompareSubToMasterResult =
  | { ok: true }
  | { ok: false; message: string };

export function DrawingWorkspaceBody({
  parsedProjectId,
  parsedDrawingId,
}: DrawingWorkspaceBodyProps) {
  const [location, setLocation] = useLocation();
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);

  const projectId = parsedProjectId;
  /** Workspace “master” side of compare — always from route `drawingId`, not from dashboard summary. */
  const masterDrawingId = parsedDrawingId;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const path = `${window.location.pathname}${window.location.search}`;
    setWorkspaceReturnPath(path);
    setLastProjectIdForWorkspaceFallback(parsedProjectId);
  }, [location, parsedProjectId, parsedDrawingId]);

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

  const routeDrawingForDelete = useMemo(() => {
    const name =
      masterDrawing?.id === parsedDrawingId
        ? masterDrawing.name
        : currentDrawingName ?? `Drawing ${parsedDrawingId}`;
    return { id: parsedDrawingId, name };
  }, [masterDrawing, parsedDrawingId, currentDrawingName]);

  useEffect(() => {
    setSelectionQueryParams({
      alignmentId: selectedAlignmentId,
      diffId: selectedDiffId,
    });
  }, [selectedAlignmentId, selectedDiffId, setSelectionQueryParams]);

  const runCompareSubToMaster = useCallback(
    async (subDrawingId: number): Promise<CompareSubToMasterResult> => {
      console.log("[compare-debug] runCompareSubToMaster start", {
        projectId,
        masterDrawingId,
        subDrawingId,
      });
      const requestId = beginCompareOperation();
      setCompareLoading(true);
      try {
        const response = await compareSubDrawingToMaster({
          projectId,
          masterDrawingId,
          subDrawingId,
        });
        console.log("[compare-debug] runCompareSubToMaster API returned, merging", {
          requestId,
          alignmentId: response.alignment?.id,
        });
        await mergeCompareResponse(response, requestId);
        console.log("[compare-debug] runCompareSubToMaster complete", { subDrawingId });
        return { ok: true };
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to compare drawings";
        console.error("[compare-debug] runCompareSubToMaster error", {
          message,
          error,
        });
        return { ok: false, message };
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
      const result = await runCompareSubToMaster(drawing.id);
      if (!result.ok) {
        toast({
          title: "Drawing comparison failed",
          description: result.message,
          variant: "destructive",
        });
      }
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

  const sidebarUploadControls = (
    uploadDisabled: boolean,
    compareBusy: boolean
  ) => (
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
        disabled={compareBusy}
        data-testid="workspace-delete-drawing-open"
      >
        <Trash2 className="mr-2 h-4 w-4 shrink-0" aria-hidden />
        Delete drawing
      </button>
    </div>
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
          sidebar={sidebarUploadControls(true, false)}
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
          sidebar={sidebarUploadControls(false, false)}
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
            projectId={parsedProjectId}
            masterDrawingId={masterDrawingId}
            masterDrawing={masterDrawing}
            selectedAlignment={selectedAlignment}
            selectedDiff={selectedDiff}
            compareBusy={compareLoading}
          />
        }
        sidebar={
          <>
            {sidebarUploadControls(compareLoading, compareLoading)}

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
