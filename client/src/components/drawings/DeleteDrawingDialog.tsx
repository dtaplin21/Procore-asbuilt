import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import type { DrawingDeleteSummaryResponse } from "@shared/schema";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  deleteProjectDrawing,
  fetchDrawingDeleteSummary,
} from "@/lib/api/projects";

type DrawingRow = {
  id: number;
  name: string;
};

export type DeleteDrawingDialogProps = {
  projectId: number;
  drawing: DrawingRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function impactLines(summary: DrawingDeleteSummaryResponse) {
  return [
    { label: "Alignments", count: summary.alignmentsCount },
    { label: "Diffs", count: summary.diffsCount },
    { label: "Regions", count: summary.regionsCount },
    { label: "Overlays", count: summary.overlaysCount },
    {
      label: "Findings linked to this sheet",
      count: summary.findingsWithDrawingCount,
    },
    { label: "Evidence links", count: summary.evidenceLinksCount },
  ];
}

const STATIC_IMPACT_COPY =
  "This removes the uploaded file and related comparison data from the project. Findings keep their records but may lose the link to this sheet.";

export function DeleteDrawingDialog({
  projectId,
  drawing,
  open,
  onOpenChange,
}: DeleteDrawingDialogProps) {
  const queryClient = useQueryClient();
  const drawingId = drawing?.id;

  const impactQuery = useQuery({
    queryKey: ["drawing-delete-summary", projectId, drawingId],
    queryFn: () => fetchDrawingDeleteSummary(projectId, drawingId!),
    enabled:
      open &&
      typeof drawingId === "number" &&
      Number.isFinite(drawingId) &&
      Number.isFinite(projectId),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (typeof drawingId !== "number" || !Number.isFinite(drawingId)) {
        throw new Error("Invalid drawing");
      }
      await deleteProjectDrawing(projectId, drawingId);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: [`/api/projects/${projectId}/drawings`],
      });
      await queryClient.invalidateQueries({
        queryKey: ["drawing-manage-dashboard-summary", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["drawing-picker-dashboard-summary", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["project-dashboard-summary"],
      });
      await queryClient.removeQueries({
        queryKey: ["drawing-delete-summary", projectId, drawingId],
      });
      onOpenChange(false);
    },
  });

  const summary = impactQuery.data;
  const hasImpactDetails = Boolean(summary) && !impactQuery.isError;
  const impactFailed = impactQuery.isError && !impactQuery.isFetching;

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      deleteMutation.reset();
    }
    onOpenChange(next);
  };

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent className="max-w-md" data-testid="delete-drawing-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Delete drawing?</AlertDialogTitle>
          <div className="text-sm text-muted-foreground space-y-3 pt-1">
            {drawing ? (
              <p>
                <span className="font-medium text-foreground">{drawing.name}</span>{" "}
                (ID {drawing.id}) will be permanently removed.
              </p>
            ) : null}

            {impactQuery.isLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                Loading impact summary…
              </div>
            ) : null}

            {hasImpactDetails && summary ? (
              <>
                {summary.isCanonicalMaster ? (
                  <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
                    This is the project&apos;s canonical master sheet. After deletion,
                    the project will have no master until you upload or assign one.
                  </p>
                ) : null}
                <p className="font-medium text-foreground text-xs uppercase tracking-wide">
                  Related data
                </p>
                <ul className="list-disc pl-5 space-y-1 text-foreground/90">
                  {impactLines(summary).map(({ label, count }) => (
                    <li key={label}>
                      {label}: <strong>{count}</strong>
                    </li>
                  ))}
                </ul>
                {summary.findingsWithDrawingCount > 0 ? (
                  <p className="text-xs">
                    Findings stay in the project; their drawing reference will be
                    cleared.
                  </p>
                ) : null}
              </>
            ) : null}

            {!impactQuery.isLoading && impactFailed ? (
              <div className="space-y-1">
                <p>{STATIC_IMPACT_COPY}</p>
                <p className="text-xs">Detailed counts could not be loaded.</p>
              </div>
            ) : null}
          </div>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            type="button"
            disabled={deleteMutation.isPending}
            data-testid="delete-drawing-cancel"
          >
            Cancel
          </AlertDialogCancel>
          <Button
            type="button"
            variant="destructive"
            disabled={
              deleteMutation.isPending ||
              impactQuery.isLoading ||
              typeof drawingId !== "number"
            }
            onClick={() => deleteMutation.mutate()}
            data-testid="delete-drawing-confirm"
          >
            {deleteMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Deleting…
              </>
            ) : (
              "Delete"
            )}
          </Button>
        </AlertDialogFooter>
        {deleteMutation.isError ? (
          <p className="text-sm text-red-600" data-testid="delete-drawing-error">
            {deleteMutation.error instanceof Error
              ? deleteMutation.error.message
              : "Delete failed."}
          </p>
        ) : null}
      </AlertDialogContent>
    </AlertDialog>
  );
}
