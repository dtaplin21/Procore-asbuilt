import { useCallback, useState } from "react";

import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";
import { useRunDrawingDiff } from "@/hooks/use-drawing-diffs";
import type { DrawingAlignmentListItem } from "@/types/drawing_workspace";

export type AlignmentsPanelProps = {
  projectId: number;
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

export default function AlignmentsPanel({
  projectId,
  masterDrawingId,
  alignments,
  selectedAlignmentId,
  loading,
  onSelectAlignment,
  onRerunComplete,
}: AlignmentsPanelProps) {
  const runDrawingDiff = useRunDrawingDiff(
    String(projectId),
    String(masterDrawingId)
  );

  const [rerunError, setRerunError] = useState<string | null>(null);
  const [rerunningAlignmentId, setRerunningAlignmentId] = useState<number | null>(
    null
  );

  const handleRerun = useCallback(
    async (alignmentId: number) => {
      setRerunError(null);
      setRerunningAlignmentId(alignmentId);
      try {
        await runDrawingDiff.mutateAsync({ alignmentId });
        await onRerunComplete?.();
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to re-run comparison";
        setRerunError(message);
      } finally {
        setRerunningAlignmentId(null);
      }
    },
    [onRerunComplete, runDrawingDiff]
  );

  const busy = runDrawingDiff.isPending || rerunningAlignmentId != null;

  return (
    <section className="overflow-hidden rounded-xl border bg-white">
      <div className="border-b px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-900">Alignments</h3>
      </div>

      <div className="max-h-[320px] overflow-y-auto">
        {loading ? (
          <div className="px-4 py-4 text-sm text-slate-500">Loading alignments...</div>
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
            const rowRerunning = rerunningAlignmentId === alignment.id;

            return (
              <div
                key={alignment.id}
                className={`flex border-b last:border-b-0 ${
                  selected ? "bg-slate-100" : "bg-white"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelectAlignment(alignment.id)}
                  data-testid={`alignment-${alignment.id}`}
                  className="min-w-0 flex-1 px-4 py-3 text-left transition hover:bg-slate-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-slate-900">
                        {alignment.subDrawing.name}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        Sub drawing #{alignment.subDrawing.id}
                      </div>
                    </div>

                    <span className="shrink-0 rounded-md border px-2 py-1 text-xs text-slate-600">
                      {formatStatus(alignment.alignmentStatus)}
                    </span>
                  </div>

                  {alignment.createdAt ? (
                    <div className="mt-2 text-xs text-slate-400">
                      {new Date(alignment.createdAt).toLocaleString()}
                    </div>
                  ) : null}
                </button>

                <div className="flex shrink-0 flex-col justify-center border-l border-slate-200 px-2 py-2">
                  <button
                    type="button"
                    onClick={() => void handleRerun(alignment.id)}
                    disabled={busy}
                    data-testid={`alignment-rerun-${alignment.id}`}
                    className="whitespace-nowrap rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {rowRerunning ? "Re-running…" : "Re-run comparison"}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {rerunError ? (
        <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">
          {rerunError}
        </div>
      ) : null}
    </section>
  );
}
