import React, {
  useRef,
  useState,
  useEffect,
  useMemo,
} from "react";

import SubDrawingList from "@/components/drawing-workspace/sub_drawing_list";
import SubDrawingSearchInput from "@/components/drawing-workspace/sub_drawing_search_input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { uploadProjectDrawing } from "@/lib/api/drawings";
import { useProjectDrawings } from "@/hooks/use_project_drawings";

/** Matches `ALLOWED_CONTENT_TYPES` in `backend/services/file_storage.py` (drawings upload). */
const ACCEPTED_DRAWING_UPLOAD_TYPES =
  "application/pdf,image/png,image/jpeg,image/jpg,image/gif";

/** Normalize parent prop: UI only renders plain strings, never raw `Error` instances. */
function normalizeCompareErrorMessage(
  value: string | null | undefined
): string | null {
  if (value == null || value === "") return null;
  return typeof value === "string" ? value : null;
}

type Props = {
  isOpen: boolean;
  /** Numeric project id — parse route params with `Number(...)` / `coerceProjectIdForApi` before passing. */
  projectId: number;
  /** Current workspace (master) drawing id — numeric; parse route params before passing. */
  masterDrawingId: number;
  onClose: () => void;
  /** Notifies parent when the user picks a row or after a successful upload (`null` only from local resets). */
  onSelectSubDrawing?: (drawingId: number | null) => void;
  onConfirmCompare: (drawingId: number) => Promise<void>;
  compareLoading: boolean;
  /** Compare failure text from the parent hook — always `string | null`, never an `Error` object. */
  compareError?: string | null;
};

export default function CompareSubDrawingModal({
  isOpen,
  projectId,
  masterDrawingId,
  onClose,
  onSelectSubDrawing,
  onConfirmCompare,
  compareLoading,
  compareError = null,
}: Props) {
  const compareErrorMessage = normalizeCompareErrorMessage(compareError);

  const [search, setSearch] = useState("");
  const [selectedDrawingId, setSelectedDrawingId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"choose" | "upload">("choose");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const { drawings, loading, error, reload } = useProjectDrawings({
    projectId,
    masterDrawingId,
    enabled: isOpen,
  });

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
      setActiveTab("choose");
      setUploading(false);
      setUploadError(null);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [isOpen]);

  /** While open, reset pick/search when project context changes so nothing stale lingers. */
  useEffect(() => {
    if (!isOpen) return;
    setSearch("");
    setSelectedDrawingId(null);
    setActiveTab("choose");
    setUploading(false);
    setUploadError(null);
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [isOpen, projectId, masterDrawingId]);

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

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadError(null);

    try {
      const response = await uploadProjectDrawing(projectId, file);

      await reload();

      setSelectedDrawingId(response.id);
      onSelectSubDrawing?.(response.id);
      setSelectedFile(null);

      setActiveTab("choose");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to upload drawing";
      setUploadError(message);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } finally {
      setUploading(false);
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    setSelectedFile(file);
    setUploadError(null);

    if (file) {
      void handleUpload(file);
    }
  }

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
          <Tabs
            value={activeTab}
            onValueChange={(value) =>
              setActiveTab(value as "choose" | "upload")
            }
            className="w-full"
          >
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

            <TabsContent value="upload" className="mt-4 space-y-4">
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_DRAWING_UPLOAD_TYPES}
                className="hidden"
                data-testid="compare-upload-file-input"
                aria-label="Upload drawing file"
                disabled={compareLoading || uploading}
                onChange={handleFileChange}
              />

              <div className="space-y-3 rounded-lg border border-dashed p-4">
                <div className="text-sm font-medium">Upload a new sub drawing</div>
                <div className="text-sm text-muted-foreground">
                  Accepted: PDF, PNG, JPEG, or GIF (same rules as the server).
                </div>

                <button
                  type="button"
                  className="inline-flex items-center rounded-md border px-3 py-2 text-sm disabled:opacity-60"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={compareLoading || uploading}
                >
                  {uploading ? "Uploading..." : "Choose file"}
                </button>

                {selectedFile ? (
                  <div className="text-sm text-muted-foreground">
                    Selected: {selectedFile.name}
                  </div>
                ) : null}

                {uploadError ? (
                  <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                    {uploadError}
                  </div>
                ) : null}
              </div>
            </TabsContent>
          </Tabs>

          {compareErrorMessage ? (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <div>{compareErrorMessage}</div>
              <div className="mt-1 text-xs text-red-600">
                If this drawing was just uploaded, its render may still be processing. Please
                retry in a moment.
              </div>
            </div>
          ) : null}

          {uploadError ? (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {uploadError}
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
