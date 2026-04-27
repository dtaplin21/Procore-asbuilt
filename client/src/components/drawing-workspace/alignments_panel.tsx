import { useCallback, useState } from "react";

import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";
import { useRunDrawingDiff } from "@/hooks/use-drawing-diffs";
import type { DrawingAlignmentListItem } from "@/types/drawing_workspace";

export type AlignmentsPanelProps = {
  /** Finite project id; parent should validate route params before rendering. */
  projectId: number;
  /** Finite master drawing id (route); parent should validate route params before rendering. */
  masterDrawingId: number;
  alignments: DrawingAlignmentListItem[];
  selectedAlignmentId: number | null;
  loading: boolean;
  onSelectAlignment: (alignmentId: number) => void | Promise<void>;
  /** Called after a successful re-run so the parent can refresh diffs / timeline. */
  onRerunComplete?: () => void | Promise<void>;
};

function formatStatus(status?: string | null) {
  if (!status) return "Unknown";
  return status.replaceAll("_", " ");
}

function unknownToErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  return fallback;
}

export default function AlignmentsPanel({
  projectId,
  masterDrawingId,
  alignments,
  selectedAlignmentId,
  loading,
  onSelectAlignment,
  onRerunComplete,
}: AlignmentsPanelProps) {
  const runDrawingDiffMutation = useRunDrawingDiff(
    String(projectId),
    String(masterDrawingId)
  );

  /** Which alignment row is currently re-running (only that row shows loading / disabled). */
  const [rerunningAlignmentId, setRerunningAlignmentId] = useState<number | null>(
    null
  );
  /** MVP: one visible error under the panel header. For per-row copy, use `Record<number, string>`. */
  const [rerunError, setRerunError] = useState<string | null>(null);

  const handleRerunComparison = useCallback(
    async (alignmentId: number) => {
      setRerunningAlignmentId(alignmentId);
      setRerunError(null);

      try {
        // `useRunDrawingDiff` above already scoped POST to projectId + masterDrawingId; mutate only takes alignmentId.
        await runDrawingDiffMutation.mutateAsync({ alignmentId });
        await onRerunComplete?.();
      } catch (error) {
        setRerunError(
          unknownToErrorMessage(error, "Failed to re-run comparison")
        );
      } finally {
        setRerunningAlignmentId(null);
      }
    },
    [onRerunComplete, runDrawingDiffMutation]
  );

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-foreground">Alignments</h3>
      </div>

      {rerunError && (
        <div className="px-4">
          <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {rerunError}
          </div>
        </div>
      )}

      <div className="max-h-[320px] overflow-y-auto">
        {loading ? (
          <div className="px-4 py-4 text-sm text-muted-foreground">Loading alignments...</div>
        ) : alignments.length === 0 ? (
          <div className="p-4">
            <WorkspaceEmptyState
              title="No alignments"
              description="No alignments are available for this master drawing yet."
            />
          </div>
        ) : (
          alignments.map((alignment) => {
            const selected = alignment.id === selectedAlignmentId;

            return (
              <div
                key={alignment.id}
                className={`flex border-b border-border last:border-b-0 ${
                  selected
                    ? "border-l-4 border-l-primary bg-primary-soft"
                    : "border-l-4 border-l-transparent bg-card"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelectAlignment(alignment.id)}
                  data-testid={`alignment-${alignment.id}`}
                  className="min-w-0 flex-1 px-4 py-3 text-left transition hover:bg-muted/60"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-foreground">
                        {alignment.subDrawing.name}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Sub drawing #{alignment.subDrawing.id}
                      </div>
                    </div>

                    <span className="shrink-0 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">
                      {formatStatus(alignment.alignmentStatus)}
                    </span>
                  </div>

                  {alignment.createdAt ? (
                    <div className="mt-2 text-xs text-muted-foreground/80">
                      {new Date(alignment.createdAt).toLocaleString()}
                    </div>
                  ) : null}
                </button>

                <div className="flex shrink-0 flex-col justify-center border-l border-border px-2 py-2">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      void handleRerunComparison(alignment.id);
                    }}
                    disabled={rerunningAlignmentId === alignment.id}
                    aria-busy={rerunningAlignmentId === alignment.id}
                    data-testid={`alignment-rerun-${alignment.id}`}
                    className="inline-flex items-center rounded-md border border-border bg-background px-2 py-1 text-xs font-medium text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {rerunningAlignmentId === alignment.id
                      ? "Re-running..."
                      : "Re-run comparison"}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
