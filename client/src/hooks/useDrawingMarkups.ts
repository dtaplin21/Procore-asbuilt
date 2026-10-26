import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/markup_api";
import type { DrawingMarkup, MarkupSummaryRow, NewMarkup } from "../types/drawing_markup";

export function useDrawingMarkups(drawingId: number | null, page: number, opts: api.ApiOptions = {}) {
  const [markups, setMarkups] = useState<DrawingMarkup[]>([]);
  const [summary, setSummary] = useState<MarkupSummaryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const reload = useCallback(async () => {
    if (drawingId == null) return;
    setLoading(true);
    try {
      const [rows, sums] = await Promise.all([
        api.listMarkups(optsRef.current, drawingId, page),
        api.markupSummary(optsRef.current, drawingId, page),
      ]);
      setMarkups(rows);
      setSummary(sums);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [drawingId, page]);

  useEffect(() => {
    setMarkups([]);
    setSummary([]);
    void reload();
  }, [reload]);

  /** Each write reloads from the server, so the screen shows what was saved and not what was drawn. */
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    try {
      const out = await fn();
      await reload();
      return out;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [reload]);

  const create = useCallback((body: NewMarkup) => drawingId == null ? Promise.resolve(null) : run(() => api.createMarkup(optsRef.current, drawingId, body)), [drawingId, run]);
  const update = useCallback((id: number, changes: Parameters<typeof api.patchMarkup>[2]) => run(() => api.patchMarkup(optsRef.current, id, changes)), [run]);
  const remove = useCallback((id: number) => run(() => api.deleteMarkup(optsRef.current, id)), [run]);

  return { markups, summary, loading, error, reload, create, update, remove };
}
