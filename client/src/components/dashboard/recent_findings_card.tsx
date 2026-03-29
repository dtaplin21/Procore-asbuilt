import { Link } from "wouter";
import { buildWorkspaceUrl } from "@/lib/workspace-links";
import type { FindingItem } from "@/types/dashboard";

type Props = {
  findings: FindingItem[];
};

export default function RecentFindingsCard({ findings }: Props) {
  return (
    <div className="rounded-xl border bg-white">
      <div className="border-b px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-900">Recent Findings</h3>
      </div>

      <div className="divide-y">
        {findings.length === 0 ? (
          <div className="px-4 py-6 text-sm text-slate-500">No recent findings for this project.</div>
        ) : (
          findings.map((finding) => {
            const content = (
              <div className="px-4 py-3 hover:bg-slate-50">
                <div className="text-sm font-medium text-slate-900">{finding.title}</div>
                {finding.severity ? (
                  <div className="mt-1 text-xs text-slate-500">Severity: {finding.severity}</div>
                ) : null}
              </div>
            );

            if (finding.workspaceLink) {
              return (
                <Link
                  key={finding.id}
                  href={buildWorkspaceUrl({
                    projectId: finding.workspaceLink.projectId,
                    masterDrawingId: finding.workspaceLink.masterDrawingId,
                    alignmentId: finding.workspaceLink.alignmentId,
                    diffId: finding.workspaceLink.diffId,
                  })}
                >
                  {content}
                </Link>
              );
            }

            return <div key={finding.id}>{content}</div>;
          })
        )}
      </div>
    </div>
  );
}
