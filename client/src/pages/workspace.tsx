import { useEffect } from "react";
import { useParams, useLocation } from "wouter";

/**
 * Legacy route: /workspace/:projectId
 * Redirects to canonical drawing picker: /projects/:projectId/drawings
 */
export default function WorkspaceStub() {
  const params = useParams<{ projectId: string }>();
  const [, setLocation] = useLocation();
  const projectId = params?.projectId ?? "";
  const search = typeof window !== "undefined" ? window.location.search : "";

  useEffect(() => {
    if (projectId) {
      setLocation(`/projects/${projectId}/drawings${search}`);
    } else {
      setLocation("/");
    }
  }, [projectId, search, setLocation]);

  return null;
}
