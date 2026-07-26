import type {
  MutationEditSummary,
  MutationToolDetail,
  ReadToolDetail,
  ShellSessionSummary,
  ShellSessionsToolDetail,
  ShellToolDetail,
  ToolActivity,
  ToolActivityDetail,
} from "./types/api";

const SHELL_TOOLS = new Set(["exec", "write_stdin"]);
const SHELL_SESSIONS_TOOL = "list_exec_sessions";
const MUTATION_TOOLS = new Set(["write_file", "edit_file", "apply_patch"]);
const READ_TOOLS = new Set(["read_file", "list_dir", "find_files", "grep"]);
const SHELL_OUTPUT_LIMIT = 16_000;
const SHELL_STDERR_LIMIT = 6_000;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null &&
    typeof value === "object" &&
    !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function parseDocument(value: unknown): Record<string, unknown> | null {
  const record = asRecord(value);
  if (record) return record;
  if (typeof value !== "string" || !value) return null;
  try {
    return asRecord(JSON.parse(value));
  } catch {
    return null;
  }
}

function stringValue(
  document: Record<string, unknown>,
  ...keys: string[]
): string | undefined {
  for (const key of keys) {
    const value = document[key];
    if (typeof value === "string") return value;
  }
  return undefined;
}

function limitedStringValue(
  document: Record<string, unknown>,
  limit: number,
  ...keys: string[]
): string | undefined {
  return stringValue(document, ...keys)?.slice(0, limit);
}

function booleanValue(
  document: Record<string, unknown>,
  ...keys: string[]
): boolean | undefined {
  for (const key of keys) {
    const value = document[key];
    if (typeof value === "boolean") return value;
  }
  return undefined;
}

function numberValue(
  document: Record<string, unknown>,
  ...keys: string[]
): number | undefined {
  for (const key of keys) {
    const value = document[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return undefined;
}

function boundedText(
  value: string | undefined,
  limit: number,
): { text: string; omitted: number } {
  if (!value) return { text: "", omitted: 0 };
  if (value.length <= limit) return { text: value, omitted: 0 };
  const tailLength = Math.min(Math.floor(limit / 3), 4_000);
  const headLength = limit - tailLength;
  const omitted = value.length - limit;
  return {
    text:
      value.slice(0, headLength) +
      `\n… 已省略 ${omitted} 个字符 …\n` +
      value.slice(-tailLength),
    omitted,
  };
}

function shellDetail(document: Record<string, unknown>): ShellToolDetail {
  const output = boundedText(
    stringValue(document, "output"),
    SHELL_OUTPUT_LIMIT,
  );
  const stdout = boundedText(
    stringValue(document, "stdout"),
    SHELL_OUTPUT_LIMIT,
  );
  const stderr = boundedText(
    stringValue(document, "stderr"),
    SHELL_STDERR_LIMIT,
  );
  const upstreamTruncated =
    (numberValue(document, "truncatedCharacters") ??
      numberValue(document, "truncated_chars") ??
      0) +
    (numberValue(document, "stdout_truncated_chars") ?? 0) +
    (numberValue(document, "stderr_truncated_chars") ?? 0);
  const rawExitCode =
    document.exitCode !== undefined
      ? document.exitCode
      : document.exit_code;
  const exitCode =
    rawExitCode === null
      ? null
      : typeof rawExitCode === "number" && Number.isFinite(rawExitCode)
        ? rawExitCode
        : undefined;

  return {
    kind: "shell",
    sessionId: limitedStringValue(
      document,
      300,
      "sessionId",
      "session_id",
    ),
    command: limitedStringValue(document, 4_000, "command"),
    workingDirectory: limitedStringValue(
      document,
      1_000,
      "workingDirectory",
      "working_dir",
    ),
    output: output.text,
    stdout: stdout.text,
    stderr: stderr.text,
    exitCode,
    running: booleanValue(document, "running"),
    done: booleanValue(document, "done"),
    timedOut: booleanValue(document, "timedOut", "timed_out"),
    terminated: booleanValue(document, "terminated"),
    elapsedSeconds: numberValue(
      document,
      "elapsedSeconds",
      "elapsed_seconds",
    ),
    truncatedCharacters:
      upstreamTruncated + output.omitted + stdout.omitted + stderr.omitted,
  };
}

function shellSessionSummary(value: unknown): ShellSessionSummary | null {
  const document = asRecord(value);
  if (!document) return null;
  const sessionId = limitedStringValue(
    document,
    300,
    "sessionId",
    "session_id",
  );
  if (!sessionId) return null;
  const rawExitCode =
    document.exitCode !== undefined
      ? document.exitCode
      : document.exit_code;
  const exitCode =
    rawExitCode === null
      ? null
      : typeof rawExitCode === "number" && Number.isFinite(rawExitCode)
        ? rawExitCode
        : undefined;
  const rawRemainingSeconds =
    document.remainingSeconds !== undefined
      ? document.remainingSeconds
      : document.remaining_seconds;
  const remainingSeconds =
    rawRemainingSeconds === null
      ? null
      : typeof rawRemainingSeconds === "number" &&
          Number.isFinite(rawRemainingSeconds)
        ? rawRemainingSeconds
        : undefined;

  return {
    sessionId,
    command: limitedStringValue(document, 4_000, "command") ?? "",
    workingDirectory: limitedStringValue(
      document,
      1_000,
      "workingDirectory",
      "working_dir",
    ),
    running: booleanValue(document, "running") ?? false,
    exitCode,
    elapsedSeconds: numberValue(
      document,
      "elapsedSeconds",
      "elapsed_seconds",
    ),
    idleSeconds: numberValue(document, "idleSeconds", "idle_seconds"),
    remainingSeconds,
  };
}

function shellSessionsDetail(
  document: Record<string, unknown>,
): ShellSessionsToolDetail {
  const sessions = Array.isArray(document.sessions)
    ? document.sessions
        .flatMap((value) => {
          const session = shellSessionSummary(value);
          return session ? [session] : [];
        })
        .slice(0, 20)
    : [];
  return { kind: "shellSessions", sessions };
}

function mutationEdits(value: unknown): MutationEditSummary[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const edits = value.flatMap((item) => {
    const edit = asRecord(item);
    const path = edit ? stringValue(edit, "path") : undefined;
    if (!edit || !path) return [];
    return [
      {
        path: path.slice(0, 1_000),
        action: limitedStringValue(edit, 100, "action"),
        added: numberValue(edit, "added"),
        deleted: numberValue(edit, "deleted"),
      } satisfies MutationEditSummary,
    ];
  });
  return edits.length ? edits.slice(0, 20) : undefined;
}

function mutationDetail(
  document: Record<string, unknown>,
): MutationToolDetail {
  return {
    kind: "mutation",
    path: limitedStringValue(document, 1_000, "path"),
    created: booleanValue(document, "created"),
    dryRun: booleanValue(document, "dryRun", "dry_run"),
    bytesWritten: numberValue(
      document,
      "bytesWritten",
      "bytes_written",
    ),
    replacements: numberValue(document, "replacements"),
    warning: limitedStringValue(document, 1_000, "warning"),
    edits: mutationEdits(document.edits),
  };
}

function stringItems(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const items = value.filter(
    (item): item is string => typeof item === "string" && Boolean(item),
  );
  return items.length ? items.slice(0, 20) : undefined;
}

function resultPaths(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item === "string" && item) return [item];
    const document = asRecord(item);
    const path = document ? stringValue(document, "path") : undefined;
    return path ? [path] : [];
  });
}

