import { useEffect, useMemo, useRef, useState } from "react";

import SubDrawingList from "@/components/drawing-workspace/sub_drawing_list";
import SubDrawingSearchInput from "@/components/drawing-workspace/sub_drawing_search_input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useProjectDrawings } from "@/hooks/use_project_drawings";
import { useUploadProjectDrawing } from "@/hooks/use_upload_project_drawing";

type Props = {
  isOpen: boolean;
  projectId: number;
  masterDrawingId: number;
  onClose: () => void;
  onSelectSubDrawing?: (drawingId: number | null) => void;
  onConfirmCompare: (drawingId: number) => Promise<void>;
  compareLoading: boolean;
  compareError: string | null;
};

export default function CompareSubDrawingModal({
  isOpen,
  projectId,
  masterDrawingId,
  onClose,
  onSelectSubDrawing,
  onConfirmCompare,
  compareLoading,
  compareError,
}: Props) {
  const [search, setSearch] = useState("");
  const [selectedDrawingId, setSelectedDrawingId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { drawings, loading, error, reload } = useProjectDrawings({
    projectId,
    masterDrawingId,
    enabled: isOpen,
  });

  const {
    uploading,
    uploadError,
    uploadDrawing,
    reset: resetUpload,
  } = useUploadProjectDrawing();

  const busy = compareLoading || uploading;

  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen, onClose, busy]);

  useEffect(() => {
    if (!isOpen) {
      setSearch("");
      setSelectedDrawingId(null);
      resetUpload();
    }
  }, [isOpen, resetUpload]);

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

  const handleConfirm = async () => {
    if (selectedDrawingId == null || busy) return;
    await onConfirmCompare(selectedDrawingId);
  };

  const handlePickFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    void (async () => {
      try {
        const drawing = await uploadDrawing(projectId, file);
        await reload();
        setSelectedDrawingId(drawing.id);
        onSelectSubDrawing?.(drawing.id);
      } catch {
        // uploadError set inside hook
      }
    })();
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={() => {
        if (!busy) onClose();
      }}
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
              Choose an existing project drawing or upload a new file, then compare.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            aria-label="Close compare sub drawing modal"
          >
            Close
          </button>
        </div>

        <div className="space-y-4 p-5">
          <Tabs defaultValue="choose" className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="choose" data-testid="compare-tab-choose">
                Choose existing
              </TabsTrigger>
              <TabsTrigger value="upload" data-testid="compare-tab-upload">
                Upload new
              </TabsTrigger>
            </TabsList>

            <TabsContent value="choose" className="mt-4 space-y-4">
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
            </TabsContent>

            <TabsContent value="upload" className="mt-4 space-y-3">
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,image/*"
                className="hidden"
                data-testid="compare-upload-file-input"
                aria-label="Upload drawing file"
                onChange={handleFileChange}
              />
              <button
                type="button"
                onClick={handlePickFile}
                disabled={uploading}
                className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
              >
                {uploading ? "Uploading…" : "Choose file…"}
              </button>
              <p className="text-xs text-slate-500">
                PDF or image. The file is added to this project; then use Compare below.
              </p>
              {uploadError ? (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {uploadError}
                </div>
              ) : null}
            </TabsContent>
          </Tabs>

          {compareError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <div className="text-sm font-medium text-red-700">
                Compare failed
              </div>
              <div className="mt-1 text-sm text-red-600">{compareError}</div>
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-between border-t px-5 py-4">
          <div className="text-sm text-slate-500">
            {selectedDrawingId
              ? `Selected drawing #${selectedDrawingId}`
              : "No sub drawing selected"}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-md border px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={() => void handleConfirm()}
              disabled={selectedDrawingId == null || busy}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              data-testid="confirm-compare-sub-drawing-button"
            >
              {compareLoading ? "Comparing..." : "Compare"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
