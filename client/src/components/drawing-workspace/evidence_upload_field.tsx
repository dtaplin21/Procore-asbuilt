import { useEffect, useRef } from "react";
import type { EvidenceRecordResponse } from "@shared/schema";

import { useUploadEvidence, type UseUploadEvidenceResult } from "@/hooks/use_upload_evidence";
import type { UploadEvidenceOptions } from "@/lib/api/evidence";

export type EvidenceUploadFieldProps = {
  projectId: number;
  /** When false, clears pending/error state (e.g. parent panel unmounted). */
  isActive?: boolean;
  onUploaded: (evidence: EvidenceRecordResponse) => void | Promise<void>;
  onUploadingChange?: (uploading: boolean) => void;
  disabled?: boolean;
  fileInputTestId?: string;
  description?: string;
  uploadOptions?: UploadEvidenceOptions;
};

/**
 * File picker + upload using {@link useUploadEvidence}.
 * POSTs to `/api/projects/.../evidence` (see backend/api/routes/evidence.py).
 */
export default function EvidenceUploadField({
  projectId,
  isActive = true,
  onUploaded,
  onUploadingChange,
  disabled = false,
  fileInputTestId = "evidence-upload-file-input",
  description = "PDF or image. Uploading starts an inspection when no run is in progress.",
  uploadOptions,
}: EvidenceUploadFieldProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const prevProjectIdRef = useRef<number | null>(null);
  const { uploading, uploadError, uploadEvidenceFile, reset }: UseUploadEvidenceResult =
    useUploadEvidence();

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
    reset();
    void (async () => {
      try {
        const evidence = await uploadEvidenceFile(projectId, file, uploadOptions);
        await Promise.resolve(onUploaded(evidence));
        reset();
        clearFileInput();
      } catch {
        // uploadError is set on the hook
      }
    })();
  };

  const controlsDisabled = disabled || uploading;

  return (
    <div className="space-y-2">
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,image/*"
        className="hidden"
        data-testid={fileInputTestId}
        aria-label="Upload evidence file"
        onChange={handleFileChange}
        disabled={controlsDisabled}
      />
      <button
        type="button"
        onClick={handlePickFile}
        disabled={controlsDisabled}
        data-testid="evidence-upload-choose"
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-60"
      >
        {uploading ? "Uploading evidence…" : "Upload evidence…"}
      </button>
      <p className="text-xs text-muted-foreground">{description}</p>
      {uploadError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-800">
          {uploadError}
        </div>
      ) : null}
    </div>
  );
}
