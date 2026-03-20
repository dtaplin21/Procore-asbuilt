import { Link, useParams } from "wouter";

function preserveSearchParams(): string {
  const search = typeof window !== "undefined" ? window.location.search : "";
  return search ? `?${search}` : "";
}
import { useQuery } from "@tanstack/react-query";
import { FileImage } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { DrawingResponse } from "@shared/schema";

export default function DrawingPickerPage() {
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
        <h1 className="text-xl font-semibold text-slate-900 mb-4">Select a Drawing</h1>
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

  return (
    <div className="p-4">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-slate-900">Select a Drawing</h1>
        <p className="text-sm text-slate-500 mt-1">
          Project {projectId} • Choose a master drawing to open the workspace
        </p>
      </div>

      {list.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileImage className="w-12 h-12 mx-auto mb-3 text-slate-400" />
            <p className="text-sm text-slate-600">No drawings in this project yet.</p>
            <Link href="/">
              <Button variant="outline" className="mt-4">
                Back to Dashboard
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((drawing) => (
            <Link
              key={drawing.id}
              href={`/projects/${projectId}/drawings/${drawing.id}${preserveSearchParams()}`}
            >
              <Card className="cursor-pointer transition hover:bg-slate-50 hover:border-slate-300">
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
    </div>
  );
}
