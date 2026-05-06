import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowLeft, FileStack, Trash2 } from "lucide-react";
import { Link, useParams } from "wouter";
import type { DashboardSummaryResponse } from "@shared/schema";

import type {
  ProjectDrawingCandidate,
  ProjectDrawingsResponse,
} from "@/types/drawing_workspace";
import { DeleteDrawingDialog } from "@/components/drawings/DeleteDrawingDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchProjectDrawings } from "@/lib/api/drawings";
import { fetchProjectDashboardSummary } from "@/lib/api/projects";
import { buildWorkspaceUrl } from "@/lib/workspace-links";

export default function DrawingLibraryPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params?.projectId ?? "";
  const parsedProjectId = Number(projectId);
  const isValidProject = Number.isFinite(parsedProjectId);

  const [deleteTarget, setDeleteTarget] = useState<ProjectDrawingCandidate | null>(
    null
  );

  const {
    data: summary,
    isLoading: summaryLoading,
    error: summaryError,
  } = useQuery<DashboardSummaryResponse>({
    queryKey: ["drawing-manage-dashboard-summary", parsedProjectId],
    queryFn: () => fetchProjectDashboardSummary(parsedProjectId),
    enabled: isValidProject,
  });

  const {
    data: drawingsPayload,
    isLoading: drawingsLoading,
    error: drawingsError,
  } = useQuery<ProjectDrawingsResponse>({
    queryKey: [`/api/projects/${projectId}/drawings`],
    queryFn: () => fetchProjectDrawings(parsedProjectId),
    enabled: isValidProject,
  });

  const masterDrawingId = summary?.project?.masterDrawingId;
  const isCanonicalMaster = (drawingId: number) =>
    typeof masterDrawingId === "number" &&
    Number.isFinite(masterDrawingId) &&
    drawingId === masterDrawingId;

  if (!isValidProject) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">Invalid project ID.</p>
        <Link href="/">
          <Button variant="outline" className="mt-4">
            Back to Dashboard
          </Button>
        </Link>
      </div>
    );
  }

  const listLoading = summaryLoading || drawingsLoading;
  const loadError = summaryError ?? drawingsError;

  if (listLoading) {
    return (
      <div className="p-4 max-w-5xl mx-auto">
        <Skeleton className="h-8 w-64 mb-4" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="p-4 max-w-5xl mx-auto">
        <p className="text-sm text-red-600">Failed to load project or drawings.</p>
        <Link href="/">
          <Button variant="outline" className="mt-4">
            Back to Dashboard
          </Button>
        </Link>
      </div>
    );
  }

  const list = drawingsPayload?.drawings ?? [];

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Link href="/">
            <span className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-4 w-4" />
              Dashboard
            </span>
          </Link>
          <h1 className="mt-2 text-xl font-semibold text-foreground flex items-center gap-2">
            <FileStack className="h-6 w-6 text-primary shrink-0" />
            Manage drawings
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Project {projectId} • All sheets in this project. Canonical master is
            labeled; open a row to go to the workspace.
          </p>
        </div>
      </div>

      {list.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No drawings in this project yet. Upload from the dashboard or drawing
            picker.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((drawing) => {
            const master = isCanonicalMaster(drawing.id);
            const workspaceHref = buildWorkspaceUrl({
              projectId: parsedProjectId,
              masterDrawingId: drawing.id,
            });
            return (
              <Card
                key={drawing.id}
                className="relative h-full overflow-hidden transition-colors hover:border-primary/50 hover:bg-primary-soft/40"
                data-testid={`drawing-library-row-${drawing.id}`}
              >
                <div className="absolute right-1 top-1 z-10">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    aria-label={`Delete ${drawing.name}`}
                    onClick={() => setDeleteTarget(drawing)}
                    data-testid={`drawing-library-delete-${drawing.id}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <Link href={workspaceHref} className="block min-h-[5rem] pr-8">
                  <CardHeader className="pb-2 space-y-2 pr-2">
                    <CardTitle className="text-base font-medium truncate pr-2">
                      {drawing.name}
                    </CardTitle>
                    {master ? (
                      <Badge
                        variant="default"
                        className="w-fit text-[10px] uppercase"
                      >
                        Master
                      </Badge>
                    ) : null}
                  </CardHeader>
                  <CardContent className="pt-0 pb-4">
                    <p className="text-xs text-muted-foreground">
                      Drawing #{drawing.id}
                      {drawing.pageCount != null
                        ? ` • ${drawing.pageCount} page(s)`
                        : ""}
                    </p>
                  </CardContent>
                </Link>
              </Card>
            );
          })}
        </div>
      )}

      <DeleteDrawingDialog
        projectId={parsedProjectId}
        drawing={
          deleteTarget
            ? { id: deleteTarget.id, name: deleteTarget.name }
            : null
        }
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      />
    </div>
  );
}
