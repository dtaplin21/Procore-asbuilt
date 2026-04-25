import { useEffect, useRef } from "react";
import type { DrawingResponse } from "@shared/schema";
import { useUploadProjectDrawing } from "@/hooks/use_upload_project_drawing";

export type DrawingUploadFieldProps = {
  projectId: number;
  /** When false, clears pending/error state (e.g. parent modal closed). */
  isActive: boolean;
  onUploaded: (drawing: DrawingResponse) => void | Promise<void>;
  /** Optional: parent can combine with other loading flags (e.g. compare in progress). */
  onUploadingChange?: (uploading: boolean) => void;
  disabled?: boolean;
  fileInputTestId?: string;
  /** Helper text under the button. */
  description?: string;
  /** When set, sent as multipart `upload_intent` on the upload request. */
  uploadIntent?: "master" | "sub";
};

/**
 * File picker + upload using {@link useUploadProjectDrawing}.
 * Use inside modals (compare sub drawing) or any screen that POSTs to `/api/projects/.../drawings`.
 */
export default function DrawingUploadField({
  projectId,
  isActive,
  onUploaded,
  onUploadingChange,
  disabled = false,
  fileInputTestId = "drawing-upload-file-input",
  description = "PDF or image. The file is added to this project.",
  uploadIntent,
}: DrawingUploadFieldProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const prevProjectIdRef = useRef<number | null>(null);
  const { uploading, uploadError, uploadDrawing, reset } = useUploadProjectDrawing();

  const clearFileInput = () => {
    const el = fileInputRef.current;
    if (el) el.value = "";
  };

  useEffect(() => {
    if (!isActive) {
      reset();
      clearFileInput();
    }
  }, [isActive, reset]);

  useEffect(() => {
    if (prevProjectIdRef.current === null) {
      prevProjectIdRef.current = projectId;
      return;
    }
    if (prevProjectIdRef.current !== projectId) {
      prevProjectIdRef.current = projectId;
      reset();
      clearFileInput();
    }
  }, [projectId, reset]);

  useEffect(() => {
    onUploadingChange?.(uploading);
  }, [uploading, onUploadingChange]);

  const handlePickFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !(file instanceof File)) return;
    // New selection: clear stale error/spinner state before this attempt
    reset();
    void (async () => {
      try {
        const drawing = await uploadDrawing(projectId, file, uploadIntent);
        await Promise.resolve(onUploaded(drawing));
        reset();
        clearFileInput();
      } catch {
        // uploadError is set on the hook
      }
    })();
  };

  const controlsDisabled = disabled || uploading;

  return (
    <div className="space-y-3">
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,image/*"
        className="hidden"
        data-testid={fileInputTestId}
        aria-label="Upload drawing file"
        onChange={handleFileChange}
        disabled={controlsDisabled}
      />
      <button
        type="button"
        onClick={handlePickFile}
        disabled={controlsDisabled}
        className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
      >
        {uploading ? "Uploading…" : "Choose file…"}
      </button>
      <p className="text-xs text-slate-500">{description}</p>
      {uploadError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {uploadError}
        </div>
      ) : null}
    </div>
  );
}
