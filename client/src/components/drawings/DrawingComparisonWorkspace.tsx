import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import DrawingViewer from "@/components/drawings/DrawingViewer";
import { compareSubDrawing } from "@/lib/api/drawing_workspace";
import { drawingComparisonWorkspaceQueryKey } from "@/lib/drawing-comparison-query";
import { validateTransform } from "@/lib/drawings";
import { extractAlignmentTransform } from "@/lib/drawing-alignment/extract_transform";
import { isAlignmentOverlayUsable } from "@/lib/drawing-alignment/is_alignment_overlay_usable";
import type {
  DrawingAlignmentListItem,
  DrawingComparisonWorkspaceResponse,
  DrawingDiff,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

/** Raw alignment debug UI — never show in production (Vite strips DEV in prod builds). */
const isDev = import.meta.env.DEV;

/** Safe snapshot for dev JSON — avoids crashes if alignment or transform is missing. */
function buildAlignmentDebugPayload(
  workspace: DrawingComparisonWorkspaceResponse | undefined
): {
  alignment_id: number | null;
  status: string | null;
  method: string | null;
  error_message: string | null;
  transform: DrawingComparisonWorkspaceResponse["alignment"]["transform"];
} | null {
  if (!workspace) return null;

  const a = workspace.alignment;
  return {
    alignment_id: a?.id ?? null,
    status: a?.status ?? null,
    method: a?.method ?? null,
    error_message: a?.errorMessage ?? null,
    transform: a?.transform ?? null,
  };
}

type Props = {
  projectId: number;
  masterDrawing: DrawingWorkspaceDrawing | null;
  selectedAlignment: DrawingAlignmentListItem | null;
  selectedDiff: DrawingDiff | null;
};

export default function DrawingComparisonWorkspace({
  projectId,
  masterDrawing,
  selectedAlignment,
  selectedDiff,
}: Props) {
  const [showOverlay, setShowOverlay] = useState(true);
  const [overlayOpacity, setOverlayOpacity] = useState(0.45);

  const subId = selectedAlignment?.subDrawing.id;
  const masterId = masterDrawing?.id;

  const comparisonEnabled = Boolean(
    projectId && masterId != null && subId != null && selectedAlignment
  );

  const { data: workspace, isPending: isComparisonPending } = useQuery({
    queryKey: drawingComparisonWorkspaceQueryKey(
      projectId,
      masterId ?? 0,
      subId ?? 0
    ),
    queryFn: () => compareSubDrawing(projectId, masterId!, subId!),
    enabled: comparisonEnabled,
  });

  const transformFromList = useMemo(
    () => extractAlignmentTransform(selectedAlignment),
    [selectedAlignment]
  );

  const transform = workspace?.alignment?.transform ?? null;
  const displayTransform = transform ?? transformFromList ?? null;
  const transformType = displayTransform?.type ?? "unknown";
  const transformMatrix = displayTransform?.matrix ?? [];

  const alignmentOverlayUsable = useMemo(
    () => isAlignmentOverlayUsable(workspace),
    [workspace]
  );

  const metadata = useMemo(() => {
    if (!selectedAlignment) return null;
    const method =
      "method" in selectedAlignment ? selectedAlignment.method : undefined;
    const status =
      selectedAlignment.alignmentStatus ??
      ("status" in selectedAlignment ? selectedAlignment.status : undefined);
    return { method, status };
  }, [selectedAlignment]);

  const debugPayload = buildAlignmentDebugPayload(workspace);
  const transformValidation = validateTransform(workspace?.alignment?.transform);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {selectedAlignment ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Alignment
          </div>
          <div className="mt-2 grid gap-2 text-sm text-slate-800 sm:grid-cols-2">
            <div>
              <span className="text-slate-500">Sub drawing: </span>
              {selectedAlignment.subDrawing.name} (#{selectedAlignment.subDrawing.id})
            </div>
            <div>
              <span className="text-slate-500">Status: </span>
              {metadata?.status ?? "—"}
            </div>
            {metadata?.method ? (
              <div>
                <span className="text-slate-500">Method: </span>
                {metadata.method}
              </div>
            ) : null}
            {"errorMessage" in selectedAlignment && selectedAlignment.errorMessage ? (
              <div className="sm:col-span-2 text-red-700">
                Error: {selectedAlignment.errorMessage}
              </div>
            ) : null}

            {displayTransform != null ? (
              <>
                <div>
                  <span className="text-slate-500">Transform: </span>
                  {transformType}
                </div>
                <div>
                  <span className="text-slate-500">Confidence: </span>
                  {displayTransform?.confidence != null
                    ? displayTransform.confidence.toFixed(3)
                    : "—"}
                </div>
                <div className="sm:col-span-2 font-mono text-xs text-slate-600">
                  matrix[{transformMatrix.length}]:{" "}
                  {transformMatrix
                    .slice(0, 12)
                    .map((n) => (Number.isFinite(n) ? n.toFixed(4) : String(n)))
                    .join(", ")}
                  {transformMatrix.length > 12 ? "…" : ""}
                </div>
              </>
            ) : (
              <div className="sm:col-span-2 text-amber-700">
                No transform on this alignment — showing master only.
              </div>
            )}
          </div>
        </div>
      ) : null}

      {selectedAlignment && workspace && alignmentOverlayUsable ? (
        <div className="mb-4 flex flex-wrap items-center gap-4 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-800">
            <input
              type="checkbox"
              checked={showOverlay}
              onChange={(e) => setShowOverlay(e.target.checked)}
              className="rounded border-slate-300"
            />
            Show sub overlay
          </label>

          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-800">
            <span className="text-slate-600">Opacity</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={overlayOpacity}
              onChange={(e) => setOverlayOpacity(Number(e.target.value))}
              className="h-2 w-48 min-w-[8rem] accent-slate-700"
            />
          </label>

          <span className="text-sm text-slate-500 tabular-nums">
            {Math.round(overlayOpacity * 100)}%
          </span>
        </div>
      ) : null}

      <div className="min-h-0 flex-1">
        <DrawingViewer
          drawing={masterDrawing}
          selectedDiff={selectedDiff}
          comparisonWorkspace={workspace ?? undefined}
          isLoadingComparisonWorkspace={comparisonEnabled && isComparisonPending}
          showOverlay={showOverlay}
          overlayOpacity={overlayOpacity}
        />
      </div>

      {isDev && debugPayload ? (
        <div className="mt-4 space-y-2 rounded-lg border border-dashed p-3">
          <div className="text-sm font-medium">Alignment debug</div>

          <div className="text-xs text-muted-foreground">
            Transform valid: {transformValidation.valid ? "yes" : "no"}
            {!transformValidation.valid && transformValidation.reason
              ? ` — ${transformValidation.reason}`
              : ""}
          </div>

          <pre
            className="overflow-x-auto rounded bg-muted p-2 text-xs"
            data-testid="dev-alignment-transform-json"
          >
            {JSON.stringify(debugPayload, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
