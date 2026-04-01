import type { DrawingAlignmentListItem } from "@/types/drawing_workspace";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";

type Props = {
  alignments: DrawingAlignmentListItem[];
  selectedAlignmentId: number | null;
  loading: boolean;
  onSelectAlignment: (alignmentId: number) => void | Promise<void>;
};

function formatStatus(status?: string | null) {
  if (!status) return "Unknown";
  return status.replaceAll("_", " ");
}

export default function AlignmentsPanel({
  alignments,
  selectedAlignmentId,
  loading,
  onSelectAlignment,
}: Props) {
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

            return (
              <button
                key={alignment.id}
                type="button"
                onClick={() => onSelectAlignment(alignment.id)}
                data-testid={`alignment-${alignment.id}`}
                className={`w-full border-b px-4 py-3 text-left transition hover:bg-slate-50 ${
                  selected ? "bg-slate-100" : "bg-white"
                }`}
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

                  <span className="rounded-md border px-2 py-1 text-xs text-slate-600">
                    {formatStatus(alignment.alignmentStatus)}
                  </span>
                </div>

                {alignment.createdAt ? (
                  <div className="mt-2 text-xs text-slate-400">
                    {new Date(alignment.createdAt).toLocaleString()}
                  </div>
                ) : null}
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}
