import type { ProjectDrawingCandidate } from "@/types/drawing_workspace";
import SubDrawingListItem from "@/components/drawing-workspace/sub_drawing_list_item";

type Props = {
  drawings: ProjectDrawingCandidate[];
  selectedDrawingId: number | null;
  loading: boolean;
  error: string | null;
  onSelect: (drawingId: number) => void;
  onRetry?: () => void;
};

export default function SubDrawingList({
  drawings,
  selectedDrawingId,
  loading,
  error,
  onSelect,
  onRetry,
}: Props) {
  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
        Loading sub drawings...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4">
        <div className="text-sm font-medium text-red-700">
          Failed to load sub drawings
        </div>
        <div className="mt-1 text-sm text-red-700">{error}</div>

        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded-md border border-red-300 bg-card px-3 py-2 text-sm text-red-800 hover:bg-red-50"
          >
            Retry
          </button>
        ) : null}
      </div>
    );
  }

  if (drawings.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
        No candidate sub drawings were found for this project.
      </div>
    );
  }

  return (
    <div className="max-h-[320px] space-y-2 overflow-y-auto pr-1">
      {drawings.map((drawing) => (
        <SubDrawingListItem
          key={drawing.id}
          drawing={drawing}
          selected={drawing.id === selectedDrawingId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
