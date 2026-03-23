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
          ? "border-slate-900 bg-slate-100"
          : "border-slate-200 bg-white hover:bg-slate-50"
      }`}
      data-testid={`sub-drawing-item-${drawing.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-slate-900">
            {drawing.name}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            Drawing #{drawing.id}
          </div>
        </div>

        {drawing.source ? (
          <span className="rounded-md border px-2 py-1 text-xs text-slate-600">
            {drawing.source}
          </span>
        ) : null}
      </div>
    </button>
  );
}
