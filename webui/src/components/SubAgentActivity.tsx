import { createContext, memo, useContext, type ReactNode } from "react";
import { workerTaskTitle } from "../lib/worker-reports";
import { StreamedMarkdown } from "./chat/MarkdownContent";
import type {
  WorkerReport,
  ToolActivity,
  ToolActivityStatus,
} from "../types/api";

const BEE_LOGO_PATH = "/brand/bumblehive-bee.png";

interface BeeCounts {
  waiting_approval: number;
  rejected: number;
  preparing: number;
  running: number;
  completed: number;
  error: number;
  cancelled: number;
}

function argumentRecord(tool: ToolActivity): Record<string, unknown> | null {
  return tool.arguments !== null &&
    typeof tool.arguments === "object" &&
    !Array.isArray(tool.arguments)
    ? (tool.arguments as Record<string, unknown>)
    : null;
}

function streamedArgument(tool: ToolActivity, key: string): string {
  const source = tool.streamedArguments;
  if (!source) return "";
  const match = source.match(
    new RegExp(`"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)(?:"|$)`),
  );
  if (!match) return "";
  try {
    return String(JSON.parse(`"${match[1]}"`));
  } catch {
    return match[1];
  }
}

function argumentText(tool: ToolActivity, key: string): string {
  const value = argumentRecord(tool)?.[key];
  if (typeof value === "string" && value.trim()) return value.trim();
  return streamedArgument(tool, key).trim();
}

function beeTitle(tool: ToolActivity): string {
  const title = argumentText(tool, "title");
  if (title) return title;
  const task = argumentText(tool, "task").replace(/\s+/g, " ");
  return task ? task.slice(0, 80) : "正在准备任务";
}

function beeTask(tool: ToolActivity): string {
  return argumentText(tool, "task");
}

function backgroundStarted(tool: ToolActivity): boolean {
  return tool.status === "completed" &&
    Boolean(tool.taskId);
}

function durationLabel(duration: number | undefined): string {
  if (duration === undefined) return "";
  return `${duration < 1 ? duration.toFixed(2) : duration.toFixed(1)}s`;
}

function isActive(status: ToolActivityStatus): boolean {
  return status === "preparing" || status === "running";
}

function singleLabel(status: ToolActivityStatus): string {
  switch (status) {
    case "waiting_approval":
      return "等待审批";
    case "rejected":
      return "已拒绝";
    case "preparing":
      return "正在派出 Bee";
    case "running":
      return "Bee 正在工作";
    case "completed":
      return "Bee 已完成";
    case "error":
      return "Bee 未能完成";
    case "cancelled":
      return "Bee 已停止";
  }
}

function itemStatus(tool: ToolActivity): string {
  switch (tool.status) {
    case "waiting_approval":
      return "等待审批";
    case "rejected":
      return "已拒绝";
    case "preparing":
      return "准备中";
    case "running":
      return "工作中";
    case "completed":
      return durationLabel(tool.durationSeconds) || "已完成";
    case "error":
      return "未完成";
    case "cancelled":
      return "已停止";
  }
}

function statusMark(status: ToolActivityStatus): string {
  if (status === "completed") return "✓";
  if (status === "error") return "!";
  if (status === "cancelled") return "–";
  return "";
}

function beeCounts(tools: ToolActivity[]): BeeCounts {
  const counts: BeeCounts = {
    waiting_approval: 0,
    rejected: 0,
    preparing: 0,
    running: 0,
    completed: 0,
    error: 0,
    cancelled: 0,
  };
  tools.forEach((tool) => {
    counts[tool.status] += 1;
  });
  return counts;
}

function hiveLabel(counts: BeeCounts, total: number): string {
  const active = counts.preparing + counts.running;
  if (counts.waiting_approval) return "Hive 等待审批";
  if (counts.rejected === total) return "Hive 已拒绝";
  if (counts.preparing === total) return "正在调度 Hive";
  if (active) return "Hive 正在协作";
  if (counts.completed === total) return "Hive 协作完成";
  if (counts.error === total) return "Hive 协作失败";
  if (counts.cancelled === total) return "Hive 协作已停止";
  return "Hive 协作结束";
}

