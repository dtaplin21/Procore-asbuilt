import type { ProjectDrawingCandidate } from "@/types/drawing_workspace";

type Props = {
  drawing: ProjectDrawingCandidate;
  selected: boolean;
  onSelect: (drawingId: number) => void;
};

export default function SubDrawingListItem({
  drawing,
  selected,
  onSelect,
}: Props) {
  return (
    <button
      type="button"
      onClick={() => onSelect(drawing.id)}
      className={`w-full rounded-lg border px-4 py-3 text-left transition ${
        selected
          ? "border-primary bg-primary-soft"
          : "border-border bg-card hover:bg-muted/60"
      }`}
      data-testid={`sub-drawing-item-${drawing.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-foreground">
            {drawing.name}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Drawing #{drawing.id}
          </div>
        </div>

        {drawing.source ? (
          <span className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">
            {drawing.source}
          </span>
        ) : null}
      </div>
    </button>
  );
}
