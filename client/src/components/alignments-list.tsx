import { useQuery } from "@tanstack/react-query";
import { ListOrdered } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import type {
  DrawingResponse,
  DrawingAlignmentResponse,
  DrawingAlignmentListResponse,
  AlignmentUpdate,
} from "@shared/schema";

interface AlignmentsListProps {
  projectId: string | null;
  masterDrawingId: string | null;
  drawings: DrawingResponse[];
}

const statusConfig: Record<
  "queued" | "processing" | "complete" | "failed",
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  queued: { label: "Queued", variant: "secondary" },
  processing: { label: "Processing", variant: "outline" },
  complete: { label: "Complete", variant: "default" },
  failed: { label: "Failed", variant: "destructive" },
};

function resolveDrawingName(drawings: DrawingResponse[], id: number): string {
  const d = drawings.find((x) => x.id === id);
  return d?.name || `Drawing ${id}`;
}

export function AlignmentsList({
  projectId,
  masterDrawingId,
  drawings,
}: AlignmentsListProps) {
  const { data: alignmentsData, isLoading } = useQuery<DrawingAlignmentListResponse>({
    queryKey: [
      `/api/projects/${projectId}/drawings/${masterDrawingId}/alignments`,
    ],
    enabled: !!projectId && !!masterDrawingId,
  });

  if (!projectId || !masterDrawingId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListOrdered className="w-5 h-5" />
            Alignments
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Select a project and master drawing to view alignments.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListOrdered className="w-5 h-5" />
            Alignments
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const list: DrawingAlignmentResponse[] = alignmentsData?.items ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ListOrdered className="w-5 h-5" />
          Alignments
        </CardTitle>
      </CardHeader>
      <CardContent>
        {list.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No alignments yet. Attach a sub-drawing above.
          </p>
        ) : (
          <div className="space-y-3">
            {list.map((a) => {
              const config = statusConfig[a.status as keyof typeof statusConfig] ?? {
                label: a.status,
                variant: "outline" as const,
              };
              return (
                <div
                  key={a.id}
                  className="flex flex-col gap-1 rounded-lg border p-3"
                >
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className="font-medium text-sm">
                      {resolveDrawingName(drawings, a.sub_drawing_id)}
                    </span>
                    <Badge variant={config.variant}>{config.label}</Badge>
                  </div>
                  {a.status === "failed" && a.error_message && (
                    <p className="text-xs text-destructive">
                      {a.error_message}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