function hiveSummary(counts: BeeCounts, total: number): string {
  if (counts.preparing === total) return `${total} 个 Bee 正在准备`;
  if (counts.running === total) return `${total} 个 Bee 正在工作`;
  if (counts.completed === total) return `${total} 个任务全部完成`;
  if (counts.error === total) return `${total} 个任务失败`;
  if (counts.cancelled === total) return `${total} 个任务已停止`;

  return [
    counts.waiting_approval ? `${counts.waiting_approval} 等待审批` : "",
    counts.rejected ? `${counts.rejected} 已拒绝` : "",
    counts.running ? `${counts.running} 工作中` : "",
    counts.preparing ? `${counts.preparing} 准备中` : "",
    counts.completed ? `${counts.completed} 完成` : "",
    counts.error ? `${counts.error} 失败` : "",
    counts.cancelled ? `${counts.cancelled} 停止` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function groupStatus(counts: BeeCounts, total: number): ToolActivityStatus {
  if (counts.waiting_approval) return "waiting_approval";
  if (counts.rejected === total) return "rejected";
  if (counts.running) return "running";
  if (counts.preparing) return "preparing";
  if (counts.completed === total) return "completed";
  if (counts.error === total) return "error";
  if (counts.cancelled === total) return "cancelled";
  return counts.error ? "error" : "cancelled";
}

function BeeLogo({ active }: { active: boolean }) {
  return (
    <span className={`subagent-logo${active ? " active" : ""}`} aria-hidden="true">
      <img alt="" src={BEE_LOGO_PATH} />
    </span>
  );
}

export const WorkerTasksContext = createContext<ReadonlyMap<string, ToolActivity>>(new Map());

function BeeDisclosure({ title, className, active = false, children }: {
  title: string;
  className: string;
  active?: boolean;
  children: ReactNode;
}) {
  return (
    <details className={className}>
      <summary className="subagent-summary">
        <BeeLogo active={active} />
        <span>{title}</span>
        <span className="tool-detail-chevron" aria-hidden="true" />
      </summary>
      {children}
    </details>
  );
}

export function WorkerReportRow({ report }: { report: WorkerReport }) {
  return (
    <BeeDisclosure className="worker-report" title={report.title}>
      <div className="worker-report-body markdown-body">
        <StreamedMarkdown content={report.body} />
      </div>
    </BeeDisclosure>
  );
}

export function AgentMessageRow({ tool }: { tool: ToolActivity }) {
  const tasks = useContext(WorkerTasksContext);
  const target = argumentText(tool, "target");
  const workerTitle = workerTaskTitle(tasks.get(target));
  const recipient = target === "parent" ? "主 Agent" : workerTitle ? `「${workerTitle}」` : " Worker";
  const value = argumentRecord(tool)?.message;
  const message = typeof value === "string" ? value : streamedArgument(tool, "message");
  const status: Partial<Record<ToolActivityStatus, string>> = { error: "发送失败", cancelled: "已停止", rejected: "已拒绝", waiting_approval: "等待审批" };
  const state = status[tool.status];
  const title = target ? `发给${recipient}` : "发送消息";
  return (
    <BeeDisclosure className="agent-message" title={state ? `${title} · ${state}` : title} active={isActive(tool.status)}>
      <div className="worker-report-body">
        {target && target !== "parent" && !workerTitle && <div className="agent-message-target">任务 ID：{target}</div>}
        <div className="agent-message-text">{message}</div>
        {tool.errorMessage && <div className="subagent-error-message">{tool.errorMessage}</div>}
      </div>
    </BeeDisclosure>
  );
}

const BeeDetail = memo(function BeeDetail({ tool }: { tool: ToolActivity }) {
  const task = beeTask(tool);
  return (
    <div className="subagent-task-detail">
      <span className="subagent-detail-label">任务</span>
      <p>{task || "正在生成任务说明…"}</p>
      {tool.errorMessage ? (
        <p className="subagent-error-message">{tool.errorMessage}</p>
      ) : null}
    </div>
  );
});

const HiveItem = memo(function HiveItem({ tool }: { tool: ToolActivity }) {
  const active = isActive(tool.status);
  const task = beeTask(tool);
  return (
    <div className={`hive-bee-item hive-bee-${tool.status}`}>
      <span className="hive-bee-mark" aria-hidden="true">
        {active ? <span /> : statusMark(tool.status)}
      </span>
      <div className="hive-bee-copy">
        <span className="hive-bee-title">{beeTitle(tool)}</span>
        {task ? <span className="hive-bee-task">{task}</span> : null}
        {tool.errorMessage ? (
          <span className="hive-bee-error">{tool.errorMessage}</span>
        ) : null}
      </div>
      <span className="hive-bee-status">{backgroundStarted(tool) ? "后台已启动" : itemStatus(tool)}</span>
    </div>
  );
});

export const SubAgentActivity = memo(function SubAgentActivity({
  tools,
}: {
  tools: ToolActivity[];
}) {
  if (tools.length === 1) {
    const tool = tools[0];
    const active = isActive(tool.status);
    const duration = durationLabel(tool.durationSeconds);
    return (
      <details
        className={`tool-entry subagent-entry subagent-${tool.status}`}
      >
        <summary className="subagent-summary">
          <BeeLogo active={active} />
          <span className="subagent-copy">
            <span className="subagent-label">{backgroundStarted(tool) ? "已启动后台 Bee" : singleLabel(tool.status)}</span>
            <span className="subagent-subtitle">{beeTitle(tool)}</span>
          </span>
          <span className="subagent-duration">{duration}</span>
          <span className="tool-detail-chevron" aria-hidden="true" />
        </summary>
        <BeeDetail tool={tool} />
      </details>
    );
  }

  const counts = beeCounts(tools);
  const status = groupStatus(counts, tools.length);
  const backgroundCount = tools.filter(backgroundStarted).length;
  const summaryCounts = { ...counts, completed: counts.completed - backgroundCount };
  return (
    <details className={`tool-entry subagent-entry hive-entry hive-${status}`}>
      <summary className="subagent-summary">
        <BeeLogo active={isActive(status)} />
        <span className="subagent-copy">
          <span className="subagent-label">
            {backgroundCount && counts.completed === tools.length
              ? "Hive 任务已派发" : hiveLabel(counts, tools.length)}
          </span>
          <span className="subagent-subtitle">
            {backgroundCount
              ? [`${backgroundCount} 个后台已启动`, hiveSummary(summaryCounts, tools.length)].filter(Boolean).join(" · ")
              : hiveSummary(counts, tools.length)}
          </span>
        </span>
        <span className="subagent-duration" />
        <span className="tool-detail-chevron" aria-hidden="true" />
      </summary>
      <div className="hive-bee-list">
        {tools.map((tool) => (
          <HiveItem key={tool.id} tool={tool} />
        ))}
      </div>
    </details>
  );
});
