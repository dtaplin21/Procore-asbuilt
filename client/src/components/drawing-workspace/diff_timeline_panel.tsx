import { DrawingDiff } from "@/types/drawing_workspace";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";

type Props = {
  diffs: DrawingDiff[];
  selectedDiffId: number | null;
  loading: boolean;
  error: string | null;
  onSelectDiff: (diffId: number) => void;
  onRetry?: () => void;
};

function formatSeverity(severity?: string | null) {
  return severity || "Unspecified";
}

export default function DiffTimelinePanel({
  diffs,
  selectedDiffId,
  loading,
  error,
  onSelectDiff,
  onRetry,
}: Props) {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-foreground">Diff Timeline</h3>
      </div>

      <div className="max-h-[420px] overflow-y-auto">
        {loading ? (
          <div className="px-4 py-4 text-sm text-muted-foreground">Loading diffs...</div>
        ) : error ? (
          <div className="p-4">
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <div className="text-sm font-medium text-red-700">Failed to load diffs</div>
              <div className="mt-1 text-sm text-red-600">{error}</div>
              {onRetry ? (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-3 rounded-md border border-red-300 bg-white px-3 py-2 text-sm text-red-700 hover:bg-red-50"
                  data-testid="retry-diffs"
                >
                  Retry
                </button>
              ) : null}
            </div>
          </div>
        ) : diffs.length === 0 ? (
          <div className="p-4">
            <WorkspaceEmptyState
              title="No diffs"
              description="No diffs are available for the selected alignment."
            />
          </div>
        ) : (
          diffs.map((diff) => {
            const selected = diff.id === selectedDiffId;

            return (
              <button
                key={diff.id}
                type="button"
                onClick={() => onSelectDiff(diff.id)}
                data-testid={`diff-${diff.id}`}
                className={`w-full border-b border-border px-4 py-3 text-left transition hover:bg-muted/60 ${
                  selected
                    ? "border-l-4 border-l-primary bg-primary-soft"
                    : "border-l-4 border-l-transparent bg-card"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-foreground">
                      {diff.summary || `Diff #${diff.id}`}
                    </div>
                    {diff.createdAt ? (
                      <div className="mt-1 text-xs text-muted-foreground">
                        {new Date(diff.createdAt).toLocaleString()}
                      </div>
                    ) : null}
                  </div>

                  <span className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">
                    {formatSeverity(diff.severity)}
                  </span>
                </div>

                <div className="mt-2 text-xs text-muted-foreground/80">
                  Regions: {diff.diffRegions?.length ?? 0}
                </div>
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}
