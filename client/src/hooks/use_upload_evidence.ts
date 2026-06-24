import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { EvidenceRecordResponse } from "@shared/schema";

import {
  invalidateProjectEvidenceQueries,
  uploadEvidence,
  type UploadEvidenceOptions,
} from "@/lib/api/evidence";

export type UseUploadEvidenceResult = {
  uploading: boolean;
  uploadError: string | null;
  uploadEvidenceFile: (
    projectId: number,
    file: File,
    options?: UploadEvidenceOptions
  ) => Promise<EvidenceRecordResponse>;
  reset: () => void;
};

export function useUploadEvidence(): UseUploadEvidenceResult {
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setUploading(false);
    setUploadError(null);
  }, []);

  const uploadEvidenceFile = useCallback(
    async (
      projectId: number,
      file: File,
      options?: UploadEvidenceOptions
    ): Promise<EvidenceRecordResponse> => {
      if (!(file instanceof File)) {
        const msg = "No file selected for upload";
        setUploadError(msg);
        throw new TypeError(msg);
      }
      setUploading(true);
      setUploadError(null);

      try {
        const evidence = await uploadEvidence(projectId, file, options);
        await invalidateProjectEvidenceQueries(queryClient, projectId);
        return evidence;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to upload evidence";
        setUploadError(message);
        throw error;
      } finally {
        setUploading(false);
      }
    },
    [queryClient]
  );

  return {
    uploading,
    uploadError,
    uploadEvidenceFile,
    reset,
  };
}
