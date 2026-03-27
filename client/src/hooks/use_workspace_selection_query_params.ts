import { useCallback, useMemo } from "react";
import { useLocation } from "wouter";

type SelectionQueryState = {
  alignmentId: number | null;
  diffId: number | null;
};

function parseNullableNumber(value: string | null): number | null {
  if (!value) return null;

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function splitPathAndSearch(location: string): { pathname: string; search: string } {
  const q = location.indexOf("?");
  if (q === -1) {
    return { pathname: location, search: "" };
  }
  return { pathname: location.slice(0, q), search: location.slice(q + 1) };
}

export function useWorkspaceSelectionQueryParams() {
  const [location, setLocation] = useLocation();

  const { pathname, search } = useMemo(() => splitPathAndSearch(location), [location]);

  const searchParams = useMemo(() => new URLSearchParams(search), [search]);

  const selection = useMemo<SelectionQueryState>(() => {
    return {
      alignmentId: parseNullableNumber(searchParams.get("alignmentId")),
      diffId: parseNullableNumber(searchParams.get("diffId")),
    };
  }, [searchParams]);

  const setSelectionQueryParams = useCallback(
    (next: { alignmentId?: number | null; diffId?: number | null }) => {
      const updated = new URLSearchParams(searchParams);

      if (next.alignmentId == null) {
        updated.delete("alignmentId");
      } else {
        updated.set("alignmentId", String(next.alignmentId));
      }

      if (next.diffId == null) {
        updated.delete("diffId");
      } else {
        updated.set("diffId", String(next.diffId));
      }

      const qs = updated.toString();
      setLocation(qs ? `${pathname}?${qs}` : pathname, { replace: true });
    },
    [pathname, searchParams, setLocation]
  );

  return {
    alignmentIdFromUrl: selection.alignmentId,
    diffIdFromUrl: selection.diffId,
    setSelectionQueryParams,
  };
}
