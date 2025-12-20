import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { SubmittalStatus, RFIStatus, InspectionStatus } from "@shared/schema";

interface StatusBadgeProps {
  status: SubmittalStatus | RFIStatus | InspectionStatus | string;
  size?: "sm" | "default";
}

const statusConfig: Record<string, { label: string; className: string }> = {
  // Submittal statuses
  pending: { label: "Pending", className: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30" },
  approved: { label: "Approved", className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30" },
  rejected: { label: "Rejected", className: "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30" },
  in_review: { label: "In Review", className: "bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30" },
  revise_resubmit: { label: "Revise & Resubmit", className: "bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30" },
  
  // RFI statuses
  open: { label: "Open", className: "bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30" },
  answered: { label: "Answered", className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30" },
  closed: { label: "Closed", className: "bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30" },
  overdue: { label: "Overdue", className: "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30" },
  
  // Inspection statuses
  scheduled: { label: "Scheduled", className: "bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30" },
  in_progress: { label: "In Progress", className: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30" },
  passed: { label: "Passed", className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30" },
  failed: { label: "Failed", className: "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30" },
  
  // Priority
  low: { label: "Low", className: "bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30" },
  medium: { label: "Medium", className: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30" },
  high: { label: "High", className: "bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30" },
  critical: { label: "Critical", className: "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30" },
};

export function StatusBadge({ status, size = "default" }: StatusBadgeProps) {
  const config = statusConfig[status] || { label: status, className: "bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30" };
  
  return (
    <Badge 
      variant="outline" 
      className={cn(
        "font-medium border",
        config.className,
        size === "sm" && "text-xs px-1.5 py-0"
      )}
      data-testid={`badge-status-${status}`}
    >
      {config.label}
    </Badge>
  );
}
