import { useEffect, useRef, useState } from "react";
import type { ApprovalMode } from "../types/api";

const OPTIONS = [
  { value: "request", label: "请求批准", description: "修改工作目录外的文件、执行终端命令时询问。" },
  { value: "full_access", label: "完全访问", description: "允许读写电脑上的任意目录、执行终端命令。" },
] satisfies Array<{ value: ApprovalMode; label: string; description: string }>;

interface ApprovalModeSelectProps {
  mode: ApprovalMode;
  disabled: boolean;
  onSelect: (mode: ApprovalMode) => void;
}

export function ApprovalModeSelect({ mode, disabled, onSelect }: ApprovalModeSelectProps) {
  const [open, setOpen] = useState(false);
  const fieldRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open || disabled) return;
    function closeOnOutsidePointer(event: PointerEvent) {
      if (event.target instanceof Node && !fieldRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePointer);
  }, [open, disabled]);

  const selected = OPTIONS.find((option) => option.value === mode)!;
  return (
    <div
      ref={fieldRef}
      className="approval-mode-field"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
          event.currentTarget.querySelector<HTMLButtonElement>(".approval-mode-button")?.focus();
        }
      }}
    >
      <button
        type="button"
        className={`workspace-button approval-mode-button${mode === "full_access" ? " full-access" : ""}`}
        aria-label={`审批模式：${selected.label}`}
        aria-expanded={open && !disabled}
        aria-haspopup="dialog"
        title={disabled ? "本轮任务使用启动时的审批模式" : selected.description}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="M10 2 17 5v5c0 4-7 8-7 8s-7-4-7-8V5Z" />
          <path d="m7 10 2 2 4-4" />
        </svg>
        <span>{selected.label}</span>
      </button>
      {open && !disabled ? (
        <div className="approval-mode-menu" role="dialog" aria-label="选择审批模式">
          {OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={mode === option.value}
              className={option.value === "full_access" ? "full-access" : ""}
              onClick={() => {
                onSelect(option.value);
                setOpen(false);
              }}
            >
              <span className="approval-mode-copy">
                <strong>{option.label}</strong>
                <span>{option.description}</span>
              </span>
              <span aria-hidden="true">{mode === option.value ? "✓" : ""}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
