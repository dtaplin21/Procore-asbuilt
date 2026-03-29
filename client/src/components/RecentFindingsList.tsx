import React from "react";
import { Link } from "wouter";
import type { FindingResponse } from "@shared/schema";
import {
  buildDrawingPickerUrl,
  buildWorkspaceUrlWithFinding,
} from "@/lib/workspace-links";

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
      {findings.map((finding) => {
        const pid = finding.projectId ?? projectId;
        const workspaceHref =
          pid != null
            ? finding.workspaceLink
              ? buildWorkspaceUrlWithFinding(
                  {
                    projectId: finding.workspaceLink.projectId,
                    masterDrawingId: finding.workspaceLink.masterDrawingId,
                    alignmentId: finding.workspaceLink.alignmentId,
                    diffId: finding.workspaceLink.diffId,
                  },
                  finding.id,
                )
              : buildDrawingPickerUrl(pid, finding.id)
            : null;

        return (
        <div
          key={finding.id}
          className="rounded-lg border p-4 shadow-sm bg-white"
        >
          <div className="flex items-center justify-between">
            <div className="font-medium">{finding.title}</div>
            {finding.severity != null && finding.severity !== "" && (
              <div className="text-sm text-gray-600">{finding.severity}</div>
            )}
          </div>

          {finding.type != null && finding.type !== "" && (
            <div className="mt-1 text-sm text-gray-600">Type: {finding.type}</div>
          )}

          {finding.description && (
            <div className="mt-2 text-sm text-gray-700">
              {finding.description}
            </div>
          )}

          <div className="mt-3">
            {workspaceHref != null ? (
              <Link
                href={workspaceHref}
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
        );
      })}
    </div>
  );
}
