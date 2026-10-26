import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface ConfirmDialogProps {
  title: string;
  titleId: string;
  children: ReactNode;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({ title, titleId, children, confirmLabel, onCancel, onConfirm }: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previousFocus = document.activeElement;
    const dialog = dialogRef.current;
    dialog?.showModal();
    cancelRef.current?.focus();
    return () => {
      dialog?.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);
  // SSR preserves the dialog markup for component rendering and tests.
  const content = <dialog ref={dialogRef} className="confirm-dialog" aria-labelledby={titleId} aria-describedby={`${titleId}Description`} onCancel={(event) => { event.preventDefault(); onCancel(); }}>
    <h2 id={titleId}>{title}</h2>
    <p id={`${titleId}Description`}>{children}</p>
    <div className="confirm-actions">
      <button ref={cancelRef} className="secondary-button" type="button" onClick={onCancel}>取消</button>
      <button className="danger-button" type="button" onClick={onConfirm}>{confirmLabel}</button>
    </div>
  </dialog>;
  return typeof document === "undefined" ? content : createPortal(content, document.body);
}
