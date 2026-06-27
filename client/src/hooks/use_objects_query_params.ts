/**
 * Centralizes the Objects page's URL query param reading/writing —
 * projectId, drawingId, run, overlay, region. Extracted out of objects.tsx
 * per the merge plan's "Files to create" list, so the param-sync logic isn't
 * duplicated between the page component and anywhere else that needs to
 * read or update these params (e.g. a future overlay-focus action).
 *
 * Uses react-router-dom's useSearchParams, matching objects.tsx's
 * existing router per the merge plan's risk note ("objects.tsx uses
 * useSearchParams from react-router-dom while other pages use wouter;
 * align during refactor"). If your app standardizes on wouter instead,
 * swap the import below for wouter's useSearchParams — the rest of this
 * hook's logic (param names, setters) does not need to change, since
 * both libraries expose a URLSearchParams-compatible get/set API.
 */

import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { parseObjectsRouteParams } from "@/lib/objectsRoute";

export interface ObjectsQueryParams {
  projectId: string | undefined;
  drawingId: string | undefined;
  runId: string | undefined;
  overlayId: string | undefined;
  /** PR5: focused backend region, from ?region=. */
  regionId: string | undefined;
}

export interface UseObjectsQueryParamsResult extends ObjectsQueryParams {
  setProject: (projectId: string | null) => void;
  setDrawing: (projectId: string, drawingId: string) => void;
  setRun: (runId: string | null) => void;
  setOverlay: (overlayId: string | null) => void;
  setRegion: (regionId: string | null) => void;
  clearRunAndOverlay: () => void;
}

export function useObjectsQueryParams(): UseObjectsQueryParamsResult {
  const [searchParams, setSearchParams] = useSearchParams();

  const params = useMemo(() => parseObjectsRouteParams(searchParams), [searchParams]);

  const setProject = useCallback(
    (projectId: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (projectId) {
          next.set("projectId", projectId);
        } else {
          next.delete("projectId");
        }
        next.delete("drawingId");
        next.delete("run");
        next.delete("overlay");
        next.delete("region");
        return next;
      });
    },
    [setSearchParams],
  );

  const setDrawing = useCallback(
    (projectId: string, drawingId: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("projectId", projectId);
        next.set("drawingId", drawingId);
        // Changing the drawing invalidates any run/overlay/region
        // selection from the PREVIOUS drawing — clear all rather than
        // carry over an id that belongs to a different sheet.
        next.delete("run");
        next.delete("overlay");
        next.delete("region");
        return next;
      });
    },
    [setSearchParams],
  );

  const setRun = useCallback(
    (runId: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (runId) {
          next.set("run", runId);
        } else {
          next.delete("run");
        }
        // A new run selection invalidates any overlay focus from a
        // different run. Region focus is independent of run, so it's
        // deliberately left untouched here.
        next.delete("overlay");
        return next;
      });
    },
    [setSearchParams],
  );

  const setOverlay = useCallback(
    (overlayId: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (overlayId) {
          next.set("overlay", overlayId);
        } else {
          next.delete("overlay");
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const setRegion = useCallback(
    (regionId: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (regionId) {
          next.set("region", regionId);
        } else {
          next.delete("region");
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const clearRunAndOverlay = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("run");
      next.delete("overlay");
      return next;
    });
  }, [setSearchParams]);

  return {
    projectId: params.projectId,
    drawingId: params.drawingId,
    runId: params.runId,
    overlayId: params.overlayId,
    regionId: params.regionId,
    setProject,
    setDrawing,
    setRun,
    setOverlay,
    setRegion,
    clearRunAndOverlay,
  };
}
