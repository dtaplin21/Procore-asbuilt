import React, {
  useCallback,
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

/** Normalize parent prop to `string | null` for display (never render raw `Error`). */
function normalizeCompareErrorMessage(value: unknown): string | null {
  if (value == null || value === "") return null;
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message;
  return null;
}

export type CompareSubDrawingModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: number;
  masterDrawingId: number;
  /** UX-only label (e.g. from dashboard summary `current_drawing.name`). */
  currentDrawingName?: string | null;
  selectedDrawingId: number | null;
  /** Called when the user picks or uploads a sub drawing (numeric id only). Clear selection on route change in the parent. */
  onSelectSubDrawing?: (drawingId: number) => void;
  compareLoading?: boolean;
  compareError?: string | null;
  onConfirmCompare: (subDrawingId: number) => Promise<void> | void;
};

export default function CompareSubDrawingModal({
  open,
  onOpenChange,
  projectId,
  masterDrawingId,
  currentDrawingName = null,
  selectedDrawingId,
  onSelectSubDrawing,
  compareLoading,
  compareError = null,
  onConfirmCompare,
}: CompareSubDrawingModalProps) {
  const compareErrorMessage = normalizeCompareErrorMessage(compareError);

  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState<"choose" | "upload">("choose");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccessMessage, setUploadSuccessMessage] = useState<string | null>(
    null
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const { drawings, loading, error, reload } = useProjectDrawings({
    projectId,
    masterDrawingId,
    enabled: open,
  });

  const isBusy = uploading || Boolean(compareLoading);

  const updateSelection = useCallback(
    (drawingId: number) => {
      onSelectSubDrawing?.(drawingId);
    },
    [onSelectSubDrawing]
  );

  const resetUploadState = useCallback(() => {
    setUploading(false);
    setUploadError(null);
    setUploadSuccessMessage(null);
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  /** Block dismiss while upload or compare is in progress (backdrop, Escape, header/footer close). */
  const handleRequestClose = useCallback(() => {
    if (isBusy) return;
    resetUploadState();
    setActiveTab("choose");
    onOpenChange(false);
  }, [isBusy, onOpenChange, resetUploadState]);

  useEffect(() => {
    if (!open) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleRequestClose();
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [open, handleRequestClose]);

  useEffect(() => {
    if (!open) {
      setSearch("");
      setActiveTab("choose");
      resetUploadState();
    }
  }, [open, resetUploadState]);

  const prevWorkspaceRef = useRef<{
    projectId: number;
    masterDrawingId: number;
  } | null>(null);

  /** When the route workspace (project + master) changes, reset search/upload and sub pick — not on every `open` toggle. */
  useEffect(() => {
    const prev = prevWorkspaceRef.current;
    const next = { projectId, masterDrawingId };
    if (
      prev &&
      prev.projectId === next.projectId &&
      prev.masterDrawingId === next.masterDrawingId
    ) {
      return;
    }
    prevWorkspaceRef.current = next;
    if (!prev) return;

    setSearch("");
    setActiveTab("choose");
    resetUploadState();
  }, [projectId, masterDrawingId, resetUploadState]);

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
    updateSelection(drawingId);
  };

  const handleConfirm = async () => {
    // Use `== null` so drawing id `0` is still valid; do not use `!selectedDrawingId`.
    if (isBusy || selectedDrawingId == null) return;
    await Promise.resolve(onConfirmCompare(selectedDrawingId));
  };

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadError(null);

    try {
      const response = await uploadProjectDrawing(projectId, file, "sub");

      await reload();

      onSelectSubDrawing?.(response.id);
      setActiveTab("choose");
      setUploadSuccessMessage(
        currentDrawingName
          ? `Upload complete. Ready to compare against ${currentDrawingName}.`
          : "Upload complete. Ready to compare against the current workspace drawing."
      );
      setSelectedFile(null);
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
    if (isBusy) {
      event.target.value = "";
      return;
    }

    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    setSelectedFile(file);
    setUploadError(null);

    if (file) {
      void handleUpload(file);
    }
  }

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={handleRequestClose}
      data-testid="compare-sub-drawing-modal-backdrop"
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-busy={isBusy}
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
              Choose another drawing in this project or upload a new file. Comparison will use
              the active workspace drawing as the master.
            </p>
          </div>

          <button
            type="button"
            onClick={handleRequestClose}
            disabled={isBusy}
            className="rounded-md border px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            aria-label="Close compare sub drawing modal"
          >
            Close
          </button>
        </div>

        <div className="space-y-4 p-5">
          <Tabs
            value={activeTab}
            onValueChange={(value) => {
              if (isBusy) return;
              setActiveTab(value as "choose" | "upload");
            }}
            className="w-full"
          >
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger
                value="choose"
                data-testid="compare-tab-choose"
                disabled={isBusy}
              >
                Choose existing
              </TabsTrigger>
              <TabsTrigger
                value="upload"
                data-testid="compare-tab-upload"
                disabled={isBusy}
              >
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
                disabled={isBusy}
                onChange={handleFileChange}
              />

              <div className="space-y-3 rounded-lg border border-dashed p-4">
                <div className="text-sm font-medium">Upload a new drawing</div>
                <div className="text-sm text-muted-foreground">
                  This upload can be compared against the drawing open in this workspace.
                </div>
                <div className="text-sm text-muted-foreground">
                  Accepted: PDF, PNG, JPEG, or GIF (same rules as the server).
                </div>

                <button
                  type="button"
                  className="inline-flex items-center rounded-md border px-3 py-2 text-sm disabled:opacity-60"
                  onClick={() => {
                    if (isBusy) return;
                    fileInputRef.current?.click();
                  }}
                  disabled={isBusy}
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

          {uploadSuccessMessage ? (
            <div className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
              {uploadSuccessMessage}
            </div>
          ) : null}

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
              onClick={handleRequestClose}
              disabled={isBusy}
              className="rounded-md border px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={() => void handleConfirm()}
              disabled={selectedDrawingId == null || isBusy}
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
