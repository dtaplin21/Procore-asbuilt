import { useCallback, useState } from "react";
import type { DrawingResponse } from "@shared/schema";
import { uploadProjectDrawing } from "@/lib/api/drawings";

export type UseUploadProjectDrawingResult = {
  uploading: boolean;
  uploadError: string | null;
  uploadDrawing: (projectId: number, file: File) => Promise<DrawingResponse>;
  reset: () => void;
};

export function useUploadProjectDrawing(): UseUploadProjectDrawingResult {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setUploadError(null);
    setUploading(false);
  }, []);

  const uploadDrawing = useCallback(
    async (projectId: number, file: File): Promise<DrawingResponse> => {
      setUploading(true);
      setUploadError(null);

      try {
        return await uploadProjectDrawing(projectId, file);
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
