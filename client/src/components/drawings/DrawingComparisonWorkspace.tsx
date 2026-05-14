import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import DrawingViewer from "@/components/drawings/DrawingViewer";
import { compareSubDrawing } from "@/lib/api/drawing_workspace";
import { fetchProjectJobs } from "@/lib/api/projects";
import { findActiveDrawingCompareJob } from "@/lib/drawing-workspace/compare_jobs";
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
  /** Route master id — used to match background `drawing_compare` jobs. */
  masterDrawingId: number;
  masterDrawing: DrawingWorkspaceDrawing | null;
  selectedAlignment: DrawingAlignmentListItem | null;
  selectedDiff: DrawingDiff | null;
  /** True while synchronous POST /compare runs from the workspace chrome. */
  compareBusy?: boolean;
};

export default function DrawingComparisonWorkspace({
  projectId,
  masterDrawingId,
  masterDrawing,
  selectedAlignment,
  selectedDiff,
  compareBusy = false,
}: Props) {
  const [showAlignedSubOverlay, setShowAlignedSubOverlay] = useState(true);
  const [overlayOpacity, setOverlayOpacity] = useState(0.45);
  const [showChangesOnly, setShowChangesOnly] = useState(false);
  const [showInspectionStatuses, setShowInspectionStatuses] = useState(true);

  const subId = selectedAlignment?.subDrawing.id;

  const comparisonEnabled = Boolean(
    projectId && subId != null && selectedAlignment
  );

  const { data: workspace, isPending: isComparisonPending } = useQuery({
    queryKey: drawingComparisonWorkspaceQueryKey(
      projectId,
      masterDrawingId,
      subId ?? 0
    ),
    queryFn: () => compareSubDrawing(projectId, masterDrawingId, subId!),
    enabled: comparisonEnabled,
  });

  const { data: activeJobsPayload } = useQuery({
    queryKey: ["projectJobs", "active", projectId],
    queryFn: () => fetchProjectJobs(projectId, "active"),
    enabled: comparisonEnabled,
    refetchInterval: (q) => {
      const match = findActiveDrawingCompareJob(
        q.state.data?.jobs,
        masterDrawingId,
        subId!
      );
      return match ? 2500 : false;
    },
  });

  const activeCompareJob = useMemo(
    () =>
      subId != null
        ? findActiveDrawingCompareJob(activeJobsPayload?.jobs, masterDrawingId, subId)
        : null,
    [activeJobsPayload?.jobs, masterDrawingId, subId]
  );

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

  const compareProgressBanner = useMemo(() => {
    if (compareBusy) {
      return {
        title: "Comparing drawings…",
        detail: "Aligning, detecting changes, and loading the workspace.",
      };
    }
    if (activeCompareJob) {
      const st = (activeCompareJob.status ?? "").toLowerCase();
      if (st === "pending") {
        return {
          title: "Compare job queued…",
          detail: "Waiting for the worker to pick up this comparison.",
        };
      }
      return {
        title: "Comparison running…",
        detail: "Aligning and detecting changes in the background.",
      };
    }
    const ast = (metadata?.status ?? "").toLowerCase();
    if (selectedAlignment && ast === "processing") {
      return {
        title: "Alignment in progress…",
        detail: "This sheet is still being aligned.",
      };
    }
    return null;
  }, [compareBusy, activeCompareJob, metadata?.status, selectedAlignment]);

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

      {compareProgressBanner ? (
        <div
          className="flex items-start gap-3 rounded-lg border border-primary/25 bg-primary-soft/90 px-4 py-3 text-sm text-foreground shadow-sm"
          data-testid="compare-progress-banner"
        >
          <div
            className="mt-0.5 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-muted border-t-primary"
            aria-hidden
          />
          <div>
            <div className="font-medium">{compareProgressBanner.title}</div>
            <div className="mt-0.5 text-muted-foreground">{compareProgressBanner.detail}</div>
          </div>
        </div>
      ) : null}

      {selectedAlignment ? (
        <div className="mb-4 flex flex-col gap-3 rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            {workspace && alignmentOverlayUsable ? (
              <>
                <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
                  <input
                    type="checkbox"
                    checked={showAlignedSubOverlay}
                    onChange={(e) => setShowAlignedSubOverlay(e.target.checked)}
                    className="rounded border-border text-primary focus:ring-primary"
                  />
                  Show aligned sub overlay
                </label>

                <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
                  <span className="text-muted-foreground">Sub opacity</span>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={overlayOpacity}
                    onChange={(e) => setOverlayOpacity(Number(e.target.value))}
                    className="h-2 w-48 min-w-[8rem] accent-primary"
                  />
                  <span className="text-sm text-muted-foreground tabular-nums">
                    {Math.round(overlayOpacity * 100)}%
                  </span>
                </label>
              </>
            ) : (
              <span className="text-sm text-muted-foreground">
                Sub overlay unavailable until alignment and compare workspace load.
              </span>
            )}

            <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={showChangesOnly}
                onChange={(e) => setShowChangesOnly(e.target.checked)}
                className="rounded border-border text-primary focus:ring-primary"
              />
              Show changes only
            </label>

            <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={showInspectionStatuses}
                onChange={(e) => setShowInspectionStatuses(e.target.checked)}
                className="rounded border-border text-primary focus:ring-primary"
              />
              Show inspection statuses
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-4 border-t border-border pt-3 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Diff overlay legend</span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-amber-500" aria-hidden />
              Changed
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-green-600" aria-hidden />
              Passed
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-red-600" aria-hidden />
              Failed
            </span>
          </div>
        </div>
      ) : null}

      <div className="min-h-0 flex-1">
        <DrawingViewer
          drawing={masterDrawing}
          selectedDiff={selectedDiff}
          comparisonWorkspace={workspace ?? undefined}
          isLoadingComparisonWorkspace={
            (comparisonEnabled && isComparisonPending) || compareBusy
          }
          showOverlay={showAlignedSubOverlay}
          overlayOpacity={overlayOpacity}
          overlayShowChangesOnly={showChangesOnly}
          overlayShowInspectionStatuses={showInspectionStatuses}
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
