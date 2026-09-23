import { useLayoutEffect, useRef } from "react";
import type { PendingApproval } from "../types/api";

interface ApprovalCardProps {
  approval: PendingApproval;
  count: number;
  isStopping: boolean;
  onDecide: (approval: PendingApproval, approved: boolean) => void;
  onStop: () => void;
}

function approvalPrompt(approval: PendingApproval): string {
  switch (approval.reason) {
    case "write_file":
      return "目标文件位于当前工作目录之外。是否允许写入？";
    case "edit_file":
      return "此操作将修改工作目录外的文件。是否允许？";
    case "apply_patch":
      return `此操作涉及 ${approval.outside_paths?.length ?? 0} 个工作目录外的文件。是否允许执行？`;
    case "exec":
      return "是否允许执行以下命令？";
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
  onDecide,
  onStop,
}: ApprovalCardProps) {
  const cardRef = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const card = cardRef.current;
    const panel = card?.closest<HTMLElement>(".main-panel");
    if (!card || !panel) return;
    const measure = () =>
      panel.style.setProperty("--composer-height", `${card.offsetHeight}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(card);
    return () => {
      observer.disconnect();
      panel.style.removeProperty("--composer-height");
    };
  }, []);

  const disabled = approval.submitting || isStopping;
  const terminal = approval.reason === "exec" || approval.reason === "write_stdin";
  return (
    <section className="composer approval-card" ref={cardRef} aria-label="工具审批">
      <div className="approval-body">
        <div className="approval-heading">
          <span>{terminal ? "终端" : "工具审批"} · {approval.name}</span>
          {count > 1 ? <span>{count} 项待确认</span> : null}
        </div>
        <p className="approval-prompt" role="status">{approvalPrompt(approval)}</p>
        <div className="approval-context">工作目录：{approval.workspace}</div>
        {approval.paths?.map((path) => (
          <code className="approval-path" key={path}>{path}</code>
        ))}
        {approval.command !== undefined ? (
          <>
            <div className="approval-context">执行目录：{approval.working_dir}</div>
            <pre className="approval-code">{approval.command}</pre>
          </>
        ) : null}
        {approval.reason === "write_stdin" ? (
          <>
            <div className="approval-context">
              终端：{String(approval.arguments.session_id ?? "")}
            </div>
            {approval.arguments.chars ? (
              <pre className="approval-code">{String(approval.arguments.chars)}</pre>
            ) : null}
          </>
        ) : null}
        <details className="approval-details">
          <summary>操作详情</summary>
          <pre className="approval-code">
            {approval.reason === "write_file"
              ? String(approval.arguments.content ?? "")
              : JSON.stringify(approval.arguments, null, 2)}
          </pre>
        </details>
      </div>
      <div className="approval-actions">
        <button
          type="button"
          className="approval-stop"
          disabled={isStopping}
          onClick={onStop}
        >
          {isStopping ? "正在停止…" : "停止任务"}
        </button>
        {approval.submitting ? <span role="status">处理中…</span> : null}
        <button type="button" disabled={disabled} onClick={() => onDecide(approval, false)}>
          拒绝
        </button>
        <button
          type="button"
          className="approval-allow"
          disabled={disabled}
          onClick={() => onDecide(approval, true)}
        >
          允许一次
        </button>
      </div>
    </section>
  );
}
