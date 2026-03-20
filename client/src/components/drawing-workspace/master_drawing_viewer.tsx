import { DrawingDiff, DrawingSummary } from "@/types/drawing_workspace";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";

type Props = {
  drawing: DrawingSummary | null;
  selectedDiff: DrawingDiff | null;
};

export default function MasterDrawingViewer({ drawing, selectedDiff }: Props) {
  if (!drawing) {
    return (
      <WorkspaceEmptyState
        title="No drawing selected"
        description="The workspace could not load a master drawing."
      />
    );
  }

  const isPdf = drawing.contentType === "application/pdf";

  return (
    <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border bg-white">
      <div className="border-b px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{drawing.name}</h2>
            <p className="text-sm text-slate-500">
              Drawing #{drawing.id}
              {drawing.pageCount != null ? ` • ${drawing.pageCount} page(s)` : ""}
            </p>
          </div>

          <div className="text-right text-xs text-slate-500">
            <div>Source: {drawing.source || "unspecified"}</div>
            {selectedDiff ? <div>Selected diff: #{selectedDiff.id}</div> : <div>No diff selected</div>}
          </div>
        </div>
      </div>

      <div className="flex-1 bg-slate-50 p-4">
        {!drawing.fileUrl ? (
          <WorkspaceEmptyState
            title="Drawing file unavailable"
            description="The drawing metadata loaded, but no file URL is available yet."
          />
        ) : isPdf ? (
          <iframe
            title={drawing.name}
            src={drawing.fileUrl}
            className="h-full w-full rounded-lg border bg-white"
          />
        ) : (
          <img
            src={drawing.fileUrl}
            alt={drawing.name}
            className="h-full w-full rounded-lg border bg-white object-contain"
          />
        )}
      </div>
    </div>
  );
}
