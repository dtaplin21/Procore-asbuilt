import { useEffect, useRef, useState, type ChangeEvent } from "react";
import type { DrawingResponse } from "@shared/schema";
import { useUploadProjectDrawing } from "@/hooks/use_upload_project_drawing";

export type DrawingUploadProps = {
  projectId: number;
  /** When set, prompts to confirm replacing the project's canonical master before upload. */
  workspaceMasterDrawingId?: number | null;
  onComplete?: (drawing: DrawingResponse) => void | Promise<void>;
  onUploadingChange?: (uploading: boolean) => void;
  masterWarningText?: string;
  replaceConfirmMessage?: string;
};

const DEFAULT_MASTER_WARNING =
  "Uploading a new drawing adds it to this project as a master sheet.";

const DEFAULT_REPLACE_CONFIRM =
  "Replace this project's canonical master drawing? The workspace will switch to the new sheet.";

/**
 * Master-only drawing upload (PDF or image). All uploads are treated as master sheets.
 */
export function DrawingUpload({
  projectId,
  workspaceMasterDrawingId = null,
  onComplete,
  onUploadingChange,
  masterWarningText,
  replaceConfirmMessage = DEFAULT_REPLACE_CONFIRM,
}: DrawingUploadProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const projectHasCanonicalMaster =
    workspaceMasterDrawingId != null &&
    Number.isFinite(Number(workspaceMasterDrawingId));

  const { uploading, uploadError, uploadDrawing, reset } =
    useUploadProjectDrawing();

  useEffect(() => {
    onUploadingChange?.(uploading);
  }, [uploading, onUploadingChange]);

  async function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    reset();

    if (!file) return;

    if (projectHasCanonicalMaster) {
      const ok = window.confirm(replaceConfirmMessage);
      if (!ok) {
        setSelectedFile(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
        return;
      }
    }

    try {
      const response = await uploadDrawing(projectId, file);
      await Promise.resolve(onComplete?.(response));
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch {
      // uploadError (hook) or onComplete rejection
    }
  }

  return (
    <div className="space-y-4" data-testid="drawing-upload">
      <div
        className="rounded-md border border-primary bg-primary-soft px-3 py-2 text-sm text-foreground"
        role="status"
        data-testid="upload-master-warning"
      >
        {masterWarningText ?? DEFAULT_MASTER_WARNING}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,image/*"
        className="hidden"
        data-testid="drawing-upload-file-input"
        aria-label="Upload drawing file"
        onChange={handleFileSelected}
        disabled={uploading}
      />

      <button
        type="button"
        className="inline-flex items-center rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-60"
        onClick={() => fileInputRef.current?.click()}
        disabled={uploading}
        data-testid="drawing-upload-choose-file"
      >
        {uploading ? "Uploading…" : "Choose file"}
      </button>

      {selectedFile ? (
        <div className="text-sm text-muted-foreground" data-testid="upload-selected-filename">
          Selected: {selectedFile.name}
        </div>
      ) : null}

      {uploadError ? (
        <div
          className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          data-testid="upload-error"
        >
          {uploadError}
        </div>
      ) : null}
    </div>
  );
}

export default DrawingUpload;
