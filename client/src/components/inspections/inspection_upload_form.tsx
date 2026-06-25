import { useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCanonicalMasterDrawing } from "@/hooks/use_canonical_master_drawing";
import { toast } from "@/hooks/use-toast";
import {
  createInspectionRun,
  uploadInspectionRunEvidence,
} from "@/lib/api/inspections";
import { refreshInspectionWorkspaceQueries } from "@/lib/api/inspection_runs";
import type { EvidenceUploadResponse } from "@/types/inspection_overlay";

export type InspectionUploadFormProps = {
  projectId: number;
  /** Override resolved master (tests / deep links). */
  initialMasterDrawingId?: string | null;
  /** Called after a successful upload with the new run and pipeline summary. */
  onUploaded?: (result: {
    runId: string;
    masterDrawingId: string;
    response: EvidenceUploadResponse;
  }) => void;
};

export default function InspectionUploadForm({
  projectId,
  initialMasterDrawingId = null,
  onUploaded,
}: InspectionUploadFormProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const {
    masterDrawingId: canonicalMasterId,
    name: canonicalMasterName,
    isLoading: canonicalLoading,
  } = useCanonicalMasterDrawing(projectId);

  const resolvedMasterDrawingId = useMemo(() => {
    if (initialMasterDrawingId) return initialMasterDrawingId;
    if (canonicalMasterId != null) return String(canonicalMasterId);
    return null;
  }, [initialMasterDrawingId, canonicalMasterId]);

  const masterDrawingName = useMemo(() => {
    if (initialMasterDrawingId) return `Drawing ${initialMasterDrawingId}`;
    return canonicalMasterName;
  }, [initialMasterDrawingId, canonicalMasterName]);

  const uploadDisabled = uploading || canonicalLoading || !resolvedMasterDrawingId;

  const handlePickFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !resolvedMasterDrawingId) return;

    setUploadError(null);
    setUploading(true);

    void (async () => {
      try {
        const run = await createInspectionRun({
          projectId: String(projectId),
          masterDrawingId: resolvedMasterDrawingId,
          skipPipeline: true,
        });

        const response = await uploadInspectionRunEvidence({
          projectId: String(projectId),
          runId: run.id,
          masterDrawingId: resolvedMasterDrawingId,
          file,
        });

        await refreshInspectionWorkspaceQueries(
          queryClient,
          projectId,
          Number(resolvedMasterDrawingId),
        );

        const parts = [
          `${response.overlays_created} overlay${response.overlays_created === 1 ? "" : "s"} mapped`,
        ];
        if (response.unresolved_count > 0) {
          parts.push(`${response.unresolved_count} need review`);
        }
        if (response.untagged_region_count > 0) {
          parts.push(`${response.untagged_region_count} untagged region(s) on sheet`);
        }

        toast({
          title: "Inspection uploaded",
          description: `Run #${run.id}: ${parts.join(" · ")}`,
        });

        onUploaded?.({
          runId: run.id,
          masterDrawingId: resolvedMasterDrawingId,
          response,
        });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to upload inspection";
        setUploadError(message);
        toast({
          title: "Upload failed",
          description: message,
          variant: "destructive",
        });
      } finally {
        setUploading(false);
      }
    })();
  };

  return (
    <div
      className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto]"
      data-testid="inspection-upload-form"
    >
      <div className="grid gap-2">
        <p
          className="text-sm text-muted-foreground"
          data-testid="inspection-upload-master-label"
        >
          Master sheet:{" "}
          {canonicalLoading ? (
            <span>Loading…</span>
          ) : masterDrawingName ? (
            <span className="font-medium text-foreground">{masterDrawingName}</span>
          ) : (
            <span>No canonical master sheet — upload a drawing on the Dashboard first.</span>
          )}
        </p>
        <p className="text-xs text-muted-foreground">
          Upload an inspection document (PDF or image). Findings are mapped onto the
          project master sheet — open the run on Objects to review overlays.
        </p>
        {uploadError ? (
          <p className="text-xs text-destructive" data-testid="inspection-upload-error">
            {uploadError}
          </p>
        ) : null}
      </div>

      <div className="flex flex-col justify-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,image/*"
          className="hidden"
          data-testid="inspection-upload-file-input"
          aria-label="Upload inspection document"
          onChange={handleFileChange}
          disabled={uploadDisabled}
        />
        <Button
          type="button"
          onClick={handlePickFile}
          disabled={uploadDisabled}
          data-testid="inspection-upload-submit"
        >
          {uploading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Processing…
            </>
          ) : (
            <>
              <Upload className="mr-2 h-4 w-4" />
              Upload inspection
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
