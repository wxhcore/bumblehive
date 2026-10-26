import { useEffect, type RefObject } from "react";

// Native buttons retain their Tab order; arrows move between enabled options.
export function useMenuNavigation(open: boolean, fieldRef: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const field = fieldRef.current;
    if (!field) return;
    const trigger = field.querySelector<HTMLButtonElement>("[aria-haspopup]");
    const menu = field.querySelector<HTMLElement>("[data-menu]");
    const options = () => [...(menu?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
    const selected = menu?.querySelector<HTMLButtonElement>('[aria-selected="true"], [aria-pressed="true"]');
    (selected ?? options()[0])?.focus({ preventScroll: true });
    function onPointer(event: PointerEvent) {
      if (event.target instanceof Node && !field!.contains(event.target)) onClose();
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation(); onClose(); trigger?.focus();
      } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        const items = options();
        if (!items.length) return;
        event.preventDefault();
        const index = items.indexOf(document.activeElement as HTMLButtonElement);
        const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length;
        items[next]?.focus();
      }
    }
    function onFocus(event: FocusEvent) {
      if (event.relatedTarget instanceof Node && !field!.contains(event.relatedTarget)) onClose();
    }
    document.addEventListener("pointerdown", onPointer);
    field.addEventListener("keydown", onKey);
    field.addEventListener("focusout", onFocus);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      field.removeEventListener("keydown", onKey);
      field.removeEventListener("focusout", onFocus);
    };
  }, [open, fieldRef, onClose]);
}
