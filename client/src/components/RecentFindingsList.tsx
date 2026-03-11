import React from "react";
import { Link } from "wouter";
import type { FindingResponse } from "@shared/schema";

type RecentFindingsListProps = {
  findings: FindingResponse[];
  isLoading?: boolean;
  error?: string | null;
  projectId?: number | null;
};

export default function RecentFindingsList({
  findings,
  isLoading = false,
  error = null,
  projectId = null,
}: RecentFindingsListProps) {
  if (isLoading) {
    return <div>Loading recent findings...</div>;
  }

  if (error) {
    return <div>{error}</div>;
  }

  if (!findings.length) {
    return <div>No recent findings for this project.</div>;
  }

  return (
    <div className="space-y-3">
      {findings.map((finding) => (
        <div
          key={finding.id}
          className="rounded-lg border p-4 shadow-sm bg-white"
        >
          <div className="flex items-center justify-between">
            <div className="font-medium">{finding.title}</div>
            <div className="text-sm">{finding.resolved ? "Resolved" : "Open"}</div>
          </div>

          <div className="mt-1 text-sm text-gray-600">
            Type: {finding.type}
          </div>

          {finding.description && (
            <div className="mt-2 text-sm text-gray-700">
              {finding.description}
            </div>
          )}

          {finding.affectedItems && finding.affectedItems.length > 0 && (
            <div className="mt-2 text-sm text-gray-600">
              Affected: {finding.affectedItems.join(", ")}
            </div>
          )}

          <div className="mt-3">
            {projectId != null ? (
              <Link
                href={`/projects/${projectId}/workspace?findingId=${encodeURIComponent(finding.id)}`}
                className="text-sm text-blue-600 hover:underline"
              >
                Open drawing workspace
              </Link>
            ) : (
              <span className="text-sm text-gray-400">
                Workspace unavailable
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
