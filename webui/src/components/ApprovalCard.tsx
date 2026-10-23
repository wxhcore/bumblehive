import { useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import type { PendingApproval } from "../types/api";

interface ApprovalCardProps {
  approval: PendingApproval;
  count: number;
  isStopping: boolean;
  disconnected?: boolean;
  onDecide: (approval: PendingApproval, approved: boolean) => void;
}

function approvalPrompt(approval: PendingApproval): string {
  switch (approval.reason) {
    case "write_file":
      return "目标文件位于当前工作目录之外。是否允许写入？";
    case "edit_file":
      return "此操作将修改工作目录外的文件。是否允许？";
    case "apply_patch":
      return `此操作涉及 ${approval.outside_paths?.length ?? 0} 个工作目录外的文件。是否允许执行？`;
    case "exec": {
      const justification = approval.arguments.justification;
      return typeof justification === "string" && justification.trim()
        ? justification.trim()
        : "是否允许执行以下命令？";
    }
    case "write_stdin": {
      const actions = [];
      if (approval.arguments.chars) actions.push("向该终端发送以下输入");
      if (approval.arguments.close_stdin) actions.push("关闭该终端的输入");
      if (approval.arguments.terminate) actions.push("终止该进程");
      return `是否允许${actions.join("并")}？`;
    }
    default:
      return `是否允许调用 ${approval.name}？`;
  }
}

export function ApprovalCard({
  approval,
  count,
  isStopping,
  disconnected = false,
  onDecide,
}: ApprovalCardProps) {
  const cardRef = useRef<HTMLElement>(null);
  const previewId = useId();
  const promptId = useId();
  const [expanded, setExpanded] = useState(true);
  useLayoutEffect(() => {
    cardRef.current?.focus({ preventScroll: true });
  }, []);

  const disabled = approval.submitting || isStopping || disconnected;
  const terminal = approval.reason === "exec" || approval.reason === "write_stdin";
  const preview = approval.command ?? (
    approval.reason === "write_stdin" ? String(approval.arguments.chars ?? "")
      : approval.reason === "write_file" ? String(approval.arguments.content ?? "")
        : JSON.stringify(approval.arguments, null, 2)
  );

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (disabled || event.repeat || event.nativeEvent.isComposing ||
      event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onDecide(approval, false);
    } else if (event.key === "Enter" && event.target === event.currentTarget) {
      event.preventDefault();
      event.stopPropagation();
      onDecide(approval, true);
    }
  }

  return (
    <section className="approval-card" ref={cardRef} tabIndex={-1}
      aria-label="工具审批" aria-describedby={promptId} onKeyDown={handleKeyDown}>
      <div className="approval-body">
        <div className="approval-heading">
          <span className="approval-label">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="3" y="3" width="18" height="18" rx="4" />
              {terminal ? <path d="m7 8 3 4-3 4m6 0h4" /> : <path d="m7 12 3 3 7-7" />}
            </svg>
            {terminal ? "终端" : `工具审批 · ${approval.name}`}
          </span>
          {count > 1 ? <span>{count} 项待确认</span> : null}
        </div>
        <p id={promptId} className="approval-prompt">{approvalPrompt(approval)}</p>
        <div id={previewId} hidden={!expanded}>
          {approval.paths?.map((path) => (
            <code className="approval-path" key={path}>{path}</code>
          ))}
          {preview ? <pre className="approval-code">{preview}</pre> : null}
        </div>
        <div className="approval-disclosure">
          <button type="button" aria-expanded={expanded} aria-controls={previewId}
            onClick={() => setExpanded((value) => !value)}>
            {expanded ? "折叠" : "展开"}
          </button>
        </div>
      </div>
      <div className="approval-actions">
        {disconnected || approval.submitting ? (
          <span className="approval-status" role="status">
            {disconnected ? "连接已中断，等待重连…" : "处理中…"}
          </span>
        ) : null}
        <button type="button" disabled={disabled} onClick={() => onDecide(approval, false)}>
          拒绝 <kbd>Esc</kbd>
        </button>
        <button type="button" className="approval-allow" disabled={disabled} onClick={() => onDecide(approval, true)}>
          允许一次 <kbd aria-label="回车">↵</kbd>
        </button>
      </div>
    </section>
  );
}
