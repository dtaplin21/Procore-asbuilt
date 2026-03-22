import { ReactNode, useCallback, useMemo, useRef, useState } from "react";

type Point = {
  x: number;
  y: number;
};

type TransformState = {
  scale: number;
  x: number;
  y: number;
};

type Props = {
  children: ReactNode;
  minScale?: number;
  maxScale?: number;
  initialScale?: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export default function PanZoomContainer({
  children,
  minScale = 0.5,
  maxScale = 5,
  initialScale = 1,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [transform, setTransform] = useState<TransformState>({
    scale: initialScale,
    x: 0,
    y: 0,
  });

  const [isDragging, setIsDragging] = useState(false);

  const dragRef = useRef<{
    pointerId: number;
    startPointer: Point;
    startTransform: TransformState;
  } | null>(null);

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      event.preventDefault();

      const container = containerRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const pointerX = event.clientX - rect.left;
      const pointerY = event.clientY - rect.top;

      const zoomIntensity = 0.0015;
      const scaleDelta = Math.exp(-event.deltaY * zoomIntensity);

      setTransform((current) => {
        const nextScale = clamp(current.scale * scaleDelta, minScale, maxScale);

        const worldX = (pointerX - current.x) / current.scale;
        const worldY = (pointerY - current.y) / current.scale;

        const nextX = pointerX - worldX * nextScale;
        const nextY = pointerY - worldY * nextScale;

        return {
          scale: nextScale,
          x: nextX,
          y: nextY,
        };
      });
    },
    [minScale, maxScale]
  );

  const handlePointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;

    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);

    setIsDragging(true);

    dragRef.current = {
      pointerId: event.pointerId,
      startPointer: {
        x: event.clientX,
        y: event.clientY,
      },
      startTransform: transform,
    };
  }, [transform]);

  const handlePointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const dragState = dragRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) return;

    const deltaX = event.clientX - dragState.startPointer.x;
    const deltaY = event.clientY - dragState.startPointer.y;

    setTransform({
      ...dragState.startTransform,
      x: dragState.startTransform.x + deltaX,
      y: dragState.startTransform.y + deltaY,
    });
  }, []);

  const stopDragging = useCallback((event?: React.PointerEvent<HTMLDivElement>) => {
    if (event && event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    setIsDragging(false);
    dragRef.current = null;
  }, []);

  const resetView = useCallback(() => {
    setTransform({
      scale: initialScale,
      x: 0,
      y: 0,
    });
  }, [initialScale]);

  const percent = useMemo(() => Math.round(transform.scale * 100), [transform.scale]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="text-xs text-slate-500">Zoom: {percent}%</div>

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
        className={`relative flex-1 overflow-hidden bg-slate-100 touch-none ${
          isDragging ? "cursor-grabbing" : "cursor-grab"
        }`}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
        data-testid="pan-zoom-container"
      >
        <div
          className="absolute left-0 top-0 will-change-transform"
          style={{
            transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
            transformOrigin: "0 0",
          }}
          data-testid="pan-zoom-content"
        >
          {children}
        </div>
      </div>
    </div>
  );
}
