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

/** POST /compare may send `comparison_progress` or `comparisonProgress`; nested counts snake_case or camelCase. */
function readComparisonProgressFromWorkspace(
  workspace: DrawingComparisonWorkspaceResponse | undefined | null
): { compared_count: number; total_relevant_count: number; label: string } | null {
  if (!workspace) return null;
  const w = workspace as unknown as Record<string, unknown>;
  const raw = w.comparison_progress ?? w.comparisonProgress;
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const compared =
    (typeof o.compared_count === "number" ? o.compared_count : undefined) ??
    (typeof o.comparedCount === "number" ? o.comparedCount : undefined);
  const total =
    (typeof o.total_relevant_count === "number" ? o.total_relevant_count : undefined) ??
    (typeof o.totalRelevantCount === "number" ? o.totalRelevantCount : undefined);
  const label = typeof o.label === "string" ? o.label : "";
  if (compared === undefined || total === undefined) return null;
  return { compared_count: compared, total_relevant_count: total, label };
}

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
  const transformValidation = validateTransform(displayTransform);

  const comparisonProgress = readComparisonProgressFromWorkspace(workspace);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {selectedAlignment ? (
        <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="text-sm text-muted-foreground">Project comparison progress</div>
          <div className="mt-2 text-xl font-semibold tabular-nums">
            {comparisonProgress
              ? `${comparisonProgress.compared_count} / ${comparisonProgress.total_relevant_count}`
              : "—"}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {comparisonProgress?.label ?? "Comparison progress unavailable."}
          </div>
        </div>
      ) : null}

      {selectedAlignment ? (
        <div className="rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Alignment
          </div>
          <div className="mt-2 grid gap-2 text-sm text-foreground sm:grid-cols-2">
            <div>
              <span className="text-muted-foreground">Sub drawing: </span>
              {selectedAlignment.subDrawing.name} (#{selectedAlignment.subDrawing.id})
            </div>
            <div>
              <span className="text-muted-foreground">Status: </span>
              {metadata?.status ?? "—"}
            </div>
            {metadata?.method ? (
              <div>
                <span className="text-muted-foreground">Method: </span>
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
                  <span className="text-muted-foreground">Transform: </span>
                  {transformType}
                </div>
                <div>
                  <span className="text-muted-foreground">Confidence: </span>
                  {displayTransform?.confidence != null
                    ? displayTransform.confidence.toFixed(3)
                    : "—"}
                </div>
                <div className="sm:col-span-2 font-mono text-xs text-muted-foreground">
                  matrix[{transformMatrix.length}]:{" "}
                  {transformMatrix
                    .slice(0, 12)
                    .map((n) => (Number.isFinite(n) ? n.toFixed(4) : String(n)))
                    .join(", ")}
                  {transformMatrix.length > 12 ? "…" : ""}
                </div>
              </>
            ) : (
              <div className="sm:col-span-2 rounded-md border border-primary/30 bg-primary-soft px-3 py-2 text-sm text-foreground">
                No transform on this alignment — showing master only.
              </div>
            )}
          </div>
        </div>
      ) : null}

      {selectedAlignment && workspace && alignmentOverlayUsable ? (
        <div className="mb-4 flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={showOverlay}
              onChange={(e) => setShowOverlay(e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary"
            />
            Show sub overlay
          </label>

          <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
            <span className="text-muted-foreground">Opacity</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={overlayOpacity}
              onChange={(e) => setOverlayOpacity(Number(e.target.value))}
              className="h-2 w-48 min-w-[8rem] accent-primary"
            />
          </label>

          <span className="text-sm text-muted-foreground tabular-nums">
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
