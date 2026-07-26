import type {
  ToolActivity,
  ToolActivityStatus,
} from "../types/api";
import { textLines } from "../text-lines";

type ToolCopy = Record<ToolActivityStatus, string>;

interface ToolPresentation {
  label: string;
  summary: string;
  duration: string;
  technicalName: string;
}

const BUILTIN_TOOL_COPY: Record<string, ToolCopy> = {
  read_file: {
    preparing: "正在准备读取文件",
    running: "正在读取文件",
    completed: "已读取文件",
    error: "已尝试读取文件",
    cancelled: "读取文件已停止",
  },
  write_file: {
    preparing: "正在生成文件内容",
    running: "正在写入文件",
    completed: "已写入文件",
    error: "已尝试写入文件",
    cancelled: "写入文件已停止",
  },
  edit_file: {
    preparing: "正在准备编辑文件",
    running: "正在编辑文件",
    completed: "已编辑文件",
    error: "已尝试编辑文件",
    cancelled: "编辑文件已停止",
  },
  apply_patch: {
    preparing: "正在生成文件修改",
    running: "正在编辑文件",
    completed: "已编辑文件",
    error: "已尝试编辑文件",
    cancelled: "编辑文件已停止",
  },
  list_dir: {
    preparing: "正在准备查看目录",
    running: "正在查看目录",
    completed: "已查看目录",
    error: "已尝试查看目录",
    cancelled: "查看目录已停止",
  },
  find_files: {
    preparing: "正在准备查找文件",
    running: "正在查找文件",
    completed: "已查找文件",
    error: "已尝试查找文件",
    cancelled: "查找文件已停止",
  },
  grep: {
    preparing: "正在准备搜索内容",
    running: "正在搜索内容",
    completed: "已搜索内容",
    error: "已尝试搜索内容",
    cancelled: "搜索内容已停止",
  },
  exec: {
    preparing: "正在生成 Shell 命令",
    running: "正在运行 Shell 命令",
    completed: "已运行 Shell 命令",
    error: "已运行 Shell 命令",
    cancelled: "Shell 命令已停止",
  },
  write_stdin: {
    preparing: "正在准备向 Shell 发送输入",
    running: "正在向 Shell 发送输入",
    completed: "已向 Shell 发送输入",
    error: "已尝试向 Shell 发送输入",
    cancelled: "向 Shell 发送输入已停止",
  },
  list_exec_sessions: {
    preparing: "正在准备查看 Shell 任务",
    running: "正在查看 Shell 任务",
    completed: "已查看 Shell 任务",
    error: "已尝试查看 Shell 任务",
    cancelled: "查看 Shell 任务已停止",
  },
};

const INFERRED_TOOL_COPY: Array<{
  keywords: string[];
  copy: ToolCopy;
}> = [
  {
    keywords: ["search", "find", "query", "grep"],
    copy: actionCopy("搜索信息", "已搜索信息"),
  },
  {
    keywords: ["delete", "remove"],
    copy: actionCopy("删除内容", "已删除内容"),
  },
  {
    keywords: ["edit", "update", "patch", "modify"],
    copy: actionCopy("更新内容", "已更新内容"),
  },
  {
    keywords: ["create", "write", "save"],
    copy: actionCopy("创建内容", "已创建内容"),
  },
  {
    keywords: ["read", "get", "fetch", "download"],
    copy: actionCopy("获取信息", "已获取信息"),
  },
  {
    keywords: ["exec", "run", "execute", "shell"],
    copy: actionCopy("运行外部操作", "已运行外部操作"),
  },
  {
    keywords: ["send", "post", "upload"],
    copy: actionCopy("发送内容", "已发送内容"),
  },
  {
    keywords: ["list"],
    copy: actionCopy("查看列表", "已查看列表"),
  },
];

const FALLBACK_COPY: ToolCopy = {
  preparing: "正在准备外部操作",
  running: "正在执行外部操作",
  completed: "已完成外部操作",
  error: "已执行外部操作",
  cancelled: "外部操作已停止",
};

function actionCopy(action: string, completed: string): ToolCopy {
  return {
    preparing: `正在准备${action}`,
    running: `正在${action}`,
    completed,
    error: `已尝试${action}`,
    cancelled: `${action}已停止`,
  };
}

function inferredCopy(name: string): ToolCopy {
  const tokens = name.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  return (
    INFERRED_TOOL_COPY.find(({ keywords }) =>
      keywords.some((keyword) => tokens.includes(keyword)),
    )?.copy ?? FALLBACK_COPY
  );
}

function shortValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null &&
    typeof value === "object" &&
    !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function displayFileName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) || path;
}

function textLineCount(value: unknown): number {
  if (typeof value !== "string" || !value) return 0;
  return textLines(value).length;
}

