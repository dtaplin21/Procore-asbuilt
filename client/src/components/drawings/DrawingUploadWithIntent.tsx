import { useEffect, useRef, useState, type ChangeEvent } from "react";
import type { DrawingResponse } from "@shared/schema";
import { useUploadProjectDrawing } from "@/hooks/use_upload_project_drawing";

export type DrawingUploadIntent = "master" | "sub";

export type DrawingUploadWithIntentProps = {
  projectId: number;
  /** Active workspace master id when comparing subs; omit or null blocks sub uploads. */
  workspaceMasterDrawingId?: number | null;
  allowMaster?: boolean;
  allowSub?: boolean;
  onComplete?: (
    drawing: DrawingResponse,
    intent: DrawingUploadIntent
  ) => void | Promise<void>;
  /** Fires when the internal upload hook busy state changes (e.g. modals use this to block dismiss). */
  onUploadingChange?: (uploading: boolean) => void;
  /** Overrides default copy when Master is selected. */
  masterWarningText?: string;
  /** Overrides default helper when Sub is selected but no master is available. */
  subDisabledReason?: string;
};

const DEFAULT_MASTER_WARNING =
  "Uploading a new master drawing should switch the active workspace to that drawing.";

const DEFAULT_SUB_NEEDS_MASTER =
  "A sub drawing requires an active master drawing. Open a workspace drawing first.";

/**
 * Upload UI with Master / Sub intent, conditional warnings, and multipart `upload_intent`.
 * Pass `workspaceMasterDrawingId` as a number (coerce route params before passing in).
 */
export function DrawingUploadWithIntent({
  projectId,
  workspaceMasterDrawingId = null,
  allowMaster = true,
  allowSub = true,
  onComplete,
  onUploadingChange,
  masterWarningText,
  subDisabledReason,
}: DrawingUploadWithIntentProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [intent, setIntent] = useState<DrawingUploadIntent>(() =>
    allowMaster ? "master" : "sub"
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const { uploading, uploadError, uploadDrawing, reset } =
    useUploadProjectDrawing();

  useEffect(() => {
    onUploadingChange?.(uploading);
  }, [uploading, onUploadingChange]);

  useEffect(() => {
    setIntent((prev) => {
      if (!allowMaster && prev === "master") {
        return allowSub ? "sub" : prev;
      }
      if (!allowSub && prev === "sub") {
        return allowMaster ? "master" : prev;
      }
      return prev;
    });
  }, [allowMaster, allowSub]);

  const subRequiresMaster =
    intent === "sub" &&
    (workspaceMasterDrawingId == null || !Number.isFinite(workspaceMasterDrawingId));
  const subAllowed = allowSub && !subRequiresMaster;

  async function handleUpload(file: File) {
    const response = await uploadDrawing(projectId, file, intent);
    await Promise.resolve(onComplete?.(response, intent));
  }

  async function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    reset();

    if (!file) return;
    if (intent === "sub" && !subAllowed) return;

    try {
      await handleUpload(file);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch {
      // uploadError (hook) or onComplete rejection (e.g. compare)
    }
  }

  const chooseDisabled =
    uploading || (intent === "sub" && !subAllowed) || (!allowMaster && !allowSub);

  return (
    <div className="space-y-4" data-testid="drawing-upload-with-intent">
      <div className="space-y-2">
        <div className="text-sm font-medium">Upload type</div>

        <div className="flex flex-wrap gap-4">
          {allowMaster ? (
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="radio"
                name="upload-intent"
                value="master"
                checked={intent === "master"}
                onChange={() => setIntent("master")}
                disabled={uploading}
                data-testid="upload-intent-master"
              />
              Master
            </label>
          ) : null}

          {allowSub ? (
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="radio"
                name="upload-intent"
                value="sub"
                checked={intent === "sub"}
                onChange={() => setIntent("sub")}
                disabled={uploading}
                data-testid="upload-intent-sub"
              />
              Sub
            </label>
          ) : null}
        </div>
      </div>

      {intent === "master" && allowMaster ? (
        <div
          className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100"
          role="status"
          data-testid="upload-master-warning"
        >
          {masterWarningText ?? DEFAULT_MASTER_WARNING}
        </div>
      ) : null}

      {intent === "sub" && subRequiresMaster && allowSub ? (
        <div
          className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100"
          role="status"
          data-testid="upload-sub-needs-master"
        >
          {subDisabledReason ?? DEFAULT_SUB_NEEDS_MASTER}
        </div>
      ) : null}

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,image/*"
        className="hidden"
        data-testid="drawing-upload-with-intent-file-input"
        aria-label="Upload drawing file"
        onChange={handleFileSelected}
        disabled={uploading}
      />

      <button
        type="button"
        className="inline-flex items-center rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
        onClick={() => fileInputRef.current?.click()}
        disabled={chooseDisabled}
        data-testid="drawing-upload-with-intent-choose-file"
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
          className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200"
          data-testid="upload-error"
        >
          {uploadError}
        </div>
      ) : null}
    </div>
  );
}

export default DrawingUploadWithIntent;
