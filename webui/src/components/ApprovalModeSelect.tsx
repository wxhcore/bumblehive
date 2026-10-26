import { useCallback, useRef, useState } from "react";
import { useMenuNavigation } from "../hooks/useMenuNavigation";
import type { ApprovalMode } from "../types/api";

const OPTIONS = [
  { value: "request", label: "请求批准", description: "修改工作目录外的文件、执行终端命令时询问。" },
  { value: "full_access", label: "完全访问", description: "允许读写电脑上的任意目录、执行终端命令。" },
] satisfies Array<{ value: ApprovalMode; label: string; description: string }>;

interface ApprovalModeSelectProps {
  mode: ApprovalMode;
  disabled: boolean;
  onSelect: (mode: ApprovalMode) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function ApprovalModeSelect({ mode, disabled, onSelect, open: controlledOpen, onOpenChange }: ApprovalModeSelectProps) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = onOpenChange ?? setLocalOpen;
  const close = useCallback(() => setOpen(false), [setOpen]);
  const fieldRef = useRef<HTMLDivElement>(null);
  useMenuNavigation(open && !disabled, fieldRef, close);

  const selected = OPTIONS.find((option) => option.value === mode)!;
  return (
    <div ref={fieldRef} className="approval-mode-field">
      <button
        type="button"
        className={`workspace-button approval-mode-button${mode === "full_access" ? " full-access" : ""}`}
        aria-label={`审批模式：${selected.label}`}
        aria-expanded={open && !disabled}
        aria-haspopup="dialog"
        title={disabled ? "本轮任务使用启动时的审批模式" : selected.description}
        disabled={disabled}
        onClick={() => setOpen(!open)}
      >
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="M10 2 17 5v5c0 4-7 8-7 8s-7-4-7-8V5Z" />
          <path d="m7 10 2 2 4-4" />
        </svg>
        <span>{selected.label}</span>
      </button>
      {open && !disabled ? (
        <div className="approval-mode-menu" data-menu role="dialog" aria-label="选择审批模式">
          {OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={mode === option.value}
              className={option.value === "full_access" ? "full-access" : ""}
              onClick={() => {
                onSelect(option.value);
                setOpen(false);
                fieldRef.current?.querySelector<HTMLButtonElement>(".approval-mode-button")?.focus();
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
