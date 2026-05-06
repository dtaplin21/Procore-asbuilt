import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileImage } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import type { DashboardSummaryResponse } from "@shared/schema";

import type { ProjectDrawingsResponse } from "@/types/drawing_workspace";
import { UploadDrawingModal } from "@/components/drawing-workspace/UploadDrawingModal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchProjectDrawings } from "@/lib/api/drawings";
import { fetchProjectDashboardSummary } from "@/lib/api/projects";
import { buildWorkspaceUrl } from "@/lib/workspace-links";

function preserveSearchParams(): string {
  const search = typeof window !== "undefined" ? window.location.search : "";
  return search ? `?${search}` : "";
}

/** Append current window search params to a path that may already include `?`. */
function pathWithPreservedSearch(pathWithOptionalQuery: string): string {
  const preserved = preserveSearchParams();
  if (!preserved) {
    return pathWithOptionalQuery;
  }
  return pathWithOptionalQuery.includes("?")
    ? `${pathWithOptionalQuery}&${preserved.slice(1)}`
    : `${pathWithOptionalQuery}${preserved}`;
}

export default function DrawingPickerPage() {
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [, setLocation] = useLocation();
  const params = useParams<{ projectId: string }>();
  const projectId = params?.projectId ?? "";

  const parsedProjectId = Number(projectId);
  const isValidProject = Number.isFinite(parsedProjectId);

  const {
    data: summary,
    isLoading: summaryLoading,
    error: summaryError,
  } = useQuery<DashboardSummaryResponse>({
    queryKey: ["drawing-picker-dashboard-summary", parsedProjectId],
    queryFn: () => fetchProjectDashboardSummary(parsedProjectId),
    enabled: isValidProject,
  });

  const masterDrawingId = summary?.project?.masterDrawingId;
  const hasCanonicalMaster =
    typeof masterDrawingId === "number" && Number.isFinite(masterDrawingId);

  useEffect(() => {
    if (!hasCanonicalMaster || !isValidProject) return;
    const ws = buildWorkspaceUrl({
      projectId: parsedProjectId,
      masterDrawingId: masterDrawingId as number,
    });
    setLocation(pathWithPreservedSearch(ws));
  }, [
    hasCanonicalMaster,
    isValidProject,
    masterDrawingId,
    parsedProjectId,
    setLocation,
  ]);

  const {
    data: drawingsPayload,
    isLoading: drawingsLoading,
    error: drawingsError,
  } = useQuery<ProjectDrawingsResponse>({
    queryKey: [`/api/projects/${projectId}/drawings`],
    queryFn: () => fetchProjectDrawings(parsedProjectId),
    enabled: isValidProject && !summaryLoading && !hasCanonicalMaster,
  });

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

  const listLoading = summaryLoading || (!hasCanonicalMaster && drawingsLoading);
  const loadError = summaryError ?? drawingsError;

  if (listLoading || hasCanonicalMaster) {
    return (
      <div className="p-4">
        <h1 className="text-xl font-semibold text-foreground mb-4">
          Select a Drawing
        </h1>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="p-4">
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

  const uploadModal = (
    <UploadDrawingModal
      open={uploadModalOpen}
      onOpenChange={setUploadModalOpen}
      projectId={parsedProjectId}
      allowMaster
      allowSub={false}
      onUploadSuccess={(drawing) => {
        setLocation(
          pathWithPreservedSearch(
            buildWorkspaceUrl({
              projectId: parsedProjectId,
              masterDrawingId: drawing.id,
            })
          )
        );
      }}
    />
  );

  return (
    <div className="p-4">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            Select a Drawing
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Project {projectId} • No canonical master yet — choose a sheet or upload
            one (first upload becomes master).
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          className="w-full shrink-0 border-primary bg-background text-primary hover:bg-primary-soft hover:text-primary sm:w-auto"
          onClick={() => setUploadModalOpen(true)}
          data-testid="drawing-picker-upload-open"
        >
          Upload drawing
        </Button>
      </div>

      {list.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileImage className="w-12 h-12 mx-auto mb-3 text-muted-foreground" />
            <p className="text-sm text-foreground">
              No drawings in this project yet.
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              Upload a drawing (it will become the project master) or return to the
              dashboard.
            </p>
            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button
                type="button"
                onClick={() => setUploadModalOpen(true)}
                data-testid="drawing-picker-empty-upload"
              >
                Upload drawing
              </Button>
              <Link href="/">
                <Button variant="outline" data-testid="drawing-picker-back-dashboard">
                  Back to Dashboard
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((drawing) => (
            <Link
              key={drawing.id}
              href={pathWithPreservedSearch(
                buildWorkspaceUrl({
                  projectId: parsedProjectId,
                  masterDrawingId: drawing.id,
                })
              )}
            >
              <Card className="cursor-pointer transition-colors hover:border-primary/50 hover:bg-primary-soft/40">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base font-medium truncate">
                    {drawing.name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  <p className="text-xs text-muted-foreground">
                    Drawing #{drawing.id}
                    {drawing.pageCount != null
                      ? ` • ${drawing.pageCount} page(s)`
                      : ""}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {uploadModal}
    </div>
  );
}
