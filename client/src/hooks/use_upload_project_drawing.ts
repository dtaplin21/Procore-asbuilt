import { useCallback, useState } from "react";
import type { DrawingResponse } from "@shared/schema";
import { uploadProjectDrawing } from "@/lib/api/drawings";

/** Return type for {@link useUploadProjectDrawing} — safe to import in components and tests. */
export type UseUploadProjectDrawingResult = {
  uploading: boolean;
  uploadError: string | null;
  uploadDrawing: (
    projectId: number,
    file: File,
    uploadIntent?: "master" | "sub"
  ) => Promise<DrawingResponse>;
  /** Clears `uploadError` and `uploading`. Avoid calling mid-flight unless you intend to cancel UI state (see reset race note in hook). */
  reset: () => void;
};

export function useUploadProjectDrawing(): UseUploadProjectDrawingResult {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setUploading(false);
    setUploadError(null);
  }, []);

  const uploadDrawing = useCallback(
    async (
      projectId: number,
      file: File,
      uploadIntent?: "master" | "sub"
    ): Promise<DrawingResponse> => {
      if (!(file instanceof File)) {
        const msg = "No file selected for upload";
        setUploadError(msg);
        throw new TypeError(msg);
      }
      setUploading(true);
      setUploadError(null);

      try {
        const drawing = await uploadProjectDrawing(
          projectId,
          file,
          uploadIntent
        );
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
    []
  );

  return {
    uploading,
    uploadError,
    uploadDrawing,
    reset,
  };
}
