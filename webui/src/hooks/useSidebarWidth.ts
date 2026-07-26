import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

export const DEFAULT_SIDEBAR_WIDTH = 276;
export const MIN_SIDEBAR_WIDTH = 224;
export const MAX_SIDEBAR_WIDTH = 420;

const STORAGE_KEY = "bumblehive.sidebar-width";

function clamp(width: number): number {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, width));
}

function initialWidth(): number {
  try {
    const stored = Number(window.localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(stored) && stored > 0
      ? clamp(stored)
      : DEFAULT_SIDEBAR_WIDTH;
  } catch {
    return DEFAULT_SIDEBAR_WIDTH;
  }
}

export function useSidebarWidth() {
  const [width, setWidth] = useState(initialWidth);
  const resizeRef = useRef<{
    pointerId: number;
    startX: number;
    startWidth: number;
  } | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(Math.round(width)));
    } catch {
      // Persistent storage is optional; resizing still works in memory.
    }
  }, [width]);

  useEffect(
    () => () => document.body.classList.remove("sidebar-is-resizing"),
    [],
  );

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: width,
    };
    document.body.classList.add("sidebar-is-resizing");
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const resize = resizeRef.current;
    if (!resize || resize.pointerId !== event.pointerId) return;
    setWidth(clamp(resize.startWidth + event.clientX - resize.startX));
  }

  function onPointerEnd(event: PointerEvent<HTMLDivElement>) {
    const resize = resizeRef.current;
    if (!resize || resize.pointerId !== event.pointerId) return;
    resizeRef.current = null;
    document.body.classList.remove("sidebar-is-resizing");
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 24 : 8;
    const next = {
      ArrowLeft: width - step,
      ArrowRight: width + step,
      Home: MIN_SIDEBAR_WIDTH,
      End: MAX_SIDEBAR_WIDTH,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    setWidth(clamp(next));
  }

  return {
    width,
    style: { "--sidebar-width": `${width}px` } as CSSProperties,
    reset: () => setWidth(DEFAULT_SIDEBAR_WIDTH),
    resizerProps: {
      onKeyDown,
      onPointerDown,
      onPointerMove,
      onPointerUp: onPointerEnd,
      onPointerCancel: onPointerEnd,
    },
  };
}
