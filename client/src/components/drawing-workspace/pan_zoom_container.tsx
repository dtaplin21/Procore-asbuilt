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

type PointerMap = Map<number, Point>;

type DragState = {
  pointerId: number;
  startPointer: Point;
  startTransform: TransformState;
};

type PinchState = {
  startDistance: number;
  startMidpoint: Point;
  startTransform: TransformState;
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

function distanceBetween(a: Point, b: Point) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  return Math.sqrt(dx * dx + dy * dy);
}

function midpointBetween(a: Point, b: Point): Point {
  return {
    x: (a.x + b.x) / 2,
    y: (a.y + b.y) / 2,
  };
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
  const [isPinching, setIsPinching] = useState(false);

  const activePointersRef = useRef<PointerMap>(new Map());
  const dragRef = useRef<DragState | null>(null);
  const pinchRef = useRef<PinchState | null>(null);

  const beginPinchIfPossible = useCallback(() => {
    const pointers = Array.from(activePointersRef.current.values());
    if (pointers.length !== 2) return;

    const [p1, p2] = pointers;
    const startDistance = distanceBetween(p1, p2);
    const startMidpoint = midpointBetween(p1, p2);

    pinchRef.current = {
      startDistance,
      startMidpoint,
      startTransform: transform,
    };

    dragRef.current = null;
    setIsDragging(false);
    setIsPinching(true);
  }, [transform]);

  const endPinch = useCallback(() => {
    pinchRef.current = null;
    setIsPinching(false);
  }, []);

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

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const container = event.currentTarget;
      container.setPointerCapture(event.pointerId);

      const rect = container.getBoundingClientRect();
      const point = {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      };

      activePointersRef.current.set(event.pointerId, point);

      const pointerCount = activePointersRef.current.size;

      if (pointerCount === 1) {
        dragRef.current = {
          pointerId: event.pointerId,
          startPointer: point,
          startTransform: transform,
        };
        setIsDragging(true);
        setIsPinching(false);
      } else if (pointerCount === 2) {
        beginPinchIfPossible();
      }
    },
    [transform, beginPinchIfPossible]
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const container = event.currentTarget;
      const rect = container.getBoundingClientRect();

      const point = {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      };

      if (!activePointersRef.current.has(event.pointerId)) {
        return;
      }

      activePointersRef.current.set(event.pointerId, point);

      const pointers = Array.from(activePointersRef.current.values());

      if (pointers.length === 2 && pinchRef.current) {
        const [p1, p2] = pointers;
        const currentDistance = distanceBetween(p1, p2);
        const currentMidpoint = midpointBetween(p1, p2);

        const pinchState = pinchRef.current;

        const rawScale =
          pinchState.startTransform.scale *
          (currentDistance / pinchState.startDistance);

        const nextScale = clamp(rawScale, minScale, maxScale);

        const startWorldX =
          (pinchState.startMidpoint.x - pinchState.startTransform.x) /
          pinchState.startTransform.scale;
        const startWorldY =
          (pinchState.startMidpoint.y - pinchState.startTransform.y) /
          pinchState.startTransform.scale;

        const nextX = currentMidpoint.x - startWorldX * nextScale;
        const nextY = currentMidpoint.y - startWorldY * nextScale;

        setTransform({
          scale: nextScale,
          x: nextX,
          y: nextY,
        });

        return;
      }

      if (pointers.length === 1 && dragRef.current) {
        const dragState = dragRef.current;

        if (dragState.pointerId !== event.pointerId) {
          return;
        }

        const deltaX = point.x - dragState.startPointer.x;
        const deltaY = point.y - dragState.startPointer.y;

        setTransform({
          ...dragState.startTransform,
          x: dragState.startTransform.x + deltaX,
          y: dragState.startTransform.y + deltaY,
        });
      }
    },
    [minScale, maxScale]
  );

  const cleanupPointer = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }

      activePointersRef.current.delete(event.pointerId);

      const pointerCount = activePointersRef.current.size;

      if (pointerCount < 2) {
        endPinch();
      }

      if (pointerCount === 1) {
        const [remainingPointerId, remainingPoint] = Array.from(
          activePointersRef.current.entries()
        )[0];

        dragRef.current = {
          pointerId: remainingPointerId,
          startPointer: remainingPoint,
          startTransform: transform,
        };

        setIsDragging(true);
      } else if (pointerCount === 0) {
        dragRef.current = null;
        setIsDragging(false);
      }
    },
    [transform, endPinch]
  );

  const resetView = useCallback(() => {
    activePointersRef.current.clear();
    dragRef.current = null;
    pinchRef.current = null;
    setIsDragging(false);
    setIsPinching(false);

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
        <div className="text-xs text-slate-500">
          Zoom: {percent}% {isPinching ? "• Pinching" : ""}
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
        className={`relative flex-1 overflow-hidden bg-slate-100 touch-none ${
          isPinching ? "cursor-zoom-in" : isDragging ? "cursor-grabbing" : "cursor-grab"
        }`}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={cleanupPointer}
        onPointerCancel={cleanupPointer}
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
