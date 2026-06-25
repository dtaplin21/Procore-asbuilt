import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useSearchParams } from "react-router-dom";
import { useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import type { ProjectListResponse } from "@shared/schema";
import {
  objectsSearchParamsAfterProjectChange,
  parseProjectIdFromLocation,
  resolveActiveProjectId,
  setActiveProjectIdInStorage,
} from "@/lib/active_project";
import {
  clearDrawingReturnPathIfProjectMismatch,
  setLastProjectIdForWorkspaceFallback,
} from "@/lib/workspace-return-path";

export type ActiveProjectContextValue = {
  projectId: number | null;
  projectName: string | null;
  /** Dashboard selector only — updates session storage, not the URL. */
  setActiveProjectId: (projectId: number | null) => void;
};

const ActiveProjectContext = createContext<ActiveProjectContextValue | null>(
  null,
);

function pathnameOnly(location: string): string {
  const q = location.indexOf("?");
  return q === -1 ? location : location.slice(0, q);
}

export function ActiveProjectProvider({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projectId, setProjectId] = useState<number | null>(() =>
    resolveActiveProjectId(window.location.pathname, window.location.search),
  );
  const prevProjectIdRef = useRef<number | null>(projectId);

  const { data: projectsData } = useQuery<ProjectListResponse>({
    queryKey: ["/api/projects"],
  });

  const projects = projectsData?.items ?? [];

  useEffect(() => {
    const search = searchParams.toString()
      ? `?${searchParams.toString()}`
      : "";
    const resolved = resolveActiveProjectId(location, search);
    setProjectId(resolved);
    const fromUrl = parseProjectIdFromLocation(location, search);
    if (fromUrl != null) {
      setLastProjectIdForWorkspaceFallback(fromUrl);
    }
  }, [location, searchParams]);

  useEffect(() => {
    const prev = prevProjectIdRef.current;
    if (
      prev != null &&
      projectId != null &&
      prev !== projectId
    ) {
      clearDrawingReturnPathIfProjectMismatch(projectId);
      if (pathnameOnly(location) === "/objects") {
        setSearchParams((current) =>
          objectsSearchParamsAfterProjectChange(current, projectId),
        );
      }
    }
    prevProjectIdRef.current = projectId;
  }, [projectId, location, setSearchParams]);

  const setActiveProjectId = useCallback((nextProjectId: number | null) => {
    setProjectId(nextProjectId);
    setActiveProjectIdInStorage(nextProjectId);
    if (nextProjectId != null) {
      setLastProjectIdForWorkspaceFallback(nextProjectId);
      clearDrawingReturnPathIfProjectMismatch(nextProjectId);
    }
  }, []);

  const projectName = useMemo(() => {
    if (projectId == null) return null;
    const match = projects.find((p) => p.id === projectId);
    return match?.name ?? null;
  }, [projectId, projects]);

  const value = useMemo(
    () => ({
      projectId,
      projectName,
      setActiveProjectId,
    }),
    [projectId, projectName, setActiveProjectId],
  );

  return (
    <ActiveProjectContext.Provider value={value}>
      {children}
    </ActiveProjectContext.Provider>
  );
}

export function useActiveProject(): ActiveProjectContextValue {
  const ctx = useContext(ActiveProjectContext);
  if (!ctx) {
    throw new Error("useActiveProject must be used within ActiveProjectProvider");
  }
  return ctx;
}