function readResultItems(
  document: Record<string, unknown>,
): string[] | undefined {
  const items = [
    ...resultPaths(document.entries),
    ...resultPaths(document.files),
    ...resultPaths(document.counts),
    ...resultPaths(document.matches),
  ];
  const unique = Array.from(new Set(items));
  return unique.length ? unique.slice(0, 20) : undefined;
}

function readDetail(document: Record<string, unknown>): ReadToolDetail {
  return {
    kind: "read",
    path: limitedStringValue(document, 1_000, "path"),
    startLine: numberValue(document, "startLine", "start_line"),
    endLine: numberValue(document, "endLine", "end_line"),
    totalLines: numberValue(document, "totalLines", "total_lines"),
    pages: limitedStringValue(document, 100, "pages"),
    totalPages: numberValue(document, "totalPages", "total_pages"),
    totalEntries: numberValue(document, "totalEntries", "total_entries"),
    totalMatches: numberValue(document, "totalMatches", "total_matches"),
    items: stringItems(document.items) ?? readResultItems(document),
    truncated: booleanValue(document, "truncated"),
    deduplicated: booleanValue(document, "deduplicated"),
  };
}

export function parseToolActivityDetail(
  value: unknown,
): ToolActivityDetail | undefined {
  const document = parseDocument(value);
  if (!document) return undefined;
  if (document.kind === "shell") return shellDetail(document);
  if (document.kind === "shellSessions") {
    return shellSessionsDetail(document);
  }
  if (document.kind === "mutation") return mutationDetail(document);
  if (document.kind === "read") return readDetail(document);
  return undefined;
}

export function detailFromStoredToolResult(
  name: string,
  value: unknown,
): ToolActivityDetail | undefined {
  const document = parseDocument(value);
  if (!document) return undefined;
  if (SHELL_TOOLS.has(name)) return shellDetail(document);
  if (name === SHELL_SESSIONS_TOOL) return shellSessionsDetail(document);
  if (MUTATION_TOOLS.has(name)) return mutationDetail(document);
  if (READ_TOOLS.has(name)) return readDetail(document);
  return undefined;
}

export function toolResultError(value: unknown): string | null {
  const document = parseDocument(value);
  if (!document) return null;
  const error = document.error;
  if (typeof error === "string" && error) return error;
  const errorDocument = asRecord(error);
  return typeof errorDocument?.message === "string"
    ? errorDocument.message
    : null;
}

function toolCommand(tool: ToolActivity): string {
  if (tool.detail?.kind === "shell" && tool.detail.command) {
    return tool.detail.command;
  }
  const argumentsValue = asRecord(tool.arguments);
  return typeof argumentsValue?.command === "string"
    ? argumentsValue.command
    : "";
}

export function normalizeToolActivityOutcome(
  tool: ToolActivity,
): ToolActivity {
  if (
    (tool.name !== "exec" && tool.name !== "write_stdin") ||
    tool.detail?.kind !== "shell"
  ) {
    return tool;
  }

  const detail = tool.detail;
  if (detail.timedOut) {
    return {
      ...tool,
      status: "error",
      errorMessage: "Shell 命令执行超时",
    };
  }
  if (detail.terminated) {
    return {
      ...tool,
      status: "cancelled",
      errorMessage: undefined,
    };
  }
  if (detail.running || detail.done === false) {
    return {
      ...tool,
      status: "running",
      errorMessage: undefined,
    };
  }
  if (
    detail.exitCode !== undefined &&
    detail.exitCode !== null &&
    detail.exitCode !== 0
  ) {
    const command = toolCommand(tool).slice(0, 100);
    return {
      ...tool,
      status: "error",
      errorMessage: [command, `exit ${detail.exitCode}`]
        .filter(Boolean)
        .join(" · "),
    };
  }
  return tool;
}