function mutationSummary(tool: ToolActivity): string | null {
  const argumentsValue = asRecord(tool.arguments);
  if (!argumentsValue) return null;

  if (tool.name === "write_file") {
    const path =
      typeof argumentsValue.path === "string"
        ? displayFileName(argumentsValue.path)
        : "";
    const added = textLineCount(argumentsValue.content);
    return [path, added ? `+${added}` : ""].filter(Boolean).join(" · ");
  }

  if (tool.name === "edit_file") {
    const path =
      typeof argumentsValue.path === "string"
        ? displayFileName(argumentsValue.path)
        : "";
    const added = textLineCount(argumentsValue.new_text);
    const deleted = textLineCount(argumentsValue.old_text);
    const stats = [
      added ? `+${added}` : "",
      deleted ? `−${deleted}` : "",
    ]
      .filter(Boolean)
      .join(" ");
    return [path, stats].filter(Boolean).join(" · ");
  }

  if (tool.name !== "apply_patch") return null;
  const resultEdits =
    tool.detail?.kind === "mutation" ? tool.detail.edits : undefined;
  const argumentEdits = Array.isArray(argumentsValue.edits)
    ? argumentsValue.edits
    : [];
  const edits = resultEdits?.length ? resultEdits : argumentEdits;
  const paths = edits.flatMap((value) => {
    const edit = asRecord(value);
    return typeof edit?.path === "string" ? [edit.path] : [];
  });
  const target =
    paths.length === 1
      ? displayFileName(paths[0])
      : paths.length > 1
        ? `${paths.length} 个文件`
        : "";
  const added = resultEdits?.reduce((sum, edit) => sum + (edit.added ?? 0), 0);
  const deleted = resultEdits?.reduce(
    (sum, edit) => sum + (edit.deleted ?? 0),
    0,
  );
  const stats = [
    added ? `+${added}` : "",
    deleted ? `−${deleted}` : "",
  ]
    .filter(Boolean)
    .join(" ");
  return [target, stats].filter(Boolean).join(" · ");
}

function streamedToolHint(argumentsValue: string): string {
  const match = argumentsValue.match(
    /"(?:path|command|query|url)"\s*:\s*"((?:\\.|[^"\\])*)"/,
  );
  if (!match) return "";
  try {
    return String(JSON.parse(`"${match[1]}"`)).slice(0, 100);
  } catch {
    return match[1].slice(0, 100);
  }
}

function streamedTextLineCount(argumentsValue: string): number | null {
  const pattern = /"(?:content|new_text)"\s*:\s*"/g;
  let totalLines = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(argumentsValue)) !== null) {
    totalLines += 1;
    let index = match.index + match[0].length;
    while (index < argumentsValue.length) {
      const character = argumentsValue[index];
      if (character === "\\" && index + 1 < argumentsValue.length) {
        const escaped = argumentsValue[index + 1];
        if (escaped === "n") totalLines += 1;
        if (
          escaped === "u" &&
          argumentsValue.slice(index + 2, index + 6).toLowerCase() === "000a"
        ) {
          totalLines += 1;
          index += 6;
          continue;
        }
        index += 2;
        continue;
      }
      if (character === '"') {
        pattern.lastIndex = index + 1;
        break;
      }
      if (character === "\n") totalLines += 1;
      index += 1;
    }
    if (index >= argumentsValue.length) {
      pattern.lastIndex = argumentsValue.length;
    }
  }

  return totalLines || null;
}

function toolSummary(tool: ToolActivity): string {
  if (
    (tool.status === "preparing" || tool.status === "cancelled") &&
    tool.streamedArguments
  ) {
    const hint = streamedToolHint(tool.streamedArguments);
    const lineCount = streamedTextLineCount(tool.streamedArguments);
    const progress = lineCount
      ? `已生成 ${lineCount} 行`
      : tool.status === "cancelled"
        ? "参数未完成"
        : "正在生成参数";
    return [hint, progress].filter(Boolean).join(" · ");
  }

  const mutation = mutationSummary(tool);
  if (mutation !== null) return mutation;

  if (
    tool.name === "list_exec_sessions" &&
    tool.detail?.kind === "shellSessions"
  ) {
    const count = tool.detail.sessions.length;
    return count ? `${count} 个活动会话` : "没有活动会话";
  }

  const argumentsValue = tool.arguments;
  if (!argumentsValue || typeof argumentsValue !== "object") {
    return shortValue(argumentsValue || "").slice(0, 100);
  }
  const values = argumentsValue as Record<string, unknown>;
  const preferredKey = ["path", "command", "query", "url"].find(
    (key) => values[key] !== undefined,
  );
  if (preferredKey) return shortValue(values[preferredKey]).slice(0, 100);
  return Object.entries(values)
    .slice(0, 2)
    .map(([key, value]) => `${key}: ${shortValue(value)}`)
    .join(", ")
    .slice(0, 100);
}

function durationLabel(duration: number | undefined): string {
  if (duration === undefined) return "";
  return `${duration < 1 ? duration.toFixed(2) : duration.toFixed(1)}s`;
}

export function getToolPresentation(tool: ToolActivity): ToolPresentation {
  const copy = BUILTIN_TOOL_COPY[tool.name] ?? inferredCopy(tool.name);
  return {
    label: copy[tool.status],
    summary: toolSummary(tool),
    duration: durationLabel(tool.durationSeconds),
    technicalName: tool.name,
  };
}
