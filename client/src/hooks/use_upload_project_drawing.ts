import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { DrawingResponse } from "@shared/schema";
import {
  projectDrawingsQueryKey,
  uploadProjectDrawing,
} from "@/lib/api/drawings";

/** Return type for {@link useUploadProjectDrawing} — safe to import in components and tests. */
export type UseUploadProjectDrawingResult = {
  uploading: boolean;
  uploadError: string | null;
  uploadDrawing: (projectId: number, file: File) => Promise<DrawingResponse>;
  /** Clears `uploadError` and `uploading`. Avoid calling mid-flight unless you intend to cancel UI state (see reset race note in hook). */
  reset: () => void;
};

export function useUploadProjectDrawing(): UseUploadProjectDrawingResult {
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setUploading(false);
    setUploadError(null);
  }, []);

  const uploadDrawing = useCallback(
    async (projectId: number, file: File): Promise<DrawingResponse> => {
      if (!(file instanceof File)) {
        const msg = "No file selected for upload";
        setUploadError(msg);
        throw new TypeError(msg);
      }
      setUploading(true);
      setUploadError(null);

      try {
        const drawing = await uploadProjectDrawing(projectId, file);
        await queryClient.invalidateQueries({
          queryKey: projectDrawingsQueryKey(projectId),
        });
        return drawing;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to upload drawing";
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
    uploadDrawing,
    reset,
  };
}
