import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ProcoreWritebackResponse } from "@shared/schema";

import { resolveFetchUrl } from "@/lib/api/http";

type WritebackParams = {
  projectId: string | null;
  procoreUserId: string | null;
};

type WritebackBody = {
  inspection_run_id: number;
  mode: "dry_run" | "commit";
};

async function fetchWriteback(
  projectId: string,
  procoreUserId: string,
  body: WritebackBody
): Promise<ProcoreWritebackResponse> {
  const url = resolveFetchUrl(
    `/api/projects/${projectId}/procore/writeback?user_id=${encodeURIComponent(procoreUserId)}`
  );
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    credentials: "include",
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((e: { msg?: string }) => e?.msg ?? JSON.stringify(e)).join("; ")
          : "Procore writeback failed";
    throw new Error(message);
  }

  return res.json();
}

function invalidateAfterWriteback(queryClient: ReturnType<typeof useQueryClient>, projectId: string) {
  queryClient.invalidateQueries({
    predicate: (query) => {
      const key = query.queryKey[0];
      return (
        typeof key === "string" &&
        (key.includes(`/api/projects/${projectId}/inspections/runs`) ||
          (key.includes(`/api/projects/${projectId}/drawings/`) && key.includes("/overlays")) ||
          key.includes(`/api/projects/${projectId}/dashboard/summary`) ||
          (key === "project-dashboard-summary" &&
            String(query.queryKey[1]) === String(projectId)))
      );
    },
  });
}

/**
 * Procore writeback mutations for inspection runs.
 * POST /api/projects/{projectId}/procore/writeback?user_id={procoreUserId}
 *
 * - previewMutation: mode=dry_run, returns payload without calling Procore
 * - commitMutation: mode=commit, sends to Procore
 *
 * Both require projectId and procoreUserId. Invalidates inspection runs,
 * drawing overlays, and dashboard summary on success.
 */
export function useProcoreWriteback({ projectId, procoreUserId }: WritebackParams) {
  const queryClient = useQueryClient();

  const previewMutation = useMutation<ProcoreWritebackResponse, Error, number>({
    mutationFn: async (inspectionRunId) => {
      if (!projectId || !procoreUserId) {
        throw new Error("Project and Procore user required");
      }
      return fetchWriteback(projectId, procoreUserId, {
        inspection_run_id: inspectionRunId,
        mode: "dry_run",
      });
    },
  });

  const commitMutation = useMutation<ProcoreWritebackResponse, Error, number>({
    mutationFn: async (inspectionRunId) => {
      if (!projectId || !procoreUserId) {
        throw new Error("Project and Procore user required");
      }
      return fetchWriteback(projectId, procoreUserId, {
        inspection_run_id: inspectionRunId,
        mode: "commit",
      });
    },
    onSuccess: () => {
      if (projectId) {
        invalidateAfterWriteback(queryClient, projectId);
      }
    },
  });

  return { previewMutation, commitMutation };
}
