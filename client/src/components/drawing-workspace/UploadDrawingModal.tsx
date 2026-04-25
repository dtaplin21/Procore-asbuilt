import { useCallback, useState } from "react";
import type { DrawingResponse } from "@shared/schema";

import {
  DrawingUploadWithIntent,
  type DrawingUploadIntent,
} from "@/components/drawings/DrawingUploadWithIntent";

export type { DrawingUploadIntent };

export type UploadDrawingModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: number;
  /** Current workspace master; required for sub uploads in workspace flows. */
  workspaceMasterDrawingId?: number | null;
  allowMaster?: boolean;
  allowSub?: boolean;
  title?: string;
  description?: string;
  masterWarningText?: string;
  subDisabledReason?: string;
  /**
   * After a successful file upload. Use for navigation (master) or compare (sub).
   * If this throws (e.g. compare failed), the modal stays open.
   */
  onUploadSuccess?: (
    drawing: DrawingResponse,
    intent: DrawingUploadIntent
  ) => void | Promise<void>;
  /** If true (default), closes the dialog after `onUploadSuccess` resolves. */
  closeOnSuccess?: boolean;
  /** Extra busy state (e.g. workspace compare in progress after sub upload). */
  isExternallyBusy?: boolean;
};

const defaultTitle = "Upload drawing";
const defaultDescription =
  "Choose whether this file is a master (workspace sheet) or a sub to compare, then select a file.";

/**
 * Modal shell around {@link DrawingUploadWithIntent} with workflow callbacks for the drawing workspace and related screens.
 */
export function UploadDrawingModal({
  open,
  onOpenChange,
  projectId,
  workspaceMasterDrawingId = null,
  allowMaster = true,
  allowSub = true,
  title = defaultTitle,
  description = defaultDescription,
  masterWarningText,
  subDisabledReason,
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
    async (drawing: DrawingResponse, intent: DrawingUploadIntent) => {
      try {
        await onUploadSuccess?.(drawing, intent);
        if (closeOnSuccess) {
          onOpenChange(false);
        }
      } catch {
        // Keep open: parent may have shown compare/workspace error
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
        className="w-full max-w-lg rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-busy={isBusy}
        aria-labelledby="upload-drawing-modal-title"
        data-testid="upload-drawing-modal"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div>
            <h2
              id="upload-drawing-modal-title"
              className="text-lg font-semibold text-slate-900 dark:text-slate-100"
            >
              {title}
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {description}
            </p>
          </div>
          <button
            type="button"
            onClick={handleRequestClose}
            disabled={isBusy}
            className="shrink-0 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            aria-label="Close upload drawing modal"
            data-testid="upload-drawing-modal-close"
          >
            Close
          </button>
        </div>

        <div className="p-5">
          <DrawingUploadWithIntent
            key={`${projectId}-${workspaceMasterDrawingId ?? "no-master"}`}
            projectId={projectId}
            workspaceMasterDrawingId={workspaceMasterDrawingId}
            allowMaster={allowMaster}
            allowSub={allowSub}
            onComplete={handleComplete}
            onUploadingChange={setUploading}
            masterWarningText={masterWarningText}
            subDisabledReason={subDisabledReason}
          />
        </div>
      </div>
    </div>
  );
}

export default UploadDrawingModal;
