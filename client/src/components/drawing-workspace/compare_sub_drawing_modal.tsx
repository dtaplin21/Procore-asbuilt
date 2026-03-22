import { useEffect } from "react";

type Props = {
  isOpen: boolean;
  onClose: () => void;
};

export default function CompareSubDrawingModal({
  isOpen,
  onClose,
}: Props) {
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
        className="w-full max-w-lg rounded-xl bg-white shadow-xl"
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
              Select a sub drawing to compare against the current master drawing.
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

        <div className="p-5">
          <div className="rounded-lg border border-dashed p-4 text-sm text-slate-500">
            Sub drawing selection UI goes here in Phase 3.2.
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 border-t px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
