import { useEffect, useMemo, useState } from "react";
import SubDrawingList from "@/components/drawing-workspace/sub_drawing_list";
import SubDrawingSearchInput from "@/components/drawing-workspace/sub_drawing_search_input";
import { useProjectDrawings } from "@/hooks/use_project_drawings";

type Props = {
  isOpen: boolean;
  projectId: number;
  masterDrawingId: number;
  onClose: () => void;
  onSelectSubDrawing?: (drawingId: number | null) => void;
};

export default function CompareSubDrawingModal({
  isOpen,
  projectId,
  masterDrawingId,
  onClose,
  onSelectSubDrawing,
}: Props) {
  const [search, setSearch] = useState("");
  const [selectedDrawingId, setSelectedDrawingId] = useState<number | null>(null);

  const { drawings, loading, error, reload } = useProjectDrawings({
    projectId,
    masterDrawingId,
    enabled: isOpen,
  });

  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) {
      setSearch("");
      setSelectedDrawingId(null);
    }
  }, [isOpen]);

  const filteredDrawings = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) {
      return drawings;
    }

    return drawings.filter((drawing) =>
      drawing.name.toLowerCase().includes(query)
    );
  }, [drawings, search]);

  const handleSelectDrawing = (drawingId: number) => {
    setSelectedDrawingId(drawingId);
    onSelectSubDrawing?.(drawingId);
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      data-testid="compare-sub-drawing-modal-backdrop"
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="compare-sub-drawing-title"
        data-testid="compare-sub-drawing-modal"
      >
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2
              id="compare-sub-drawing-title"
              className="text-lg font-semibold text-slate-900"
            >
              Compare a sub drawing
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Select a project drawing to compare against the current master drawing.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-md border px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            aria-label="Close compare sub drawing modal"
          >
            Close
          </button>
        </div>

        <div className="space-y-4 p-5">
          <SubDrawingSearchInput
            value={search}
            onChange={setSearch}
          />

          <SubDrawingList
            drawings={filteredDrawings}
            selectedDrawingId={selectedDrawingId}
            loading={loading}
            error={error}
            onSelect={handleSelectDrawing}
            onRetry={() => void reload()}
          />
        </div>

        <div className="flex items-center justify-between border-t px-5 py-4">
          <div className="text-sm text-slate-500">
            {selectedDrawingId
              ? `Selected drawing #${selectedDrawingId}`
              : "No sub drawing selected"}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-md border px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
