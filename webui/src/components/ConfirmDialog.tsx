import type { ReactNode } from "react";

interface ConfirmDialogProps {
  title: string;
  titleId: string;
  children: ReactNode;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({
  title,
  titleId,
  children,
  confirmLabel,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <div className="confirm-backdrop" role="presentation">
      <section
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 id={titleId}>{title}</h2>
        <p>{children}</p>
        <div className="confirm-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={onCancel}
          >
            取消
          </button>
          <button
            className="danger-button"
            type="button"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
