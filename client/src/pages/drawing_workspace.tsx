import { useParams } from "wouter";

export default function DrawingWorkspacePage() {
  const params = useParams<{ projectId?: string; drawingId?: string }>();
  const projectId = params?.projectId;
  const drawingId = params?.drawingId;

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Drawing Workspace</h1>

      <div className="rounded-lg border p-4 bg-white shadow-sm">
        <div className="text-sm text-gray-600">Project ID</div>
        <div className="text-lg font-medium">{projectId ?? "N/A"}</div>
      </div>

      <div className="rounded-lg border p-4 bg-white shadow-sm">
        <div className="text-sm text-gray-600">Drawing ID</div>
        <div className="text-lg font-medium">{drawingId ?? "N/A"}</div>
      </div>

      <div className="rounded-lg border p-4 bg-yellow-50 border-yellow-200">
        <div className="text-lg font-medium">Coming soon</div>
        <div className="text-sm text-gray-700 mt-1">
          This drawing workspace route is active, but the full viewer and tools
          have not been implemented yet.
        </div>
      </div>
    </div>
  );
}
