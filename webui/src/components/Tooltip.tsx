import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const anchorRef = useRef<HTMLSpanElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number; below: boolean } | null>(null);
  const hide = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setPosition(null);
  }, []);
  function show() {
    hide();
    timerRef.current = setTimeout(() => {
      const rect = anchorRef.current?.getBoundingClientRect();
      if (!rect) return;
      const below = rect.top < 60;
      setPosition({ left: Math.max(128, Math.min(window.innerWidth - 128, rect.left + rect.width / 2)), top: below ? rect.bottom + 8 : rect.top - 8, below });
    }, 400);
  }
  useEffect(() => {
    function onKey(event: KeyboardEvent) { if (event.key === "Escape") hide(); }
    window.addEventListener("resize", hide);
    window.addEventListener("scroll", hide, true);
    document.addEventListener("keydown", onKey);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      window.removeEventListener("resize", hide);
      window.removeEventListener("scroll", hide, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [hide]);
  return <span className="tooltip-anchor" ref={anchorRef} onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide} onPointerDown={hide} aria-describedby={position ? id : undefined}>
    {children}
    {position && createPortal(<span id={id} role="tooltip" className={`tooltip-bubble${position.below ? " below" : ""}`} style={{ left: position.left, top: position.top }}>{label}</span>, document.body)}
  </span>;
}
