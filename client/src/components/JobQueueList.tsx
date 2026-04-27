import React from "react";
import type { JobResponse } from "@shared/schema";

type JobQueueListProps = {
  jobs: JobResponse[];
  isLoading?: boolean;
  error?: string | null;
};

function getStatusLabel(status: string) {
  switch (status) {
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "processing":
      return "Processing";
    case "failed":
      return "Failed";
    case "completed":
      return "Completed";
    default:
      return status;
  }
}

export default function JobQueueList({
  jobs,
  isLoading = false,
  error = null,
}: JobQueueListProps) {
  if (isLoading) {
    return <div>Loading active jobs...</div>;
  }

  if (error) {
    return <div>{error}</div>;
  }

  if (!jobs.length) {
    return <div>No active jobs for this project.</div>;
  }

  return (
    <div className="space-y-3">
      {jobs.map((job) => (
        <div
          key={job.id}
          className="rounded-lg border border-border bg-card p-4 shadow-sm"
        >
          <div className="flex items-center justify-between">
            <div className="font-medium">{job.job_type}</div>
            <div className="text-sm">{getStatusLabel(job.status)}</div>
          </div>

          <div className="mt-2 text-sm text-muted-foreground">
            Job ID: {job.id}
          </div>

          {job.started_at && (
            <div className="text-sm text-muted-foreground">
              Started: {new Date(job.started_at).toLocaleString()}
            </div>
          )}

          {job.completed_at && (
            <div className="text-sm text-muted-foreground">
              Completed: {new Date(job.completed_at).toLocaleString()}
            </div>
          )}

          {job.error_message && (
            <div className="mt-2 text-sm text-red-600">
              Error: {job.error_message}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
