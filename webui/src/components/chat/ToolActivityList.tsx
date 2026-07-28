import { memo, useState } from "react";
import { normalizeToolActivityOutcome } from "../../tool-details";
import type {
  AssistantIteration,
  ToolActivity,
  ToolActivityStatus,
} from "../../types/api";
import { SubAgentActivity } from "../SubAgentActivity";
import { getToolPresentation } from "../tool-presentation";
import {
  hasExpandableToolDetail,
  mergeShellDetails,
  shellSessionId,
  ToolDetailPanel,
} from "../ToolDetailPanel";

const READ_ACTIVITY_TOOLS = new Set([
  "read_file",
  "list_dir",
  "find_files",
  "grep",
]);

type ToolDisplayRow =
  | { kind: "tool"; tool: ToolActivity }
  | { kind: "reads"; id: string; tools: ToolActivity[] }
  | { kind: "subagents"; id: string; tools: ToolActivity[] };

function toolDisplayRows(tools: ToolActivity[]): ToolDisplayRow[] {
  const rows: ToolDisplayRow[] = [];
  let reads: ToolActivity[] = [];
  let subagents: ToolActivity[] = [];

  function flushReads() {
    if (!reads.length) return;
    rows.push({
      kind: "reads",
      id: `reads-${reads[0].id}-${reads.at(-1)?.id}`,
      tools: reads,
    });
    reads = [];
  }

  function flushSubagents() {
    if (!subagents.length) return;
    rows.push({
      kind: "subagents",
      id: `subagents-${subagents[0].id}-${subagents.at(-1)?.id}`,
      tools: subagents,
    });
    subagents = [];
  }

  tools.forEach((tool) => {
    if (READ_ACTIVITY_TOOLS.has(tool.name) && tool.status !== "error") {
      flushSubagents();
      reads.push(tool);
      return;
    }
    if (tool.name === "sub_agent") {
      flushReads();
      subagents.push(tool);
      return;
    }
    flushReads();
    flushSubagents();
    rows.push({ kind: "tool", tool });
  });
  flushReads();
  flushSubagents();
  return rows;
}

export function consolidateShellIterations(
  iterations: AssistantIteration[],
): AssistantIteration[] {
  const normalized = iterations.map((iteration) => ({
    ...iteration,
    tools: iteration.tools ? [...iteration.tools] : undefined,
  }));
  const shellBySession = new Map<
    string,
    { iterationIndex: number; toolIndex: number }
  >();
  const mergedWriteTools = new Set<string>();

  normalized.forEach((iteration, iterationIndex) => {
    iteration.tools?.forEach((tool, toolIndex) => {
      const sessionId = shellSessionId(tool);
      if (tool.name === "exec" && sessionId) {
        shellBySession.set(sessionId, { iterationIndex, toolIndex });
        return;
      }
      if (tool.name !== "write_stdin" || !sessionId) return;

      const owner = shellBySession.get(sessionId);
      if (!owner) return;
      const original =
        normalized[owner.iterationIndex].tools?.[owner.toolIndex];
      if (!original) return;
      const detail =
        original.detail?.kind === "shell" &&
        tool.detail?.kind === "shell"
          ? mergeShellDetails(original.detail, tool.detail)
          : original.detail;
      normalized[owner.iterationIndex].tools![owner.toolIndex] =
        normalizeToolActivityOutcome({
          ...original,
          status: tool.status,
          durationSeconds:
            (original.durationSeconds ?? 0) +
            (tool.durationSeconds ?? 0),
          errorMessage: tool.errorMessage || original.errorMessage,
          detail,
        });
      mergedWriteTools.add(tool.id);
    });
  });

  return normalized.map((iteration) => ({
    ...iteration,
    tools: iteration.tools?.filter((tool) => !mergedWriteTools.has(tool.id)),
  }));
}

