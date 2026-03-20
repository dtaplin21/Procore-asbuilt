import { useMemo } from "react";
import { useParams } from "wouter";

import { useDrawingWorkspace } from "@/hooks/use_drawing_workspace";
import type { WorkspaceRouteParams } from "@/types/drawing_workspace";

export default function DrawingWorkspacePage() {
  const { projectId, drawingId } = useParams<WorkspaceRouteParams>();

  const parsedProjectId = Number(projectId);
  const parsedDrawingId = Number(drawingId);

  const idsAreValid = useMemo(() => {
    return Number.isFinite(parsedProjectId) && Number.isFinite(parsedDrawingId);
  }, [parsedProjectId, parsedDrawingId]);

  if (!idsAreValid) {
    return (
      <div className="p-4 text-red-600">
        Invalid project id or drawing id.
      </div>
    );
  }

  const {
    masterDrawing,
    alignments,
    selectedAlignmentId,
    selectedDiffId,
    selectedDiffs,
    workspaceLoading,
    diffsLoading,
    workspaceError,
    diffsError,
    selectAlignment,
    selectDiff,
    reloadWorkspace,
    reloadSelectedDiffs,
  } = useDrawingWorkspace({
    projectId: parsedProjectId,
    drawingId: parsedDrawingId,
  });

  return (
    <div className="min-h-screen bg-slate-50 p-4">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Drawing Workspace</h1>
        <p className="text-sm text-slate-500">
          Project {parsedProjectId} • Drawing {parsedDrawingId}
        </p>
      </div>

      {workspaceError ? (
        <div className="mb-4 rounded border border-red-200 bg-red-50 p-4">
          <div className="text-sm font-medium text-red-700">
            Failed to load workspace
          </div>
          <div className="mt-1 text-sm text-red-600">{workspaceError}</div>
          <button
            type="button"
            onClick={() => void reloadWorkspace()}
            className="mt-3 rounded border border-red-300 bg-white px-3 py-2 text-sm text-red-700"
            data-testid="retry-workspace"
          >
            Retry
          </button>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="rounded-xl border bg-white p-4">
          {workspaceLoading ? (
            <div className="text-sm text-slate-500">Loading master drawing...</div>
          ) : masterDrawing ? (
            <>
              <div className="mb-3">
                <div className="text-lg font-semibold">{masterDrawing.name}</div>
                <div className="text-sm text-slate-500">
                  Drawing #{masterDrawing.id}
                </div>
              </div>

              {masterDrawing.fileUrl ? (
                masterDrawing.contentType === "application/pdf" ? (
                  <iframe
                    title={masterDrawing.name}
                    src={masterDrawing.fileUrl}
                    className="h-[75vh] w-full rounded border"
                  />
                ) : (
                  <img
                    src={masterDrawing.fileUrl}
                    alt={masterDrawing.name}
                    className="h-[75vh] w-full rounded border object-contain"
                  />
                )
              ) : (
                <div className="rounded border border-dashed p-6 text-sm text-slate-500">
                  Drawing file URL is not available.
                </div>
              )}
            </>
          ) : null}
        </div>

        <div className="flex flex-col gap-4">
          <section className="overflow-hidden rounded-xl border bg-white">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-semibold">Alignments</h2>
            </div>

            <div className="max-h-[320px] overflow-y-auto">
              {workspaceLoading ? (
                <div className="px-4 py-4 text-sm text-slate-500">
                  Loading alignments...
                </div>
              ) : alignments.length === 0 ? (
                <div className="px-4 py-4 text-sm text-slate-500">
                  No alignments found.
                </div>
              ) : (
                alignments.map((alignment) => {
                  const selected = alignment.id === selectedAlignmentId;

                  return (
                    <button
                      key={alignment.id}
                      type="button"
                      onClick={() => void selectAlignment(alignment.id)}
                      data-testid={`alignment-${alignment.id}`}
                      className={`w-full border-b px-4 py-3 text-left ${
                        selected ? "bg-slate-100" : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium">
                            {alignment.subDrawing.name}
                          </div>
                          <div className="text-xs text-slate-500">
                            Sub drawing #{alignment.subDrawing.id}
                          </div>
                        </div>

                        <div className="rounded border px-2 py-1 text-xs text-slate-600">
                          {alignment.alignmentStatus || "unknown"}
                        </div>
                      </div>

                      {alignment.createdAt ? (
                        <div className="mt-2 text-xs text-slate-400">
                          {new Date(alignment.createdAt).toLocaleString()}
                        </div>
                      ) : null}
                    </button>
                  );
                })
              )}
            </div>
          </section>

          <section className="overflow-hidden rounded-xl border bg-white">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-semibold">Diff Timeline</h2>
            </div>

            <div className="max-h-[420px] overflow-y-auto">
              {diffsError ? (
                <div className="p-4">
                  <div className="rounded border border-red-200 bg-red-50 p-4">
                    <div className="text-sm font-medium text-red-700">
                      Failed to load diffs
                    </div>
                    <div className="mt-1 text-sm text-red-600">{diffsError}</div>
                    <button
                      type="button"
                      onClick={() => void reloadSelectedDiffs()}
                      className="mt-3 rounded border border-red-300 bg-white px-3 py-2 text-sm text-red-700"
                      data-testid="retry-diffs"
                    >
                      Retry diffs
                    </button>
                  </div>
                </div>
              ) : diffsLoading ? (
                <div className="px-4 py-4 text-sm text-slate-500">
                  Loading diffs...
                </div>
              ) : selectedDiffs.length === 0 ? (
                <div className="px-4 py-4 text-sm text-slate-500">
                  No diffs for the selected alignment.
                </div>
              ) : (
                selectedDiffs.map((diff) => {
                  const selected = diff.id === selectedDiffId;

                  return (
                    <button
                      key={diff.id}
                      type="button"
                      onClick={() => selectDiff(diff.id)}
                      data-testid={`diff-${diff.id}`}
                      className={`w-full border-b px-4 py-3 text-left ${
                        selected ? "bg-slate-100" : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium">
                            {diff.summary || `Diff #${diff.id}`}
                          </div>
                          {diff.createdAt ? (
                            <div className="mt-1 text-xs text-slate-500">
                              {new Date(diff.createdAt).toLocaleString()}
                            </div>
                          ) : null}
                        </div>

                        <div className="rounded border px-2 py-1 text-xs text-slate-600">
                          {diff.severity || "unspecified"}
                        </div>
                      </div>

                      <div className="mt-2 text-xs text-slate-400">
                        Regions: {diff.diffRegions?.length ?? 0}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
