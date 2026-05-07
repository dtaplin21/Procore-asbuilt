import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import type { DrawingDeleteSummaryResponse } from "@shared/schema";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  deleteProjectDrawing,
  fetchDrawingDeleteSummary,
} from "@/lib/api/projects";
import { projectDrawingsQueryKey } from "@/lib/api/drawings";

type DrawingRow = {
  id: number;
  name: string;
};

export type DeleteDrawingDialogProps = {
  projectId: number;
  drawing: DrawingRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * After cache cleanup; receives the deleted drawing id (for conditional navigation, e.g. workspace route).
   */
  onDeleteSuccess?: (deletedDrawingId: number) => void | Promise<void>;
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

function drawingConfirmationLabel(d: DrawingRow): string {
  const t = d.name.trim();
  return t.length > 0 ? t : `Drawing ${d.id}`;
}

export function DeleteDrawingDialog({
  projectId,
  drawing,
  open,
  onOpenChange,
  onDeleteSuccess,
}: DeleteDrawingDialogProps) {
  const queryClient = useQueryClient();
  const drawingId = drawing?.id;
  const [confirmName, setConfirmName] = useState("");

  useEffect(() => {
    if (open) {
      setConfirmName("");
    }
  }, [open, drawing?.id]);

  const expectedName = drawing ? drawingConfirmationLabel(drawing) : "";
  const nameMatches =
    Boolean(drawing) &&
    expectedName.length > 0 &&
    confirmName.trim() === expectedName;
  const nameHint =
    confirmName.trim().length > 0 && !nameMatches
      ? "Type the full name exactly as shown above."
      : null;

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
      if (typeof drawingId !== "number" || !Number.isFinite(drawingId)) {
        onOpenChange(false);
        return;
      }
      const deletedId = drawingId;

      await queryClient.removeQueries({
        queryKey: projectDrawingsQueryKey(projectId),
      });
      await queryClient.removeQueries({
        queryKey: ["drawing-manage-dashboard-summary", projectId],
      });
      await queryClient.removeQueries({
        queryKey: ["drawing-picker-dashboard-summary", projectId],
      });
      await queryClient.removeQueries({
        queryKey: ["project-dashboard-summary", projectId],
      });
      queryClient.removeQueries({
        predicate: (q) => {
          const k = q.queryKey;
          if (!Array.isArray(k) || k[0] !== "drawing-diffs") return false;
          if (k[1] === "disabled") return false;
          const pid = k[1];
          return pid === projectId || pid === String(projectId);
        },
      });
      queryClient.removeQueries({
        predicate: (q) => {
          const k = q.queryKey;
          if (!Array.isArray(k)) return false;
          if (k[0] === "drawingComparisonWorkspace" && k[1] === projectId) {
            return k[2] === deletedId || k[3] === deletedId;
          }
          return false;
        },
      });
      queryClient.removeQueries({
        predicate: (q) => {
          const first = q.queryKey[0];
          return (
            typeof first === "string" &&
            first.startsWith(`/api/projects/${projectId}/drawings/${deletedId}`)
          );
        },
      });
      await queryClient.removeQueries({
        queryKey: ["drawing-delete-summary", projectId, deletedId],
      });

      await onDeleteSuccess?.(deletedId);
      onOpenChange(false);
    },
  });

  const summary = impactQuery.data;
  const hasImpactDetails = Boolean(summary) && !impactQuery.isError;
  const impactFailed = impactQuery.isError && !impactQuery.isFetching;

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      deleteMutation.reset();
      setConfirmName("");
    }
    onOpenChange(next);
  };

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent className="max-w-md" data-testid="delete-drawing-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Delete drawing?</AlertDialogTitle>
          <AlertDialogDescription className="sr-only">
            Review related data and type the drawing name exactly to confirm permanent
            deletion.
          </AlertDialogDescription>
          <div className="text-sm text-muted-foreground space-y-3 pt-1">
            {drawing ? (
              <p>
                <span className="font-medium text-foreground">
                  {drawingConfirmationLabel(drawing)}
                </span>{" "}
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

            {drawing && expectedName ? (
              <div className="space-y-2 pt-1 border-t border-border">
                <Label htmlFor="delete-drawing-confirm-name">
                  Type the drawing name to confirm
                </Label>
                <Input
                  id="delete-drawing-confirm-name"
                  value={confirmName}
                  onChange={(e) => setConfirmName(e.target.value)}
                  placeholder={expectedName}
                  autoComplete="off"
                  disabled={deleteMutation.isPending}
                  data-testid="delete-drawing-confirm-name"
                />
                {nameHint ? (
                  <p className="text-xs text-destructive" data-testid="delete-drawing-name-hint">
                    {nameHint}
                  </p>
                ) : null}
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
              typeof drawingId !== "number" ||
              !nameMatches
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
