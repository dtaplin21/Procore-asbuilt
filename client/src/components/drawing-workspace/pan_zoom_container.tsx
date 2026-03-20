import { ReactNode, useCallback, useMemo, useRef, useState } from "react";

type Props = {
  children: ReactNode;
  minScale?: number;
  maxScale?: number;
  initialScale?: number;
};

type PanState = {
  x: number;
  y: number;
};

export default function PanZoomContainer({
  children,
  minScale = 0.5,
  maxScale = 4,
  initialScale = 1,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(initialScale);
  const [pan, setPan] = useState<PanState>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);

  const dragRef = useRef<{
    originX: number;
    originY: number;
    startPanX: number;
    startPanY: number;
  } | null>(null);

  const clampedScale = useMemo(() => {
    return Math.max(minScale, Math.min(maxScale, scale));
  }, [scale, minScale, maxScale]);

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      event.preventDefault();

      const delta = event.deltaY;
      const zoomStep = delta > 0 ? -0.1 : 0.1;

      setScale((current) => {
        const next = current + zoomStep;
        return Math.max(minScale, Math.min(maxScale, next));
      });
    },
    [minScale, maxScale]
  );

  const handleMouseDown = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;

    setIsDragging(true);

    dragRef.current = {
      originX: event.clientX,
      originY: event.clientY,
      startPanX: pan.x,
      startPanY: pan.y,
    };
  }, [pan.x, pan.y]);

  const handleMouseMove = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;

    const deltaX = event.clientX - dragRef.current.originX;
    const deltaY = event.clientY - dragRef.current.originY;

    setPan({
      x: dragRef.current.startPanX + deltaX,
      y: dragRef.current.startPanY + deltaY,
    });
  }, []);

  const stopDragging = useCallback(() => {
    setIsDragging(false);
    dragRef.current = null;
  }, []);

  const resetView = useCallback(() => {
    setScale(initialScale);
    setPan({ x: 0, y: 0 });
  }, [initialScale]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="text-xs text-slate-500">
          Zoom: {Math.round(clampedScale * 100)}%
        </div>
        <button
          type="button"
          onClick={resetView}
          className="rounded-md border px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
        >
          Reset view
        </button>
      </div>

      <div
        ref={containerRef}
        className={`relative flex-1 overflow-hidden bg-slate-100 ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={stopDragging}
        onMouseLeave={stopDragging}
        data-testid="pan-zoom-container"
      >
        <div
          className="absolute left-1/2 top-1/2 origin-center"
          style={{
            transform: `translate(calc(-50% + ${pan.x}px), calc(-50% + ${pan.y}px)) scale(${clampedScale})`,
            transformOrigin: "center center",
          }}
          data-testid="pan-zoom-content"
        >
          {children}
        </div>
      </div>
    </div>
  );
}