function ToolGlyph({
  tool,
  running,
}: {
  tool: ToolActivity;
  running: boolean;
}) {
  if (running) {
    return <span className="tool-step-spinner" aria-hidden="true" />;
  }
  if (tool.status === "cancelled") {
    return <span className="tool-step-stopped" aria-hidden="true" />;
  }
  if (
    tool.name === "edit_file" ||
    tool.name === "write_file" ||
    tool.name === "apply_patch"
  ) {
    return (
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M3.1 11.85 2.7 14l2.15-.4 7.55-7.55-1.75-1.75Z" />
        <path d="m9.8 5.15 1.75 1.75M10.65 4.3l.75-.75a1.24 1.24 0 0 1 1.75 0l.1.1a1.24 1.24 0 0 1 0 1.75l-.85.65" />
      </svg>
    );
  }
  if (
    tool.name === "exec" ||
    tool.name === "write_stdin" ||
    tool.name === "list_exec_sessions"
  ) {
    return (
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <rect x="2.25" y="3" width="11.5" height="10" rx="2" />
        <path d="m4.5 6 2 1.7-2 1.7M8.2 10h3" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d="M2.5 4.25h4l1.1 1.25h5.9v6.25a1.5 1.5 0 0 1-1.5 1.5H4a1.5 1.5 0 0 1-1.5-1.5Z" />
    </svg>
  );
}

function ToolStepRow({
  tool,
  open,
  expandable,
}: {
  tool: ToolActivity;
  open: boolean;
  expandable: boolean;
}) {
  const running = tool.status === "running" || tool.status === "preparing";
  const presentation = getToolPresentation(tool);
  return (
    <>
      <span className="tool-step-icon">
        <ToolGlyph running={running} tool={tool} />
      </span>
      <span className="tool-step-name">{presentation.label}</span>
      <span className="tool-step-summary">{presentation.summary}</span>
      <span className="tool-step-status">{presentation.duration}</span>
      {expandable ? (
        <span
          className={`tool-detail-chevron${open ? " open" : ""}`}
          aria-hidden="true"
        />
      ) : (
        <span />
      )}
    </>
  );
}

const ToolEntry = memo(function ToolEntry({ tool }: { tool: ToolActivity }) {
  const expandable = hasExpandableToolDetail(tool);
  const [open, setOpen] = useState(false);
  const title = `工具：${tool.name}`;

  return (
    <section
      className={`tool-entry tool-step-${tool.status}${
        open ? " open" : ""
      }`}
    >
      {expandable ? (
        <button
          className="tool-step"
          type="button"
          aria-expanded={open}
          title={title}
          onClick={() => setOpen((current) => !current)}
        >
          <ToolStepRow expandable open={open} tool={tool} />
        </button>
      ) : (
        <div className="tool-step" title={title}>
          <ToolStepRow expandable={false} open={false} tool={tool} />
        </div>
      )}
      {open ? (
        <div className="tool-detail-panel">
          <ToolDetailPanel tool={tool} />
        </div>
      ) : null}
    </section>
  );
});

function readActivityStatus(tools: ToolActivity[]): ToolActivityStatus {
  if (tools.some((tool) => tool.status === "running")) return "running";
  if (tools.some((tool) => tool.status === "preparing")) return "preparing";
  if (tools.some((tool) => tool.status === "cancelled")) return "cancelled";
  return "completed";
}

function toolArguments(tool: ToolActivity): Record<string, unknown> {
  return tool.arguments !== null &&
    typeof tool.arguments === "object" &&
    !Array.isArray(tool.arguments)
    ? (tool.arguments as Record<string, unknown>)
    : {};
}

function argumentText(
  tool: ToolActivity,
  key: string,
): string | undefined {
  const value = toolArguments(tool)[key];
  return typeof value === "string" && value ? value : undefined;
}

function readActivityTarget(tool: ToolActivity): string {
  const detail = tool.detail?.kind === "read" ? tool.detail : undefined;
  if (tool.name === "grep") {
    const pattern = argumentText(tool, "pattern");
    return pattern ? `“${pattern}”` : "文件内容";
  }
  if (tool.name === "find_files") {
    return (
      argumentText(tool, "query") ??
      argumentText(tool, "glob") ??
      argumentText(tool, "type") ??
      "项目文件"
    );
  }
  return argumentText(tool, "path") ?? detail?.path ?? ".";
}

function readActivityMetadata(tool: ToolActivity): string {
  const detail = tool.detail?.kind === "read" ? tool.detail : undefined;
  const scope =
    tool.name === "grep" || tool.name === "find_files"
      ? argumentText(tool, "path") ?? "."
      : "";
  const values: string[] = [];
  if (scope) values.push(`范围 ${scope}`);
  if (
    detail?.startLine !== undefined &&
    detail.endLine !== undefined
  ) {
    values.push(`第 ${detail.startLine}–${detail.endLine} 行`);
  } else if (detail?.pages) {
    values.push(`第 ${detail.pages} 页`);
  }
  if (detail?.totalEntries !== undefined) {
    values.push(`${detail.totalEntries} 项`);
  }
  if (detail?.totalMatches !== undefined) {
    values.push(`${detail.totalMatches} 处结果`);
  }
  if (detail?.deduplicated) values.push("已读取过");
  if (detail?.truncated) values.push("结果已截断");
  return values.join(" · ");
}

function readActivityLabel(tool: ToolActivity): string {
  const running = tool.status === "running" || tool.status === "preparing";
  if (tool.name === "read_file") return running ? "正在读取" : "读取了";
  if (tool.name === "list_dir") return running ? "正在查看" : "查看了";
  if (tool.name === "find_files") return running ? "正在查找" : "查找了";
  return running ? "正在搜索" : "搜索了";
}

const ReadActivityItem = memo(function ReadActivityItem({
  tool,
}: {
  tool: ToolActivity;
}) {
  const detail = tool.detail?.kind === "read" ? tool.detail : undefined;
  const duration = getToolPresentation(tool).duration;
  return (
    <div className="tool-read-detail">
      <div className="tool-read-detail-row">
        <span className="tool-read-detail-action">
          {readActivityLabel(tool)}
        </span>
        <code className="tool-read-detail-target" title={readActivityTarget(tool)}>
          {readActivityTarget(tool)}
        </code>
        <span className="tool-read-detail-meta">
          {readActivityMetadata(tool)}
        </span>
        <span className="tool-read-detail-duration">{duration}</span>
      </div>
      {detail?.items?.length ? (
        <div className="tool-read-result-items">
          {detail.items.map((item) => (
            <code key={item} title={item}>
              {item}
            </code>
          ))}
        </div>
      ) : null}
    </div>
  );
});

const ReadActivity = memo(function ReadActivity({
  tools,
}: {
  tools: ToolActivity[];
}) {
  const status = readActivityStatus(tools);
  const running = status === "running" || status === "preparing";
  const files = tools.filter((tool) => tool.name === "read_file").length;
  const searches = tools.filter(
    (tool) => tool.name === "grep" || tool.name === "find_files",
  ).length;
  const directories = tools.filter(
    (tool) => tool.name === "list_dir",
  ).length;
  const details = [
    files ? `${files} 个文件` : "",
    searches ? `${searches} 次搜索` : "",
    directories ? `${directories} 次查看` : "",
  ].filter(Boolean);

  return (
    <details className={`tool-entry tool-step-${status} tool-read-entry`}>
      <summary
        className="tool-step tool-read-summary"
      >
        <span className="tool-step-icon">
          {running ? (
            <span className="tool-step-spinner" aria-hidden="true" />
          ) : (
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M2.5 4.25h4l1.1 1.25h5.9v6.25a1.5 1.5 0 0 1-1.5 1.5H4a1.5 1.5 0 0 1-1.5-1.5Z" />
              <path d="M5 8h6M5 10.25h4" />
            </svg>
          )}
        </span>
        <span className="tool-step-name">
          {running ? "正在查看项目" : "已查看项目"}
        </span>
        <span className="tool-step-summary">{details.join(" · ")}</span>
        <span className="tool-step-status" />
        <span
          className="tool-detail-chevron"
          aria-hidden="true"
        />
      </summary>
      <div className="tool-read-details">
        {tools.map((tool) => (
          <ReadActivityItem key={tool.id} tool={tool} />
        ))}
      </div>
    </details>
  );
});

export const ToolSteps = memo(function ToolSteps({ tools }: { tools: ToolActivity[] }) {
  const rows = toolDisplayRows(tools);
  return (
    <div className="tool-steps" aria-label="工具调用">
      {rows.map((row) =>
        row.kind === "reads" ? (
          <ReadActivity key={row.id} tools={row.tools} />
        ) : row.kind === "subagents" ? (
          <SubAgentActivity key={row.id} tools={row.tools} />
        ) : (
          <ToolEntry key={row.tool.id} tool={row.tool} />
        ),
      )}
    </div>
  );
});
