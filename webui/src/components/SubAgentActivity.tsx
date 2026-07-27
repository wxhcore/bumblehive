import { memo } from "react";
import type {
  ToolActivity,
  ToolActivityStatus,
} from "../types/api";

const BEE_LOGO_PATH = "/brand/bumblehive-bee.png";

interface BeeCounts {
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

function durationLabel(duration: number | undefined): string {
  if (duration === undefined) return "";
  return `${duration < 1 ? duration.toFixed(2) : duration.toFixed(1)}s`;
}

function isActive(status: ToolActivityStatus): boolean {
  return status === "preparing" || status === "running";
}

function singleLabel(status: ToolActivityStatus): string {
  switch (status) {
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
      <span className="hive-bee-status">{itemStatus(tool)}</span>
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
            <span className="subagent-label">{singleLabel(tool.status)}</span>
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
  return (
    <details className={`tool-entry subagent-entry hive-entry hive-${status}`}>
      <summary className="subagent-summary">
        <BeeLogo active={isActive(status)} />
        <span className="subagent-copy">
          <span className="subagent-label">
            {hiveLabel(counts, tools.length)}
          </span>
          <span className="subagent-subtitle">
            {hiveSummary(counts, tools.length)}
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
