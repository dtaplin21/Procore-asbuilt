import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileImage } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import type { DrawingResponse } from "@shared/schema";

import { UploadDrawingModal } from "@/components/drawing-workspace/UploadDrawingModal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function preserveSearchParams(): string {
  const search = typeof window !== "undefined" ? window.location.search : "";
  return search ? `?${search}` : "";
}

export default function DrawingPickerPage() {
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [, setLocation] = useLocation();
  const params = useParams<{ projectId: string }>();
  const projectId = params?.projectId ?? "";

  const { data: drawings, isLoading, error } = useQuery<DrawingResponse[]>({
    queryKey: [`/api/projects/${projectId}/drawings`],
    enabled: !!projectId,
  });

  const parsedProjectId = Number(projectId);
  const isValidProject = Number.isFinite(parsedProjectId);

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

  if (isLoading) {
    return (
      <div className="p-4">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100 mb-4">
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

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">Failed to load drawings.</p>
        <Link href="/">
          <Button variant="outline" className="mt-4">
            Back to Dashboard
          </Button>
        </Link>
      </div>
    );
  }

  const list = drawings ?? [];

  const uploadModal = (
    <UploadDrawingModal
      open={uploadModalOpen}
      onOpenChange={setUploadModalOpen}
      projectId={parsedProjectId}
      allowMaster
      allowSub={false}
      onUploadSuccess={(drawing) => {
        setLocation(
          `/projects/${projectId}/drawings/${drawing.id}/workspace${preserveSearchParams()}`
        );
      }}
    />
  );

  return (
    <div className="p-4">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Select a Drawing
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Project {projectId} • Choose a master drawing to open the workspace
          </p>
        </div>
        <button
          type="button"
          className="inline-flex w-full shrink-0 items-center justify-center rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 sm:w-auto dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
          onClick={() => setUploadModalOpen(true)}
          data-testid="drawing-picker-upload-open"
        >
          Upload drawing
        </button>
      </div>

      {list.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileImage className="w-12 h-12 mx-auto mb-3 text-slate-400" />
            <p className="text-sm text-slate-600 dark:text-slate-300">
              No drawings in this project yet.
            </p>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
              Upload a master drawing to open the workspace, or return to the dashboard.
            </p>
            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <button
                type="button"
                className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
                onClick={() => setUploadModalOpen(true)}
                data-testid="drawing-picker-empty-upload"
              >
                Upload drawing
              </button>
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
              href={`/projects/${projectId}/drawings/${drawing.id}/workspace${preserveSearchParams()}`}
            >
              <Card className="cursor-pointer transition hover:bg-slate-50 hover:border-slate-300 dark:hover:bg-slate-900/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base font-medium truncate">
                    {drawing.name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  <p className="text-xs text-slate-500">
                    Drawing #{drawing.id}
                    {drawing.page_count != null ? ` • ${drawing.page_count} page(s)` : ""}
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
