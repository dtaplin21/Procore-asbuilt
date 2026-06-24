import { useCallback, useState } from "react";
import type { DrawingResponse } from "@shared/schema";

import { DrawingUpload } from "@/components/drawings/DrawingUpload";

export type UploadDrawingModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: number;
  /** Current workspace master; used for replace-master confirmation copy. */
  workspaceMasterDrawingId?: number | null;
  title?: string;
  description?: string;
  masterWarningText?: string;
  replaceConfirmMessage?: string;
  onUploadSuccess?: (drawing: DrawingResponse) => void | Promise<void>;
  /** If true (default), closes the dialog after `onUploadSuccess` resolves. */
  closeOnSuccess?: boolean;
  /** Extra busy state (e.g. navigation in progress). */
  isExternallyBusy?: boolean;
};

const defaultTitle = "Upload drawing";
const defaultDescription =
  "Select a PDF or image. The file is added to this project as a master sheet.";

/**
 * Modal shell around {@link DrawingUpload} for the drawing workspace and related screens.
 */
export function UploadDrawingModal({
  open,
  onOpenChange,
  projectId,
  workspaceMasterDrawingId = null,
  title = defaultTitle,
  description = defaultDescription,
  masterWarningText,
  replaceConfirmMessage,
  onUploadSuccess,
  closeOnSuccess = true,
  isExternallyBusy = false,
}: UploadDrawingModalProps) {
  const [uploading, setUploading] = useState(false);

  const isBusy = uploading || isExternallyBusy;

  const handleRequestClose = useCallback(() => {
    if (isBusy) return;
    onOpenChange(false);
  }, [isBusy, onOpenChange]);

  const handleComplete = useCallback(
    async (drawing: DrawingResponse) => {
      try {
        await onUploadSuccess?.(drawing);
        if (closeOnSuccess) {
          onOpenChange(false);
        }
      } catch {
        // Keep open: parent may have shown an error
      }
    },
    [onUploadSuccess, closeOnSuccess, onOpenChange]
  );

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={handleRequestClose}
      data-testid="upload-drawing-modal-backdrop"
    >
      <div
        className="w-full max-w-lg rounded-xl border border-border bg-card shadow-xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-busy={isBusy}
        aria-labelledby="upload-drawing-modal-title"
        data-testid="upload-drawing-modal"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <h2
              id="upload-drawing-modal-title"
              className="text-lg font-semibold text-foreground"
            >
              {title}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {description}
            </p>
          </div>
          <button
            type="button"
            onClick={handleRequestClose}
            disabled={isBusy}
            className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-muted disabled:opacity-60"
            aria-label="Close upload drawing modal"
            data-testid="upload-drawing-modal-close"
          >
            Close
          </button>
        </div>

        <div className="p-5">
          <DrawingUpload
            key={`${projectId}-${workspaceMasterDrawingId ?? "no-master"}`}
            projectId={projectId}
            workspaceMasterDrawingId={workspaceMasterDrawingId}
            onComplete={handleComplete}
            onUploadingChange={setUploading}
            masterWarningText={masterWarningText}
            replaceConfirmMessage={replaceConfirmMessage}
          />
        </div>
      </div>
    </div>
  );
}

export default UploadDrawingModal;
